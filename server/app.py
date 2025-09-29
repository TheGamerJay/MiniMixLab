import os, uuid, time, tempfile, subprocess, json
from flask import Flask, request, send_file, jsonify, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# --- config
BASE = os.path.dirname(__file__)
STORE = os.path.join(BASE, "storage")
MIXES = os.path.join(BASE, "mixes")
os.makedirs(STORE, exist_ok=True)
os.makedirs(MIXES, exist_ok=True)

app = Flask(__name__)
CORS(app, supports_credentials=True)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY","dev_key")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

def ffmpeg(*args):
    cmd = ["ffmpeg","-hide_banner","-loglevel","error"] + list(args)
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

# --- upload stem
@app.post("/api/upload")
def upload():
    f = request.files.get("file")
    if not f: return jsonify({"error":"file required"}), 400
    ext = os.path.splitext(f.filename)[1].lower() or ".wav"
    fid = str(uuid.uuid4()) + ext
    path = os.path.join(STORE, fid)
    f.save(path)
    # simple probe
    pr = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","json",path],
                        stdout=subprocess.PIPE)
    meta = json.loads(pr.stdout or b"{}")
    return jsonify({"file_id": fid, "duration": float(meta.get("format",{}).get("duration",0))})

# --- stream preview slice (memory-safe)
# GET /api/preview?file_id=..&start=..&end=..&speed=1.0
@app.get("/api/preview")
def preview():
    fid = request.args.get("file_id")
    start = float(request.args.get("start", 0))
    end = float(request.args.get("end", start+15))
    speed = float(request.args.get("speed", 1.0)) # can be used for BPM adjust
    src = os.path.join(STORE, fid)
    if not os.path.exists(src): return jsonify({"error":"not found"}), 404

    # Using a temp FIFO stream to avoid loading into RAM
    def generate():
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as tmp:
            # atempo supports 0.5..2.0; chain if needed
            atempo = []
            sp = speed
            # chain atempo in steps between 0.5..2.0 for stability
            while sp < 0.5 or sp > 2.0:
                step = 2.0 if sp > 2.0 else 0.5
                atempo.append(f"atempo={step}")
                sp = sp/step if sp > 2.0 else sp/0.5
            atempo.append(f"atempo={sp}")
            af = ",".join(atempo)

            # slice & speed adjust, encode mp3 @128k
            args = [
                "-ss", str(start),
                "-to", str(end),
                "-i", src,
                "-filter:a", af,
                "-map", "a:0",
                "-b:a", "128k",
                "-f", "mp3",
                "pipe:1"
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

# --- render full mix (server-side)
# body: { "tracks": [ { "file_id": "...", "offset": 0.0, "gain": -3.0, "speed": 1.0 } ] }
@app.post("/api/mix")
def mix():
    payload = request.get_json(force=True)
    tracks = payload.get("tracks", [])
    if not tracks: return jsonify({"error":"no tracks"}), 400

    out_id = f"{uuid.uuid4()}.wav"
    out_path = os.path.join(MIXES, out_id)

    # build ffmpeg inputs/filters
    inputs = []
    filters = []
    amix_inputs = []
    for i, t in enumerate(tracks):
        src = os.path.join(STORE, t["file_id"])
        if not os.path.exists(src): return jsonify({"error": f'missing {t["file_id"]}'}), 400
        # each as input
        inputs += ["-i", src]
        speed = float(t.get("speed",1.0))
        gain = float(t.get("gain",0.0))
        start = float(t.get("offset",0.0))
        # filtergraph label
        lbl_in = f"[{i}:a]"
        lbl = f"a{i}"
        atempo = []
        sp = speed
        while sp < 0.5 or sp > 2.0:
            step = 2.0 if sp > 2.0 else 0.5
            atempo.append(f"atempo={step}")
            sp = sp/step if sp > 2.0 else sp/0.5
        atempo.append(f"atempo={sp}")
        # apply offset by adding silent pad at start
        filters.append(f"{lbl_in} adelay={int(start*1000)}|{int(start*1000)}, " +
                       f"{','.join(atempo)}, volume={10**(gain/20):.6f} [{lbl}]")
        amix_inputs.append(f"[{lbl}]")

    # mixdown
    filter_complex = "; ".join(filters) + f"; {''.join(amix_inputs)} amix=inputs={len(tracks)}:normalize=0 [mix]"
    args = inputs + ["-filter_complex", filter_complex, "-map", "[mix]", "-ac", "2", out_path]
    r = ffmpeg(*args)
    if r.returncode != 0:
        return jsonify({"error":"ffmpeg_failed", "stderr": r.stderr.decode()}), 500

    return jsonify({"mix_id": out_id, "url": f"/api/mix/{out_id}"})

@app.get("/api/mix/<mix_id>")
def get_mix(mix_id):
    path = os.path.join(MIXES, mix_id)
    if not os.path.exists(path): return jsonify({"error":"not found"}), 404
    return send_file(path, mimetype="audio/wav", as_attachment=True, download_name="mix.wav")

# --- simple progress example via socket
@socketio.on("mix_progress")
def _mix_progress(msg):
    # you'd emit real progress from long running tasks
    for i in range(0,101,10):
        emit("mix_progress", {"percent": i})
        socketio.sleep(0.1)

@app.get("/healthz")
def health(): return "ok", 200

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
    return send_file(os.path.join(static_dir, filename))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    socketio.run(app, host="0.0.0.0", port=port)