import os, uuid, time, tempfile, subprocess, json, threading, queue
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

# ---- upload
@app.post("/api/upload")
def upload():
    f = request.files.get("file")
    if not f: return jsonify({"error":"file required"}), 400
    ext = os.path.splitext(f.filename)[1].lower() or ".wav"
    fid = str(uuid.uuid4()) + ext
    path = os.path.join(STORE, fid)
    f.save(path)
    pr = subprocess.run(
        ["ffprobe","-v","error","-show_entries","format=duration","-of","json",path],
        stdout=subprocess.PIPE
    )
    meta = json.loads(pr.stdout or b"{}")
    return jsonify({"file_id": fid, "duration": float(meta.get("format",{}).get("duration",0))})

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