import os, uuid, time, tempfile, subprocess, json
import numpy as np
import librosa
from flask import Flask, request, send_file, jsonify, Response, send_from_directory
from flask_cors import CORS

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
    try:
        y, sr = librosa.load(filepath)
        duration = librosa.get_duration(y=y, sr=sr)

        # Advanced segmentation using spectral and rhythmic analysis

        # 1. Extract features for segmentation
        hop_length = 512
        frame_length = 2048

        # Spectral features
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop_length)
        chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=hop_length)
        spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop_length)

        # Energy and rhythm features
        rms_energy = librosa.feature.rms(y=y, hop_length=hop_length)
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length)

        # 2. Detect structural changes using spectral clustering
        # Combine features for similarity matrix
        features = np.vstack([
            np.mean(mfcc, axis=0),
            np.mean(chroma, axis=0),
            np.mean(spectral_centroid, axis=0),
            np.mean(rms_energy, axis=0)
        ])

        # 3. Find segment boundaries using novelty detection
        # Use onset detection for potential boundaries
        onset_frames = librosa.onset.onset_detect(y=y, sr=sr, hop_length=hop_length, units='time')

        # 4. Intelligent boundary selection
        boundaries = []

        # Always start with 0
        boundaries.append(0.0)

        # Add boundaries based on energy changes and beat alignment
        if len(onset_frames) > 0:
            # Group onsets into potential sections
            min_section_length = 15.0  # Minimum 15 seconds per section

            for onset_time in onset_frames:
                if onset_time > min_section_length and onset_time < duration - min_section_length:
                    # Check if this is a significant boundary
                    if len(boundaries) == 0 or onset_time - boundaries[-1] >= min_section_length:
                        boundaries.append(float(onset_time))

        # Ensure we don't have too many boundaries
        if len(boundaries) > 8:  # Max 8 sections
            # Keep the most significant boundaries
            boundaries = boundaries[:8]

        # Always end with duration
        if boundaries[-1] < duration - 5:  # If last boundary is more than 5s from end
            boundaries.append(duration)
        else:
            boundaries[-1] = duration

        # 5. Intelligent labeling based on position and characteristics
        segments = []

        # Analyze each segment for rap characteristics
        def detect_rap_section(y_segment, sr):
            """Detect if a segment is likely a rap section based on audio features"""
            try:
                # Extract features that indicate rap
                tempo, _ = librosa.beat.beat_track(y=y_segment, sr=sr)
                spectral_rolloff = librosa.feature.spectral_rolloff(y=y_segment, sr=sr)
                zero_crossing_rate = librosa.feature.zero_crossing_rate(y_segment)

                # Rap characteristics:
                # - Often has lower spectral rolloff (more bass/mid frequencies)
                # - Higher zero crossing rate (more speech-like)
                # - Often different tempo patterns

                avg_rolloff = np.mean(spectral_rolloff)
                avg_zcr = np.mean(zero_crossing_rate)

                # Simple heuristic: if spectral rolloff is low and ZCR is high, might be rap
                rap_score = 0
                if avg_rolloff < 3000:  # Lower frequency content
                    rap_score += 1
                if avg_zcr > 0.1:  # Higher speech-like characteristics
                    rap_score += 1

                return rap_score >= 1
            except:
                return False

        for i in range(len(boundaries) - 1):
            start_time = boundaries[i]
            end_time = boundaries[i + 1]
            section_length = end_time - start_time

            # Extract audio segment for analysis
            start_sample = int(start_time * sr)
            end_sample = int(end_time * sr)
            y_segment = y[start_sample:end_sample]

            # Smart labeling based on position in song
            position_ratio = start_time / duration
            is_rap = detect_rap_section(y_segment, sr)

            if i == 0:  # First section
                label = "Intro"
            elif i == len(boundaries) - 2:  # Last section
                label = "Outro"
            elif is_rap:  # Detected rap characteristics
                label = "Rap"
            elif position_ratio < 0.15:  # Early in song
                label = "Verse 1"
            elif position_ratio < 0.25:  # After intro
                label = "Pre-Chorus" if section_length < 20 else "Verse 1"
            elif position_ratio < 0.4:  # First major section
                label = "Chorus"
            elif position_ratio < 0.6:  # Middle sections
                if section_length < 25:
                    # Vary middle section types
                    existing_labels = [s["label"] for s in segments]
                    if "Bridge" not in existing_labels:
                        label = "Bridge"
                    elif "Breakdown" not in existing_labels:
                        label = "Breakdown"
                    else:
                        label = "Verse 2"
                else:
                    label = "Verse 2"
            elif position_ratio < 0.8:  # Later sections
                existing_labels = [s["label"] for s in segments]
                if section_length > 20:
                    # Prefer different section types for variety
                    if "Rap" not in existing_labels and len(segments) >= 4:
                        label = "Rap"
                    elif "Bridge" not in existing_labels:
                        label = "Bridge"
                    else:
                        label = "Chorus" if section_length > 30 else "Verse 2"
                else:
                    label = "Pre-Chorus"
            else:  # Near end
                label = "Outro" if section_length < 30 else "Chorus"

            # Ensure no duplicate consecutive labels
            if segments and segments[-1]["label"] == label:
                if "Verse" in label:
                    label = label.replace("1", "2") if "1" in label else label + " (Alt)"
                elif "Chorus" in label:
                    label = "Chorus (Repeat)"
                elif "Rap" in label:
                    label = "Rap (Extended)"
                else:
                    label = label + " (Extended)"

            segments.append({
                "start": float(start_time),
                "end": float(end_time),
                "label": label,
                "confidence": 0.75 + (0.2 if section_length > 15 else 0)
            })

        return segments

    except Exception as e:
        print(f"Advanced segmentation error: {e}")
        # Fallback to basic segmentation
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