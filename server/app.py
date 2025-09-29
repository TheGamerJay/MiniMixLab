import os, uuid, time, tempfile, subprocess, json, threading, queue
import numpy as np
import librosa
from flask import Flask, request, send_file, jsonify, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room

BASE = os.path.dirname(__file__)
STORE = os.path.join(BASE, "storage")
MIXES = os.path.join(BASE, "mixes")
os.makedirs(STORE, exist_ok=True)
os.makedirs(MIXES, exist_ok=True)

app = Flask(__name__)
CORS(app, supports_credentials=True)
app.config["SECRET_KEY"] = os.environ.get("LOCAL_SECRET_KEY") or os.environ.get("SECRET_KEY", "dev_key")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

def ffmpeg(*args):
    cmd = ["ffmpeg","-hide_banner","-loglevel","error"] + list(args)
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

# --- NEW: simple in-memory stores (you can persist later)
PROJECT = {"bpm": 120.0, "key": "C"}   # default project tempo/key
ANALYSIS = {}  # file_id -> {"bpm": float, "key": "Am", "first_beat": seconds}

# --- NEW: helpers
MAJOR_KEYS = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
MINOR_KEYS = [k+"m" for k in MAJOR_KEYS]
# Krumhansl key profiles (normalized)
_K_MAJOR = np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88])
_K_MINOR = np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])

# --- key → semitone helpers
PITCH_CLASS = {"C":0,"C#":1,"Db":1,"D":2,"D#":3,"Eb":3,"E":4,"F":5,"F#":6,"Gb":6,"G":7,"G#":8,"Ab":8,"A":9,"A#":10,"Bb":10,"B":11}

def _parse_key(k: str):
    if not k or k=="Unknown": return (None, "maj")
    k = k.strip()
    mode = "min" if k.endswith("m") or "min" in k.lower() else "maj"
    root = k[:-1] if k.endswith("m") else k
    root = root.replace("maj","").replace("min","").strip()
    root_pc = PITCH_CLASS.get(root, None)
    return (root_pc, mode)

def semitone_delta(from_key: str, to_key: str):
    fr, fm = _parse_key(from_key)
    tr, tm = _parse_key(to_key)
    if fr is None or tr is None: return 0  # fallback: no shift
    # naive approach: match tonic; ignore mode for now (extension: map relative maj/min if desired)
    delta = (tr - fr) % 12
    # choose the shortest direction (e.g., +7 vs -5 -> pick -5)
    if delta > 6: delta -= 12
    return int(delta)

def atempo_chain(value: float):
    # FFmpeg atempo supports 0.5..2.0; chain if outside
    v = max(0.05, float(value))
    chain = []
    while v < 0.5 or v > 2.0:
        step = 2.0 if v > 2.0 else 0.5
        chain.append(f"atempo={step}")
        v = v/step if step==2.0 else v/0.5
    chain.append(f"atempo={v}")
    return ",".join(chain)

def _estimate_key(y, sr):
    # chroma via CQT then average over time
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma = np.mean(chroma, axis=1)  # 12-bin
    # try all rotations
    scores_major = [np.corrcoef(np.roll(chroma, -i), _K_MAJOR)[0,1] for i in range(12)]
    scores_minor = [np.corrcoef(np.roll(chroma, -i), _K_MINOR)[0,1] for i in range(12)]
    i_maj = int(np.argmax(scores_major))
    i_min = int(np.argmax(scores_minor))
    if scores_major[i_maj] >= scores_minor[i_min]:
        return MAJOR_KEYS[i_maj]             # e.g., "G"
    else:
        return MINOR_KEYS[i_min]             # e.g., "Em"

def analyze_audio(path):
    # downmix & resample for analysis (fast & memory-friendly)
    y, sr = librosa.load(path, sr=22050, mono=True)
    # beat tracking
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    first_beat = float(beats[0]) if len(beats) else 0.0
    # key estimate
    key = _estimate_key(y, sr)
    return float(tempo), key, first_beat

