import os, uuid, tempfile, subprocess, json
import numpy as np
import librosa
from flask import Flask, request, send_file, jsonify, send_from_directory
from flask_cors import CORS
from segmentation import segment_and_label, map_letters_to_music_labels

# ── OpenAI ───────────────────────────────────────────────────────────────────
try:
    from openai import OpenAI
    _openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    _openai_ok = bool(os.environ.get("OPENAI_API_KEY"))
    if not _openai_ok:
        print("[openai] No OPENAI_API_KEY — AI features will be unavailable")
except ImportError:
    _openai_client = None
    _openai_ok = False
    print("[openai] openai package not installed — run: pip install openai")

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# ── Genre knowledge (extracted from Mini AI Studios pipeline) ─────────────────

GENRE_STRUCTURES = {
    "hip-hop":     ["[Intro]","[Verse 1]","[Hook]","[Verse 2]","[Hook]","[Outro]"],
    "boom-bap":    ["[Intro]","[Verse 1]","[Hook]","[Verse 2]","[Hook]","[Outro]"],
    "trap":        ["[Intro]","[Verse 1]","[Hook]","[Verse 2]","[Hook]","[Bridge]","[Hook]","[Outro]"],
    "drill":       ["[Intro]","[Verse 1]","[Hook]","[Verse 2]","[Hook]","[Outro]"],
    "lo-fi":       ["[Intro]","[Verse 1]","[Hook]","[Verse 2]","[Hook]","[Outro]"],
    "pop":         ["[Intro]","[Verse 1]","[Pre-Chorus]","[Chorus]","[Verse 2]","[Pre-Chorus]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "indie":       ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "alternative": ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "rock":        ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Guitar Solo]","[Bridge]","[Chorus]","[Outro]"],
    "metal":       ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Guitar Solo]","[Bridge]","[Chorus]","[Outro]"],
    "punk":        ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "folk":        ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "country":     ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "disco":       ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "r&b":         ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "soul":        ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "funk":        ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "blues":       ["[Intro]","[Verse 1]","[Hook]","[Verse 2]","[Hook]","[Verse 3]","[Outro]"],
    "gospel":      ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "jazz":        ["[Intro]","[Verse 1]","[Hook]","[Verse 2]","[Solo]","[Hook]","[Outro]"],
    "electronic":  ["[Intro]","[Verse 1]","[Build-Up]","[Drop]","[Break]","[Build-Up]","[Drop]","[Outro]"],
    "house":       ["[Intro]","[Verse 1]","[Build-Up]","[Drop]","[Break]","[Build-Up]","[Drop]","[Outro]"],
    "techno":      ["[Intro]","[Build-Up]","[Drop]","[Break]","[Build-Up]","[Drop]","[Outro]"],
    "dubstep":     ["[Intro]","[Verse 1]","[Build-Up]","[Drop]","[Break]","[Build-Up]","[Drop]","[Outro]"],
    "drum & bass": ["[Intro]","[Verse 1]","[Build-Up]","[Drop]","[Break]","[Drop]","[Outro]"],
    "synthwave":   ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "ambient":     ["[Intro]","[Part 1]","[Part 2]","[Part 3]","[Outro]"],
    "bachata":     ["[Intro]","[Verso 1]","[Coro]","[Verso 2]","[Coro]","[Puente]","[Coro]","[Final]"],
    "salsa":       ["[Intro]","[Verso 1]","[Coro]","[Verso 2]","[Coro]","[Mambo]","[Coro]","[Final]"],
    "merengue":    ["[Intro]","[Verso 1]","[Coro]","[Verso 2]","[Coro]","[Puente]","[Coro]","[Final]"],
    "cumbia":      ["[Intro]","[Verso 1]","[Coro]","[Verso 2]","[Coro]","[Puente]","[Coro]","[Final]"],
    "reggaeton":   ["[Intro]","[Verso 1]","[Coro]","[Verso 2]","[Coro]","[Break]","[Coro]","[Final]"],
    "latin pop":   ["[Intro]","[Verso 1]","[Pre-Coro]","[Coro]","[Verso 2]","[Pre-Coro]","[Coro]","[Puente]","[Coro]","[Final]"],
    "bossa nova":  ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "reggae":      ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "dancehall":   ["[Intro]","[Verse 1]","[Hook]","[Verse 2]","[Hook]","[Outro]"],
    "afrobeats":   ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "k-pop":       ["[Intro]","[Verse 1]","[Pre-Chorus]","[Chorus]","[Verse 2]","[Pre-Chorus]","[Chorus]","[Bridge]","[Rap Break]","[Chorus]","[Outro]"],
    "classical":   ["[Intro]","[Part 1]","[Part 2]","[Part 3]","[Outro]"],
}
_DEFAULT_STRUCTURE = ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"]

