import os, uuid, time, tempfile, subprocess, json
import numpy as np
import librosa
from flask import Flask, request, send_file, jsonify, Response, send_from_directory
from flask_cors import CORS
from segmentation import segment_and_label, map_letters_to_music_labels

# Environment configuration
NODE_ENV = os.environ.get("NODE_ENV", "development")
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")
API_URL = os.environ.get("API_URL", "/api")

BASE = os.path.dirname(__file__)
STORE = os.path.join(BASE, "storage")
MIXES = os.path.join(BASE, "mixes")
os.makedirs(STORE, exist_ok=True)
os.makedirs(MIXES, exist_ok=True)

app = Flask(__name__)

# Configure CORS based on environment
if CORS_ORIGIN == "*":
    CORS(app, supports_credentials=True)
else:
    CORS(app, origins=CORS_ORIGIN.split(","), supports_credentials=True)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev_key")

def ffmpeg(*args):
    cmd = ["ffmpeg","-hide_banner","-loglevel","error"] + list(args)
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def has_rubberband():
    try:
        out = subprocess.run(["ffmpeg", "-filters"], stdout=subprocess.PIPE, text=True).stdout
        return "rubberband" in out
    except Exception:
        return False

# Simple in-memory stores
upload_store = {}  # file_id -> metadata
project_store = {"bpm": 120, "key": "Am"}

def analyze_track(filepath):
    try:
        y, sr = librosa.load(filepath, duration=30)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        chroma = librosa.feature.chroma_stft(y=y, sr=sr)
        key_idx = np.argmax(np.sum(chroma, axis=1))
        keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        key = keys[key_idx]
        return {"bpm": float(tempo), "key": key, "first_beat": 0.0}
    except Exception as e:
        print(f"Analysis error: {e}")
        return {"bpm": 120.0, "key": "C", "first_beat": 0.0}

def segment_track(filepath):
    """
    Advanced segmentation using multi-scale novelty detection + spectral clustering
    """
    try:
        # Load audio
        y, sr = librosa.load(filepath, sr=22050, mono=True)

        # Get detected tempo for context
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)

        # Use the new segmentation algorithm
        segments = segment_and_label(y, sr, min_seg_s=7.0, target_clusters=(3, 6), tempo=tempo)

        # Map A/B/C labels to musical section names
        musical_segments = map_letters_to_music_labels(segments, detected_tempo=tempo)

        return musical_segments

    except Exception as e:
        print(f"Advanced segmentation failed: {e}, using fallback")
        # Fallback: basic segmentation
        try:
            duration = librosa.get_duration(filename=filepath)
            segment_duration = duration / 4
            segments = []
            labels = ["Intro", "Verse", "Chorus", "Outro"]

            for i, label in enumerate(labels):
                start_time = i * segment_duration
                end_time = min((i + 1) * segment_duration, duration)
                segments.append({
                    "start": start_time,
                    "end": end_time,
                    "label": label,
                    "confidence": 0.5
                })
            return segments
        except:
            return []

@app.route("/api/upload", methods=["POST"])
def upload():
    try:
        file = request.files.get("file")
        if not file:
            return jsonify({"error": "No file"}), 400

        file_id = str(uuid.uuid4())
        ext = os.path.splitext(file.filename)[1] or ".mp3"
        filepath = os.path.join(STORE, f"{file_id}{ext}")

        file.save(filepath)
        print(f"Saved file: {filepath}")

        # Analyze the track
        analysis = analyze_track(filepath)
        duration = librosa.get_duration(filename=filepath)

        metadata = {
            "file_id": file_id,
            "duration": duration,
            "analysis": analysis
        }

        upload_store[file_id] = metadata
        print(f"Upload successful: {metadata}")

        return jsonify(metadata)

    except Exception as e:
        print(f"Upload error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/segment")
def get_segments():
    try:
        file_id = request.args.get("file_id")
        if not file_id:
            return jsonify({"error": "Missing file_id"}), 400

        if file_id not in upload_store:
            return jsonify({"error": "File not found"}), 404

        # Find the file
        for ext in [".mp3", ".wav", ".m4a", ".flac"]:
            filepath = os.path.join(STORE, f"{file_id}{ext}")
            if os.path.exists(filepath):
                break
        else:
            return jsonify({"error": "File not found on disk"}), 404

        segments = segment_track(filepath)
        print(f"Generated {len(segments)} segments for {file_id}")

        return jsonify({
            "file_id": file_id,
            "segments": segments
        })

    except Exception as e:
        print(f"Segment error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/preview")
def preview():
    try:
        file_id = request.args.get("file_id")
        start = float(request.args.get("start", 0))
        end = float(request.args.get("end", 30))

        if not file_id:
            return jsonify({"error": "Missing file_id"}), 400

        # Find the file
        for ext in [".mp3", ".wav", ".m4a", ".flac"]:
            filepath = os.path.join(STORE, f"{file_id}{ext}")
            if os.path.exists(filepath):
                break
        else:
            return jsonify({"error": "File not found"}), 404

        # Generate preview
        preview_path = os.path.join(tempfile.gettempdir(), f"preview_{file_id}_{start}_{end}.mp3")

        ffmpeg(
            "-i", filepath,
            "-ss", str(start),
            "-t", str(end - start),
            "-c:a", "mp3",
            "-y", preview_path
        )

        return send_file(preview_path, mimetype="audio/mpeg")

    except Exception as e:
        print(f"Preview error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/project", methods=["GET", "POST"])
def project():
    global project_store
    if request.method == "GET":
        return jsonify(project_store)
    else:
        data = request.json or {}
        if "bpm" in data:
            project_store["bpm"] = data["bpm"]
        if "key" in data:
            project_store["key"] = data["key"]
        return jsonify(project_store)

@app.route("/api/sections", methods=["GET", "POST"])
def sections():
    # Simple sections endpoint - just return empty for now
    if request.method == "GET":
        return jsonify({"sections": []})
    else:
        # POST to save sections - just return success
        return jsonify({"status": "saved"})

@app.route("/api/auto_pitch", methods=["POST"])
def auto_pitch():
    # Simple auto-pitch endpoint
    data = request.json or {}
    file_ids = data.get("file_ids", [])
    project_key = data.get("project_key", "C")

    # Return zero pitch adjustment for all tracks
    tracks = [{"file_id": fid, "semitones": 0} for fid in file_ids]

    return jsonify({
        "target_key": project_key,
        "tracks": tracks
    })

@app.route("/healthz")
def health_check():
    return jsonify({"status": "healthy", "service": "MiniMixLab"})

# Serve static files (frontend)
@app.route("/")
def serve_frontend():
    static_dir = os.path.join(BASE, "static")
    if os.path.exists(static_dir):
        return send_from_directory(static_dir, "index.html")
    else:
        return jsonify({"message": "MiniMixLab API Server", "status": "running"})

@app.route("/<path:path>")
def serve_static_files(path):
    static_dir = os.path.join(BASE, "static")
    if os.path.exists(static_dir):
        return send_from_directory(static_dir, path)
    else:
        return jsonify({"error": "File not found"}), 404

if __name__ == "__main__":
    print("Starting MiniMixLab server...")
    print(f"Environment: {NODE_ENV}")
    print(f"Storage: {STORE}")
    print(f"Mixes: {MIXES}")
    print(f"CORS Origin: {CORS_ORIGIN}")
    print(f"API URL: {API_URL}")
    print(f"Rubber Band available: {has_rubberband()}")

    port = int(os.environ.get("PORT", 5000))
    debug_mode = NODE_ENV == "development"

    app.run(host="0.0.0.0", port=port, debug=debug_mode)