def segment_song(path, sr=22050, k_segments=8):
    """
    Returns a list of segments: [{start, end, label, confidence}]
    Uses librosa structural segmentation (recurrence matrix + clustering).
    """
    y, sr = librosa.load(path, sr=sr, mono=True)
    # Beat-synchronous chroma for structure
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units='frames')
    if len(beats) < 4:
        # Fallback: uniform chunks of ~15s
        dur = librosa.get_duration(y=y, sr=sr)
        step = max(10.0, dur / k_segments)
        segs = []
        t = 0.0
        while t < dur:
            segs.append({"start": t, "end": min(t+step, dur), "label": "Section", "confidence": 0.3})
            t += step
        return segs

    C = librosa.feature.chroma_cqt(y=y, sr=sr)
    # Beat-sync chroma
    C_sync = librosa.util.sync(C, librosa.beat.beat_track(y=y, sr=sr)[1])
    R = librosa.segment.recurrence_matrix(C_sync, sym=True, mode='affinity', metric='cosine')
    # Path enhancement to emphasize diagonals (repeated structure)
    Rf = librosa.segment.path_enhance(R, diagonal=True)
    # Laplacian segmentation to k segments
    seg_ids = librosa.segment.agglomerative(Rf, k=k_segments)
    # Map beat indices to times
    beat_times = librosa.frames_to_time(librosa.beat.beat_track(y=y, sr=sr)[1], sr=sr)
    # Build continuous ranges for each cluster id
    boundaries = [0]
    for i in range(1, len(seg_ids)):
        if seg_ids[i] != seg_ids[i-1]:
            boundaries.append(i)
    boundaries.append(len(seg_ids)-1)

    # Convert to times
    segments = []
    for i in range(len(boundaries)-1):
        b0 = boundaries[i]
        b1 = boundaries[i+1]
        start = float(beat_times[b0]) if b0 < len(beat_times) else 0.0
        end = float(beat_times[b1]) if b1 < len(beat_times) else float(librosa.get_duration(y=y, sr=sr))
        if end - start < 2.5:  # drop ultra-short blips
            continue
        segments.append({"start": start, "end": end})

    # Labeling heuristic:
    # - Most repeated chroma pattern → "Chorus"
    # - First low-energy → "Intro"
    # - Last high-energy unique → "Bridge"
    # - Others → "Verse"
    # Compute energy per segment and a crude repetition score
    S = np.abs(librosa.stft(y))
    rms = librosa.feature.rms(S=S, frame_length=2048, hop_length=512).flatten()
    t_frames = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=512)
    def seg_energy(s,e):
        idx = np.where((t_frames>=s)&(t_frames<e))[0]
        return float(np.mean(rms[idx])) if len(idx) else 0.0

    # Chroma mean per segment for repetition similarity
    def seg_chroma_sim(s,e):
        f0 = librosa.time_to_frames(s, sr=sr)
        f1 = librosa.time_to_frames(e, sr=sr)
        c = C[:, max(0,f0):min(C.shape[1],f1)]
        return np.mean(c, axis=1) if c.size else np.zeros((12,))

    chroma_means = [seg_chroma_sim(s["start"], s["end"]) for s in segments]
    # Pairwise cosine sims
    sims = np.zeros((len(segments),len(segments)))
    for i in range(len(segments)):
        for j in range(len(segments)):
            a, b = chroma_means[i], chroma_means[j]
            if np.linalg.norm(a)==0 or np.linalg.norm(b)==0:
                sims[i,j]=0
            else:
                sims[i,j]= float(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)))
    rep_score = np.sum(sims, axis=1)  # how much it repeats overall

    energies = [seg_energy(s["start"], s["end"]) for s in segments]

    # Pick labels
    if segments:
        chorus_idx = int(np.argmax(rep_score))
        intro_idx = int(np.argmin(np.abs([s["start"] for s in segments])))  # earliest
        bridge_idx = int(np.argmin(rep_score))  # least-repeating
        # Assign
        for i, s in enumerate(segments):
            label = "Verse"
            conf = 0.6
            if i == chorus_idx: label, conf = "Chorus", 0.9
            if i == intro_idx and s["start"] < (segments[0]["end"]-segments[0]["start"])*1.5:
                label, conf = "Intro", 0.8
            if i == bridge_idx and i not in (chorus_idx, intro_idx):
                label, conf = "Bridge", 0.7
            s["label"] = label
            s["confidence"] = conf
    return segments