GENRE_LANGUAGE = {
    "bachata": "Spanish", "salsa": "Spanish", "merengue": "Spanish",
    "cumbia": "Spanish", "reggaeton": "Spanish", "latin pop": "Spanish",
    "bossa nova": "Portuguese", "k-pop": "Korean",
}

BPM_DEFAULTS = {
    "boom-bap": 90, "trap": 145, "drill": 145, "lo-fi": 80,
    "reggaeton": 92, "salsa": 180, "bachata": 126, "merengue": 158,
    "cumbia": 100, "latin pop": 110, "pop": 120, "rock": 130,
    "indie": 120, "punk": 168, "metal": 155, "alternative": 125,
    "electronic": 128, "house": 128, "techno": 138, "dubstep": 140,
    "drum & bass": 174, "synthwave": 110, "ambient": 70,
    "r&b": 90, "soul": 85, "funk": 110, "blues": 75,
    "gospel": 90, "jazz": 100, "classical": 80, "reggae": 76,
    "dancehall": 90, "afrobeats": 102, "bossa nova": 128, "folk": 90,
    "country": 100, "k-pop": 120, "disco": 120, "hip-hop": 90,
}

BANNED_CLICHES = [
    "sun sets", "broken heart", "tears fall", "ghosts of memories",
    "empty inside", "without you", "pain remains", "my world is cold",
]


def _genre_structure_str(genre: str) -> str:
    struct = GENRE_STRUCTURES.get(genre.lower(), _DEFAULT_STRUCTURE)
    return " → ".join(struct)


def _lyrics_language(genre: str) -> str:
    return GENRE_LANGUAGE.get(genre.lower(), "English")


# ── Static data ───────────────────────────────────────────────────────────────
VOICE_OPTIONS = [
    "neutral",
    "male", "male – deep", "male – warm", "male – bright", "male – smooth",
    "male – raw", "male – raspy",
    "female", "female – soft", "female – strong", "female – raw", "female – breathy",
    "sad", "sad – female",
    "painful", "painful – female",
    "vulnerable", "vulnerable – female",
    "anguished", "anguished – female",
    "gothic", "gothic – female",
    "dark", "dark – female",
    "whispery", "powerful", "spoken word", "choir", "trap – ad libs",
]

GENRE_OPTIONS = [
    "auto",
    "hip-hop", "boom-bap", "trap", "drill", "lo-fi",
    "reggaeton", "salsa", "bachata", "merengue", "cumbia", "latin pop",
    "pop", "rock", "indie", "punk", "metal", "alternative",
    "electronic", "house", "techno", "dubstep", "drum & bass", "synthwave", "ambient",
    "r&b", "soul", "funk", "blues", "gospel",
    "jazz", "classical", "reggae", "dancehall", "afrobeats",
    "bossa nova", "folk", "country", "k-pop", "disco",
]

# ── App setup ─────────────────────────────────────────────────────────────────
NODE_ENV    = os.environ.get("NODE_ENV", "development")
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")

BASE  = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(BASE, "storage")
# Production (Docker): static/ is populated by the build stage
# Development: fall back to ../frontend_dist built by Vite
_static = os.path.join(BASE, "static")
_dist   = os.path.join(BASE, "..", "frontend_dist")
DIST    = _static if os.path.isdir(_static) else _dist
MIXES = os.path.join(BASE, "mixes")
os.makedirs(STORE, exist_ok=True)
os.makedirs(MIXES, exist_ok=True)

app = Flask(__name__)
CORS(app, origins=CORS_ORIGIN.split(",") if CORS_ORIGIN != "*" else "*", supports_credentials=True)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev_key")

upload_store = {}   # file_id -> metadata

# ── Helpers ───────────────────────────────────────────────────────────────────
def ffmpeg(*args):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"] + list(args)
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def analyze_track(filepath):
    try:
        y, sr = librosa.load(filepath, duration=30)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        chroma = librosa.feature.chroma_stft(y=y, sr=sr)
        key_idx = int(np.argmax(np.sum(chroma, axis=1)))
        keys = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
        return {"bpm": float(tempo), "key": keys[key_idx], "first_beat": 0.0}
    except Exception as e:
        print(f"[analyze] {e}")
        return {"bpm": 120.0, "key": "C", "first_beat": 0.0}

