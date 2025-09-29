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