# ---- SECTIONS (global defaults; you can persist per-project if you want)
SECTIONS = [
    {"label": "Intro",   "start": 0,   "end": 30},
    {"label": "Verse 1", "start": 30,  "end": 70},
    {"label": "Chorus",  "start": 70,  "end": 100},
    {"label": "Bridge",  "start": 100, "end": 135},
    {"label": "Chorus 2","start": 135, "end": 165},
]

@app.get("/api/sections")
def get_sections():
    return jsonify({"sections": SECTIONS})

@app.post("/api/sections")
def set_sections():
    # Accepts: { sections: [ {label, start, end}, ... ] }
    data = request.get_json(force=True)
    secs = data.get("sections", [])
    if not isinstance(secs, list) or not secs:
        return jsonify({"error": "invalid sections"}), 400
    global SECTIONS
    SECTIONS = [
        {"label": s["label"], "start": float(s["start"]), "end": float(s["end"])}
        for s in secs
    ]
    return jsonify({"ok": True, "sections": SECTIONS})

# --- NEW: project settings endpoints
@app.get("/api/project")
def get_project():
    return jsonify(PROJECT)

@app.post("/api/project")
def set_project():
    data = request.get_json(force=True)
    if "bpm" in data: PROJECT["bpm"] = float(data["bpm"])
    if "key" in data: PROJECT["key"] = str(data["key"])
    return jsonify(PROJECT)

# --- NEW: auto-align endpoint
# body: { "file_ids": ["..",".."] }
@app.post("/api/auto_align")
def auto_align():
    data = request.get_json(force=True)
    ids = data.get("file_ids", [])
    if not ids: return jsonify({"error":"file_ids required"}), 400
    target_bpm = float(data.get("target_bpm", PROJECT["bpm"]))

    result = []
    for fid in ids:
        a = ANALYSIS.get(fid)
        if not a:
            # fallback analyze on the fly
            p = os.path.join(STORE, fid)
            if not os.path.exists(p):
                return jsonify({"error": f"missing {fid}"}), 400
            bpm, key, first_beat = analyze_audio(p)
            a = ANALYSIS[fid] = {"bpm": bpm, "key": key, "first_beat": first_beat}

        src_bpm = max(a.get("bpm", 0.0), 1e-6)
        speed = target_bpm / src_bpm         # >1.0 = speed up, <1.0 = slow down
        # Align first downbeat to project grid start (offset compensates lead-in)
        offset = -float(a.get("first_beat", 0.0))
        result.append({
            "file_id": fid,
            "detected_bpm": a["bpm"],
            "detected_key": a["key"],
            "suggested_speed": float(speed),
            "suggested_offset": float(max(0.0, offset)),  # don't go negative in this simple model
        })
    return jsonify({"target_bpm": target_bpm, "tracks": result})

@app.post("/api/auto_pitch")
def auto_pitch():
    data = request.get_json(force=True)
    file_ids = data.get("file_ids", [])
    project_key = data.get("project_key", "C")
    out = []
    for fid in file_ids:
        a = ANALYSIS.get(fid) or {}
        from_key = a.get("key","Unknown")
        st = semitone_delta(from_key, project_key)
        out.append({"file_id": fid, "detected_key": from_key, "target_key": project_key, "semitones": st})
    return jsonify({"target_key": project_key, "tracks": out})