def segment_track(filepath):
    try:
        y, sr = librosa.load(filepath, sr=22050, mono=True)
        duration = librosa.get_duration(y=y, sr=sr)
        onsets = librosa.onset.onset_detect(y=y, sr=sr, units="time",
                                            pre_max=3, post_max=3, pre_avg=3, post_avg=3,
                                            delta=0.1, wait=1)
        boundaries = [0.0]
        for o in onsets:
            if o > boundaries[-1] + 15.0 and o < duration - 10:
                boundaries.append(float(o))
        if len(boundaries) > 8:
            boundaries = boundaries[:8]
        boundaries.append(duration if boundaries[-1] < duration - 5 else duration)
        boundaries[-1] = duration

        label_map = ["Intro","Verse 1","Chorus","Verse 2","Bridge","Chorus","Rap","Outro"]
        segments = []
        for i in range(len(boundaries) - 1):
            start, end = boundaries[i], boundaries[i + 1]
            seg_len = end - start
            ratio   = start / duration
            if i == 0:
                label = "Intro" if seg_len < 25 else "Verse 1"
            elif i == len(boundaries) - 2:
                label = "Outro"
            elif ratio < 0.3:
                label = "Verse 1"
            elif ratio < 0.6:
                label = "Chorus" if i % 2 == 1 else "Verse 2"
            elif ratio < 0.8:
                used = {s["label"] for s in segments}
                label = "Bridge" if "Bridge" not in used and seg_len < 30 else \
                        "Rap"    if "Rap"    not in used and seg_len > 20 else "Chorus"
            else:
                label = "Outro" if seg_len < 30 else "Chorus"
            segments.append({"start": float(start), "end": float(end),
                              "label": label, "confidence": 0.8})
        return segments
    except Exception as e:
        print(f"[segment] {e}")
        return []