@app.get("/api/segment")
def api_segment():
    fid = request.args.get("file_id")
    if not fid: return jsonify({"error":"file_id required"}), 400
    src = os.path.join(STORE, fid)
    if not os.path.exists(src): return jsonify({"error":"not found"}), 404
    segs = segment_song(src, k_segments=8)
    return jsonify({"file_id": fid, "segments": segs})

@app.post("/api/render_arrangement")
def render_arrangement():
    """
    body: {
      "pieces": [ { "file_id": "...", "start": float, "end": float,
                    "speed": 1.0, "gain": -3.0, "pitch": 0 } ],  # pitch in semitones (can be 0)
      "xfade_ms": 200,
      "bar_aware": true,
      "project_bpm": 120,
      "beats_per_bar": 4,
      "snap_to_bars": true,
      "align_key": true,
      "project_key": "Am",
      "hq_pitch": true
    }
    """
    payload = request.get_json(force=True)
    pieces = payload.get("pieces", [])
    if not pieces: return jsonify({"error":"no pieces"}), 400

    xfade_ms_req = int(payload.get("xfade_ms", 200))
    bar_aware     = bool(payload.get("bar_aware", False))
    snap_to_bars  = bool(payload.get("snap_to_bars", True))
    project_bpm   = float(payload.get("project_bpm", 120.0))
    beats_per_bar = int(payload.get("beats_per_bar", 4))
    align_key     = bool(payload.get("align_key", False))
    project_key   = str(payload.get("project_key", "C"))
    hq_pitch      = bool(payload.get("hq_pitch", True))

    def seconds_per_beat(bpm): return 60.0 / max(bpm, 1e-6)
    spb = seconds_per_beat(project_bpm)
    bar_seconds = spb * beats_per_bar
    safe_min_piece = 0.75

    # normalize/snap + compute per-piece pitch if align_key requested
    norm = []
    for p in pieces:
        src = os.path.join(STORE, p["file_id"])
        if not os.path.exists(src): return jsonify({"error": f"missing {p['file_id']}"}), 400

        start = float(p.get("start",0.0))
        end   = float(p.get("end", start+10.0))
        speed = float(p.get("speed",1.0))
        gain  = float(p.get("gain",0.0))
        raw_len = max(safe_min_piece, end-start)

        if bar_aware and snap_to_bars:
            bars = max(1, int(round(raw_len / bar_seconds)) or 1)
            end  = start + bars*bar_seconds

        # pitch: explicit from piece or computed from analysis
        if "pitch" in p and p["pitch"] is not None:
            semi = int(p["pitch"])
        elif align_key:
            detected = ANALYSIS.get(p["file_id"], {}).get("key", "Unknown")
            semi = semitone_delta(detected, project_key)
        else:
            semi = 0

        norm.append({"file_id": p["file_id"], "start": start, "end": end,
                     "speed": speed, "gain": gain, "pitch": semi})

    # build graph
    inputs, filters, outs = [], [], []
    for i, p in enumerate(norm):
        inputs += ["-i", os.path.join(STORE, p["file_id"])]
        lbl = f"s{i}"

        # pitch shift via asetrate + aresample (ratio r = 2^(semitones/12))
        r = 2.0 ** (p["pitch"] / 12.0)
        # combine tempo: we ALSO want overall tempo factor = p["speed"] (from BPM align)
        # asetrate changes both pitch & tempo by r; then atempo(1/r) restores tempo.
        # to achieve final tempo factor = speed, we set total atempo = (speed / r).
        combined_atempo = p["speed"] / max(r, 1e-6)

        filters.append(
            f"[{i}:a]"
            f" atrim={p['start']}:{p['end']}, asetpts=PTS-STARTPTS,"
            f" asetrate=48000*{r:.8f}, aresample=48000,"
            f" {atempo_chain(combined_atempo)},"
            f" volume={10**(p['gain']/20):.6f}"
            f" [{lbl}]"
        )
        outs.append(f"[{lbl}]")

    # acrossfades with bar-aware caps
    acc, cur = [], outs[0] if outs else None
    for i in range(1, len(outs)):
        prev_len = norm[i-1]["end"] - norm[i-1]["start"]
        next_len = norm[i]["end"]   - norm[i]["start"]
        max_allowed = min(
            bar_seconds if bar_aware else 999,
            prev_len * 0.5 - 0.05,
            next_len * 0.5 - 0.05
        )
        max_allowed = max(safe_min_piece/4, max_allowed)
        d_sec = min(xfade_ms_req/1000.0, max_allowed)
        d_sec = max(0.05, float(d_sec))
        outlbl = f"mix{i}"
        acc.append(f"{cur}{outs[i]} acrossfade=d={d_sec}:c1=tri:c2=tri [{outlbl}]")
        cur = f"[{outlbl}]"

    fc = "; ".join(filters + acc)
    out_id, out_path = f"{uuid.uuid4()}.wav", os.path.join(MIXES, f"{uuid.uuid4()}.wav")
    args = inputs + ["-filter_complex", fc or "", "-map", cur if outs else "0:a", "-ac", "2", out_path]
    r = ffmpeg(*args)
    if r.returncode != 0:
        return jsonify({"error":"ffmpeg_failed","stderr": r.stderr.decode()}), 500
    return jsonify({"mix_id": os.path.basename(out_path), "url": f"/api/mix/file/{os.path.basename(out_path)}"})

# ---- upload
@app.post("/api/upload")
def upload():
    f = request.files.get("file")
    if not f: return jsonify({"error":"file required"}), 400
    ext = os.path.splitext(f.filename)[1].lower() or ".wav"
    fid = str(uuid.uuid4()) + ext
    path = os.path.join(STORE, fid)
    f.save(path)

    # duration probe
    pr = subprocess.run(
        ["ffprobe","-v","error","-show_entries","format=duration","-of","json",path],
        stdout=subprocess.PIPE
    )
    meta = json.loads(pr.stdout or b"{}")
    duration = float(meta.get("format",{}).get("duration",0))

    # NEW: audio analysis (tempo/key/first beat)
    try:
        bpm, key, first_beat = analyze_audio(path)
    except Exception as e:
        bpm, key, first_beat = 0.0, "Unknown", 0.0

    ANALYSIS[fid] = {"bpm": bpm, "key": key, "first_beat": first_beat, "duration": duration}
    return jsonify({"file_id": fid, "duration": duration, "analysis": ANALYSIS[fid]})

# ---- memory-safe preview slice
@app.get("/api/preview")
def preview():
    fid = request.args.get("file_id")
    start = float(request.args.get("start", 0))
    end = float(request.args.get("end", start+15))
    speed = float(request.args.get("speed", 1.0))
    src = os.path.join(STORE, fid)
    if not os.path.exists(src): return jsonify({"error":"not found"}), 404

    def generate():
        # Chain atempo into 0.5..2.0 safe steps
        sp = speed
        atempo_chain = []
        while sp < 0.5 or sp > 2.0:
            step = 2.0 if sp > 2.0 else 0.5
            atempo_chain.append(f"atempo={step}")
            sp = sp/step if sp > 2.0 else sp/0.5
        atempo_chain.append(f"atempo={sp}")
        args = [
            "-ss", str(start), "-to", str(end),
            "-i", src,
            "-filter:a", ",".join(atempo_chain),
            "-map", "a:0", "-b:a", "128k", "-f", "mp3", "pipe:1"
        ]
        proc = subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error"]+args,
                                stdout=subprocess.PIPE)
        try:
            while True:
                chunk = proc.stdout.read(64*1024)
                if not chunk: break
                yield chunk
        finally:
            proc.kill()

    return Response(generate(), mimetype="audio/mpeg")