def _openai_chat(system: str, user: str, json_mode: bool = False) -> str:
    """Call OpenAI chat completion. Returns the assistant message string."""
    kwargs = dict(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=0.85,
        max_tokens=1800,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = _openai_client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content.strip()

# ── Audio endpoints ───────────────────────────────────────────────────────────

@app.route("/api/upload", methods=["POST"])
def upload():
    try:
        file = request.files.get("file")
        if not file:
            return jsonify({"error": "No file"}), 400
        file_id = str(uuid.uuid4())
        ext     = os.path.splitext(file.filename)[1] or ".mp3"
        filepath = os.path.join(STORE, f"{file_id}{ext}")
        file.save(filepath)
        analysis = analyze_track(filepath)
        duration = librosa.get_duration(filename=filepath)
        meta = {"file_id": file_id, "duration": duration, "analysis": analysis}
        upload_store[file_id] = meta
        return jsonify(meta)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/segment")
def get_segments():
    try:
        file_id = request.args.get("file_id")
        if not file_id or file_id not in upload_store:
            return jsonify({"error": "File not found"}), 404
        for ext in [".mp3", ".wav", ".m4a", ".flac"]:
            filepath = os.path.join(STORE, f"{file_id}{ext}")
            if os.path.exists(filepath):
                break
        else:
            return jsonify({"error": "File not found on disk"}), 404
        segments = segment_track(filepath)
        return jsonify({"file_id": file_id, "segments": segments})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/preview")
def preview():
    try:
        file_id = request.args.get("file_id")
        start   = float(request.args.get("start", 0))
        end     = float(request.args.get("end", 30))
        if not file_id:
            return jsonify({"error": "Missing file_id"}), 400
        for ext in [".mp3", ".wav", ".m4a", ".flac"]:
            filepath = os.path.join(STORE, f"{file_id}{ext}")
            if os.path.exists(filepath):
                break
        else:
            return jsonify({"error": "File not found"}), 404
        preview_path = os.path.join(tempfile.gettempdir(),
                                    f"preview_{file_id}_{start}_{end}.mp3")
        ffmpeg("-i", filepath, "-ss", str(start), "-t", str(end - start),
               "-c:a", "mp3", "-y", preview_path)
        return send_file(preview_path, mimetype="audio/mpeg")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/auto_pitch", methods=["POST"])
def auto_pitch():
    data   = request.json or {}
    tracks = [{"file_id": fid, "semitones": 0} for fid in data.get("file_ids", [])]
    return jsonify({"target_key": data.get("project_key", "C"), "tracks": tracks})


# ── Metadata endpoints ────────────────────────────────────────────────────────

@app.route("/api/voices")
def get_voices():
    return jsonify({"voices": VOICE_OPTIONS})


@app.route("/api/genres")
def get_genres():
    return jsonify({"genres": GENRE_OPTIONS})


@app.route("/healthz")
def health_check():
    return jsonify({
        "status":  "healthy",
        "service": "Mini AI Studio",
        "openai":  _openai_ok,
        "model":   OPENAI_MODEL,
    })


# ── Shared AI rules (extracted from mini-architect-ai) ───────────────────────

GENRE_RULES = """GENRE SUPPORT RULES (MANDATORY):
1. Accept ANY genre or sub-genre including hybrids like "Trap-Bachata", "Cinematic Reggaetón", "Emo Pop Rap"
2. Treat genres as contextual profiles, not rigid rules. Never say a genre has only one "correct" structure.
3. For hybrid genres: offer options that (a) lean genre A, (b) lean genre B, (c) balance both
4. Use language like "often", "commonly", "one possible approach" — never enforce a single structure
5. Artist intent > Genre rules. Education > Enforcement. Flexibility > Rigidity"""

NOTATION_RULES = """NOTATION RULES (MANDATORY):
- Square Brackets [ ] = Structure + Performance Instructions (NOT sung): [Intro] [Verse 1] [whispered] [soft]
  Never edit, rename, or remove text inside [ ]
- Parentheses ( ) = Ad-libs / Background Vocals (SUNG/SPOKEN): (yeah) (uh) (mmh) (oh-oh)
  Never remove or rewrite parentheses content
- If you see tone words in parentheses like (whisper) or (soft), note: those should be [whispered]/[soft] instead"""


# ── Secret Writer (OpenAI) ────────────────────────────────────────────────────

SECRET_WRITER_SYSTEM = """You are "Secret Writer" — a professional songwriter, composer, producer, and vocal director inside Mini AI Studio.

MISSION: Deliver complete, release-ready songs in any genre.

CRITICAL RULE — SINGABILITY OVER POETRY:
Lyrics must be written to be SUNG, not read. Every line must feel natural when performed over a beat.
PRIORITIZE:
- Conversational, everyday language (write how people talk and feel)
- Repeated phrases and refrains (repetition = catchiness)
- Consistent syllable counts per line within each section
- Simple, emotional wording in choruses (hook must be dead simple)
- Short, punchy lines that breathe with the rhythm
AVOID:
- Overly abstract or literary imagery
- Long, uneven lines that fight the meter
- Dense metaphors that sound good on paper but can't be sung
Every chorus MUST feel simpler than the verses. If a chorus sounds like a poem, simplify it until it sounds like something you'd shout at a concert.

OUTPUT: Return ONLY valid JSON — no markdown fences, no extra keys.

JSON SCHEMA (match exactly):
{
  "assistant_message": "1-2 sentence response describing what you created",
  "song": {
    "title": "Song Title",
    "voice": "voice style from app (e.g. male – smooth, female – soft, neutral)",
    "genre": "detected or specified genre",
    "bpm": 95,
    "mood_tags": ["tag1", "tag2"],
    "sound_description": "Precise production notes: instrumentation, texture, mood, key instruments"
  },
  "lyrics": {
    "structure": ["Intro", "Verse 1", "Chorus", "Verse 2", "Bridge", "Chorus", "Outro"],
    "text": "Full lyrics with [Section Headers] on their own lines"
  },
  "production_notes": {
    "arrangement": "Arrangement guide: dynamics, build, drop, contrast",
    "mix_notes": "Mixing/mastering notes: vocal delivery, ad-libs, harmonies, BPM feel"
  }
}

ABSOLUTE RULES:
- Accept ANY genre including hybrids; treat genre as a profile not a rigid rule; artist intent > genre rules
- [ ] = structure/performance markers (not sung); ( ) = ad-libs/background vocals (sung)
- BANNED clichés (never use these or close variants): "sun sets", "broken heart", "tears fall", "ghosts of memories", "empty inside", "without you", "pain remains", "my world is cold"
- Specificity: at least 2 concrete objects + 2 actions + 1 sensory detail per verse
- Consistent POV and coherent emotional arc across all sections (setup → build → peak → release)
- Ad-libs inline in parentheses: (yeah), (uh), (ayy). Vocal guides in brackets: [raspy], [whisper], [falsetto]
- LANGUAGE: Use the language from "lyrics_language" in the user message. Spanish for reggaeton/bachata/salsa/merengue/cumbia/latin pop. Portuguese for bossa nova. Korean for k-pop.
- STRUCTURE: Use the section headers from "song_structure" in the user message, each on its own line
- If instrumental_only is true: set lyrics.text to "" and describe the arrangement instead
- Avoid real artist names unless user explicitly requests references

QUALITY GATE (self-check before responding):
- Structure matches the genre
- Lyrics are complete intro→outro with no placeholders
- Emotional arc progresses
- Prosody is natural (no awkward syllable jams)
- SINGABILITY CHECK: Read every chorus aloud — if it sounds like a poem, simplify it"""


@app.route("/api/secret-writer", methods=["POST"])
def secret_writer():
    if not _openai_ok:
        return jsonify({"error": "OPENAI_API_KEY not set"}), 503

    data         = request.json or {}
    user_message = data.get("user_message", "").strip()
    if not user_message:
        return jsonify({"error": "user_message is required"}), 400

    ui    = data.get("ui_settings", {})
    genre = ui.get("genre", "pop") or "pop"
    lang  = _lyrics_language(genre)
    struct = _genre_structure_str(genre)

    ctx = (
        f"Current settings: voice={ui.get('voice','')}, genre={genre}, "
        f"instrumental_only={ui.get('instrumental_only', False)}\n"
        f"lyrics_language: {lang}  ← ALL lyrics MUST be in {lang}\n"
        f"song_structure: {struct}  ← use EXACTLY these section headers"
    )
    if data.get("current_song"):
        song = data["current_song"]
        ctx += f"\nExisting lyrics snippet: {str(song.get('lyrics',''))[:300]}"

    try:
        raw = _openai_chat(SECRET_WRITER_SYSTEM, f"{ctx}\n\nUser request: {user_message}",
                           json_mode=True)
        result = json.loads(raw)
        return jsonify(result)
    except json.JSONDecodeError:
        return jsonify({"assistant_message": raw, "song": None, "lyrics": None}), 200
    except Exception as e:
        print(f"[secret-writer] {e}")
        return jsonify({"error": str(e)}), 500


# ── Lyrics generation (OpenAI) ────────────────────────────────────────────────

LYRICS_SYSTEM = """You are a professional songwriter inside Mini AI Studio.

SINGABILITY RULE: Lyrics must be written to be SUNG, not read. Short punchy lines, consistent syllable counts per section, simple emotional choruses — if a chorus sounds like a poem, simplify it.

RULES:
- Use EXACTLY the section headers from "song_structure" in the user message, each on its own line
- Write in the language from "lyrics_language" in the user message
- Specific imagery: at least 2 concrete objects + 1 sensory detail per verse
- NEVER use: "sun sets", "broken heart", "tears fall", "ghosts of memories", "empty inside", "without you", "pain remains", "my world is cold"
- Ad-libs inline: (yeah), (uh), (ayy). Vocal guides: [raspy], [whisper], [falsetto]
- Match the genre's cadence and rhyme scheme
- Return ONLY the lyrics — no commentary, no title, no explanations"""


@app.route("/api/lyrics", methods=["POST"])
def generate_lyrics():
    if not _openai_ok:
        return jsonify({"error": "OPENAI_API_KEY not set"}), 503

    data   = request.json or {}
    prompt = data.get("prompt", "").strip()
    genre  = data.get("genre", "pop")
    voice  = data.get("voice", "neutral")
    extra  = data.get("secret_writer_context", "")

    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    lang   = _lyrics_language(genre)
    struct = _genre_structure_str(genre)
    user_msg = (
        f"Genre: {genre}\nVoice style: {voice}\n"
        f"lyrics_language: {lang}  ← ALL lyrics MUST be in {lang}\n"
        f"song_structure: {struct}  ← use EXACTLY these section headers\n"
    )
    if extra:
        user_msg += f"Production context: {extra}\n"
    user_msg += f"Request: {prompt}"

    try:
        lyrics = _openai_chat(LYRICS_SYSTEM, user_msg)
        return jsonify({"lyrics": lyrics})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Song generation ────────────────────────────────────────────────────────────
# Music audio generation requires a music API (Suno, Udio, etc.).
# Set MUSIC_API_KEY + MUSIC_API_URL env vars and implement _call_music_api() below.
# Without it, /api/generate returns lyrics + metadata only (no audio file).

def _call_music_api(prompt: str, genre: str, duration: int, instrumental: bool) -> dict | None:
    """
    Connect your music generation API here.
    Should return {"audio_url": "...", "file_id": "..."} or None on failure.

    Supported providers (set env vars):
      MUSIC_PROVIDER=suno  → uses Suno API (MUSIC_API_KEY required)
      MUSIC_PROVIDER=udio  → uses Udio API (MUSIC_API_KEY required)
    """
    provider = os.environ.get("MUSIC_PROVIDER", "")
    api_key  = os.environ.get("MUSIC_API_KEY", "")
    api_url  = os.environ.get("MUSIC_API_URL", "")

    if not provider or not api_key:
        return None   # No music API configured

    # ── Add your provider integration here ──
    # Example Suno-style request:
    # import requests
    # r = requests.post(api_url, json={"prompt": prompt, "duration": duration, ...},
    #                   headers={"Authorization": f"Bearer {api_key}"})
    # return r.json()
    return None


@app.route("/api/generate", methods=["POST"])
def generate_song():
    """
    Generate a song using OpenAI (lyrics) + optional music API (audio).
    Always returns lyrics. Audio file_id is only set if a music API is configured.
    """
    if not _openai_ok:
        return jsonify({"error": "OPENAI_API_KEY not set"}), 503

    data              = request.json or {}
    prompt            = data.get("prompt", "").strip()
    lyrics_in         = data.get("lyrics", "").strip()
    voice             = data.get("voice", "neutral")
    genre             = data.get("genre", "hip-hop")
    model_size        = data.get("model_size", "medium")   # passed to music API if supported
    instrumental_only = data.get("instrumental_only", False)
    helper_ctx        = data.get("secret_writer", "").strip()
    duration          = int(data.get("duration", 30))

    if not prompt and not lyrics_in:
        return jsonify({"error": "Provide a prompt or lyrics"}), 400

    # ── Step 1: Lyrics ──────────────────────────────────────────────────────
    if lyrics_in:
        lyrics = lyrics_in
    elif instrumental_only:
        lyrics = ""
    else:
        user_msg = f"Genre: {genre}\nVoice style: {voice}\n"
        if helper_ctx:
            user_msg += f"Production context: {helper_ctx}\n"
        user_msg += f"Request: {prompt}"
        try:
            lyrics = _openai_chat(LYRICS_SYSTEM, user_msg)
        except Exception as e:
            return jsonify({"error": f"Lyrics generation failed: {e}"}), 500

    # ── Step 2: Music API (optional) ─────────────────────────────────────────
    music_prompt = f"{genre} instrumental, {prompt}"
    if helper_ctx:
        music_prompt += f", {helper_ctx}"

    music_result = _call_music_api(music_prompt, genre, duration, instrumental_only)

    file_id  = None
    segments = []

    if music_result and music_result.get("audio_url"):
        # Download audio and store locally
        import requests as req_lib
        r = req_lib.get(music_result["audio_url"], timeout=60)
        file_id  = str(uuid.uuid4())
        filepath = os.path.join(STORE, f"{file_id}.mp3")
        with open(filepath, "wb") as f:
            f.write(r.content)
        analysis = analyze_track(filepath)
        segments = segment_track(filepath)
        upload_store[file_id] = {
            "file_id":  file_id,
            "duration": duration,
            "analysis": analysis,
        }
        bpm = analysis.get("bpm", 120)
        key = analysis.get("key", "C")
    else:
        # No music API — return lyrics-only result with placeholder segments
        bpm = _genre_bpm(genre)
        key = "Am"
        segments = _placeholder_segments(duration)

    return jsonify({
        "status":   "ok",
        "file_id":  file_id,
        "lyrics":   lyrics,
        "genre":    genre,
        "voice":    voice,
        "bpm":      bpm,
        "key":      key,
        "duration": duration,
        "segments": segments,
        "has_audio": file_id is not None,
    })


def _genre_bpm(genre: str) -> int:
    return BPM_DEFAULTS.get(genre.lower(), 100)


def _placeholder_segments(duration: int) -> list:
    """Return standard song structure segments scaled to duration."""
    structure = [
        ("Intro",   0.00, 0.08),
        ("Verse 1", 0.08, 0.28),
        ("Pre-Chorus", 0.28, 0.38),
        ("Chorus",  0.38, 0.54),
        ("Verse 2", 0.54, 0.70),
        ("Bridge",  0.70, 0.82),
        ("Chorus",  0.82, 0.94),
        ("Outro",   0.94, 1.00),
    ]
    return [
        {"label": lbl, "start": round(s * duration, 1),
         "end": round(e * duration, 1), "confidence": 0.75}
        for lbl, s, e in structure
    ]


# ── Rhyme Finder ──────────────────────────────────────────────────────────────

@app.route("/api/rhyme", methods=["POST"])
def rhyme_finder():
    if not _openai_ok:
        return jsonify({"error": "OPENAI_API_KEY not set"}), 503
    data  = request.json or {}
    line  = data.get("line", "").strip()
    genre = data.get("genre", "pop")
    tone  = data.get("tone", "neutral")
    if not line:
        return jsonify({"error": "line is required"}), 400
    prompt = (
        f'You are a rhyme assistant for songwriters. Analyze the ending sound of this line and suggest rhymes.\n\n'
        f'Line: "{line}"\nGenre: {genre}\nTone: {tone}\n\n'
        f'{NOTATION_RULES}\n\n'
        'Provide exactly 3 categories: perfect, near, and slant rhymes. Each must have exactly 5 words or short phrases '
        'that fit the genre and tone. These are SUGGESTIONS ONLY.\n\n'
        'Respond in this exact JSON format:\n'
        '{"rhymes": {"perfect": ["w1","w2","w3","w4","w5"], "near": ["w1","w2","w3","w4","w5"], "slant": ["w1","w2","w3","w4","w5"]}}'
    )
    try:
        raw = _openai_chat("You are a rhyme assistant for songwriters.", prompt, json_mode=True)
        return jsonify(json.loads(raw))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Beat Directions ────────────────────────────────────────────────────────────

@app.route("/api/beat", methods=["POST"])
def beat_directions():
    if not _openai_ok:
        return jsonify({"error": "OPENAI_API_KEY not set"}), 503
    data          = request.json or {}
    genre         = data.get("genre", "pop")
    mood          = data.get("mood", "neutral")
    vocal_type    = data.get("vocal_type", "")
    delivery      = data.get("delivery_style", "")
    lyrics        = data.get("lyrics", "")
    refine        = data.get("refine", "")
    prompt = (
        f'You are a beat direction assistant for songwriters. Suggest beat directions (NOT audio generation).\n\n'
        f'{GENRE_RULES}\n\n'
        f'Genre: {genre}\nMood: {mood}\nVocal Type: {vocal_type or "Not specified"}\n'
        f'Delivery Style: {delivery or "Not specified"}\n'
        + (f'Refinement: {refine}\n' if refine else '')
        + (f'Lyrics context:\n{lyrics[:500]}\n' if lyrics else '')
        + '\nSTRICT RULES:\n- Return exactly 3 beat direction options\n- Each under 1000 characters\n'
        '- Never reference real artists or specific producers\n'
        '- Suggest instrumentation, tempo feel, rhythm patterns, energy level\n'
        '- These are DIRECTIONS ONLY — not audio generation\n\n'
        'Respond in this exact JSON format:\n'
        '{"options": [{"title": "Option A", "text": "..."}, {"title": "Option B", "text": "..."}, {"title": "Option C", "text": "..."}]}'
    )
    try:
        raw = _openai_chat("You are a beat direction assistant.", prompt, json_mode=True)
        return jsonify(json.loads(raw))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Structure Coach ────────────────────────────────────────────────────────────

@app.route("/api/coach", methods=["POST"])
def structure_coach():
    if not _openai_ok:
        return jsonify({"error": "OPENAI_API_KEY not set"}), 503
    data            = request.json or {}
    lyrics          = data.get("lyrics", "").strip()
    genre           = data.get("genre", "pop")
    selected_option = data.get("selected_option")
    if not lyrics:
        return jsonify({"error": "lyrics is required"}), 400

    if selected_option is not None:
        prompt = (
            f'You are reformatting a song based on the user\'s selected structural option.\n\n'
            f'{GENRE_RULES}\n\n{NOTATION_RULES}\n\n'
            'REFORMATTING RULES:\n- Copy lyrics VERBATIM (no word changes)\n- Only move sections as specified\n'
            '- Never merge verses or split lines\n- Preserve all original section names\n\n'
            f'Original Lyrics:\n{lyrics}\n\nSelected Structure: {selected_option}\nTarget Genre: {genre}\n\n'
            f'Output the reformatted song with clear section headers, then a brief teaching note explaining why this structure works for {genre}.'
        )
    else:
        prompt = (
            f'You are a music structure coach. Analyze these lyrics and provide structure rearrangement advice for {genre}.\n\n'
            f'{GENRE_RULES}\n\n{NOTATION_RULES}\n\n'
            'STRICT RULES:\n- NEVER write or rewrite any lyrics\n- ONLY suggest how to rearrange existing sections\n'
            '- Provide exactly 3 different structural options\n- Output must be human-readable, NOT JSON\n'
            '- Acknowledge ALL existing sections explicitly\n\n'
            f'Lyrics:\n{lyrics}\n\n'
            'OUTPUT FORMAT:\nExplanation\n• Why current structure differs from genre expectation\n• What this genre usually expects\n\n'
            'Option 1 – [title]\nSuggested Structure:\n• Section → Section\nWhy this works:\n• Reason\n\n'
            'Option 2 – [title]\nSuggested Structure:\n• Section → Section\nWhy this works:\n• Reason\n\n'
            'Option 3 – [title]\nSuggested Structure:\n• Section → Section\nWhy this works:\n• Reason'
        )
    try:
        raw = _openai_chat("You are a music structure coach.", prompt)
        return jsonify({"genre": genre, "output": raw})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Song Meaning ───────────────────────────────────────────────────────────────

@app.route("/api/meaning", methods=["POST"])
def song_meaning():
    if not _openai_ok:
        return jsonify({"error": "OPENAI_API_KEY not set"}), 503
    data   = request.json or {}
    lyrics = data.get("lyrics", "").strip()
    genre  = data.get("genre", "pop")
    if not lyrics:
        return jsonify({"error": "lyrics is required"}), 400
    prompt = (
        f'You are a song interpretation assistant. Explain the meaning, themes, emotions, and narrative of this song.\n\n'
        f'{GENRE_RULES}\n\n'
        'STRICT RULES:\n- Interpret the meaning only\n- Explain themes, emotions, and narrative\n'
        '- May explain ambiguity or multiple interpretations\n'
        '- NEVER critique quality or suggest improvements\n- NEVER rewrite or modify lyrics\n\n'
        f'Genre: {genre}\nLyrics:\n{lyrics}\n\n'
        'Provide a thoughtful interpretation that helps the artist understand what their song communicates.'
    )
    try:
        raw = _openai_chat("You are a song interpretation assistant.", prompt)
        return jsonify({"genre": genre, "output": raw})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Section Writer ─────────────────────────────────────────────────────────────

@app.route("/api/section-writer", methods=["POST"])
def section_writer():
    """Generate 3 options for a single stuck section — never touches existing lyrics."""
    if not _openai_ok:
        return jsonify({"error": "OPENAI_API_KEY not set"}), 503
    data          = request.json or {}
    genre         = data.get("genre", "pop")
    language      = data.get("language", "English")
    mood          = data.get("mood", "neutral")
    stuck_section = data.get("stuck_section", "Verse 1")
    lyrics_so_far = data.get("lyrics_so_far", "")
    guidance      = data.get("guidance", "")
    vocal_type    = data.get("vocal_type", "")
    delivery      = data.get("delivery_style", "")
    refine        = data.get("refine", "")
    prompt = (
        f'You are a songwriting assistant helping with writer\'s block. Generate lyrics ONLY for the missing section.\n\n'
        f'{GENRE_RULES}\n\n{NOTATION_RULES}\n\n'
        f'Vocal Type: {vocal_type or "Not specified"}\nDelivery Style: {delivery or "Not specified"}\n'
        + (f'Refinement: {refine}\n' if refine else '')
        + f'\nSTRICT RULES:\n- NEVER rewrite or modify existing lyrics\n'
        f'- ONLY write the requested missing section: {stuck_section}\n'
        f'- Return exactly 3 different options\n- Match language: {language}, mood: {mood}\n\n'
        f'Genre: {genre}\n'
        + (f'Existing lyrics:\n{lyrics_so_far}\n' if lyrics_so_far else '')
        + (f'Additional guidance: {guidance}\n' if guidance else '')
        + '\nRespond in this exact JSON format:\n'
        '{"options": [{"title": "Option A", "text": "..."}, {"title": "Option B", "text": "..."}, {"title": "Option C", "text": "..."}]}'
    )
    try:
        raw = _openai_chat("You are a songwriting assistant.", prompt, json_mode=True)
        return jsonify({"stuck_section": stuck_section, "genre": genre, **json.loads(raw)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Static frontend serving ───────────────────────────────────────────────────

@app.route("/")
def serve_frontend():
    if os.path.exists(DIST):
        return send_from_directory(DIST, "index.html")
    return jsonify({"message": "Mini AI Studio API", "status": "running"})


@app.route("/<path:path>")
def serve_static(path):
    if os.path.exists(DIST):
        file_path = os.path.join(DIST, path)
        if os.path.exists(file_path):
            return send_from_directory(DIST, path)
        # SPA fallback — all unmatched routes serve index.html for React Router
        return send_from_directory(DIST, "index.html")
    return jsonify({"error": "Not found"}), 404


if __name__ == "__main__":
    print(f"Mini AI Studio — backend starting")
    print(f"OpenAI: {'✓ ready' if _openai_ok else '✗ OPENAI_API_KEY not set'}")
    print(f"Model:  {OPENAI_MODEL}")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=(NODE_ENV == "development"))