# ---- mixing with progress (Socket.IO)
JOBS = {}  # job_id -> {"status": "queued|running|done|error|cancelled", "result": mix_id or None}

def progress_emit(room, pct, msg=""):
    socketio.emit("mix_progress", {"percent": pct, "message": msg}, to=room)

def build_mix(job_id, room, tracks):
    try:
        JOBS[job_id]["status"] = "running"
        progress_emit(room, 5, "Preparing")

        inputs = []
        filters = []
        amix_inputs = []

        for i, t in enumerate(tracks):
            src = os.path.join(STORE, t["file_id"])
            if not os.path.exists(src):
                raise RuntimeError(f"missing {t['file_id']}")
            inputs += ["-i", src]
            speed = float(t.get("speed",1.0))
            gain  = float(t.get("gain",0.0))
            start = float(t.get("offset",0.0))

            # chain safe atempo
            sp = speed
            atempo = []
            while sp < 0.5 or sp > 2.0:
                step = 2.0 if sp > 2.0 else 0.5
                atempo.append(f"atempo={step}")
                sp = sp/step if sp > 2.0 else sp/0.5
            atempo.append(f"atempo={sp}")
            lbl = f"a{i}"
            ms = int(start*1000)
            filters.append(f"[{i}:a] adelay={ms}|{ms}, {','.join(atempo)}, volume={10**(gain/20):.6f} [{lbl}]")
            amix_inputs.append(f"[{lbl}]")

        progress_emit(room, 40, "Mixing")
        filter_complex = "; ".join(filters) + f"; {''.join(amix_inputs)} amix=inputs={len(tracks)}:normalize=0 [mix]"

        out_id = f"{uuid.uuid4()}.wav"
        out_path = os.path.join(MIXES, out_id)
        args = inputs + ["-filter_complex", filter_complex, "-map", "[mix]", "-ac", "2", out_path]
        r = ffmpeg(*args)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode())

        JOBS[job_id]["status"] = "done"
        JOBS[job_id]["result"] = out_id
        progress_emit(room, 100, "Done")
    except Exception as e:
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["result"] = str(e)
        progress_emit(room, 100, f"Error: {e}")

@app.post("/api/mix")
def mix():
    payload = request.get_json(force=True)
    tracks = payload.get("tracks", [])
    socket_room = payload.get("socket_room")  # client-provided UUID to receive progress
    if not tracks: return jsonify({"error":"no tracks"}), 400
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status":"queued", "result":None}
    threading.Thread(target=build_mix, args=(job_id, socket_room or job_id, tracks), daemon=True).start()
    return jsonify({"job_id": job_id})

@app.get("/api/jobs/<job_id>")
def job_status(job_id):
    j = JOBS.get(job_id)
    if not j: return jsonify({"error":"not found"}), 404
    return jsonify(j)

@app.get("/api/mix/file/<mix_id>")
def get_mix(mix_id):
    path = os.path.join(MIXES, mix_id)
    if not os.path.exists(path): return jsonify({"error":"not found"}), 404
    return send_file(path, mimetype="audio/wav", as_attachment=True, download_name="mix.wav")

# socket join helper
@socketio.on("join")
def on_join(room):
    join_room(room)
    emit("mix_progress", {"percent": 0, "message": "Joined room"}, to=room)

# --- serve frontend static files ---
@app.route("/")
def serve_frontend():
    static_dir = os.path.join(BASE, "static")
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return send_file(index_file)
    return jsonify({"message": "MiniMixLab Flask Backend", "status": "running"})

@app.route("/<path:filename>")
def serve_static(filename):
    static_dir = os.path.join(BASE, "static")
    file_path = os.path.join(static_dir, filename)
    if os.path.exists(file_path):
        return send_file(file_path)
    # If file not found in static, return 404
    return jsonify({"error": "File not found"}), 404

@app.get("/healthz")
def health(): return "ok", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    socketio.run(app, host="0.0.0.0", port=port)