"""
Secret Helper — AI music co-writer backed by Ollama.
Handles: prompt building, AI call, JSON parsing/repair, cliché linting.
"""
import json
import logging
import os
import re

import requests

from config import OLLAMA_MODEL, OLLAMA_PLANNER_MODEL, OLLAMA_URL

# Redis cache — set REDIS_URL env var on Railway to enable
_REDIS_URL   = os.environ.get("REDIS_URL", "")
_CACHE_TTL   = 3600   # 1 hour


def _redis():
    """Return a Redis client, or None if REDIS_URL is not set."""
    if not _REDIS_URL:
        return None
    try:
        import redis
        return redis.from_url(_REDIS_URL, decode_responses=True, socket_timeout=2)
    except Exception:
        return None


def _cache_get(key: str):
    r = _redis()
    if not r:
        return None
    try:
        return r.get(key)
    except Exception:
        return None


def _cache_set(key: str, value: str):
    r = _redis()
    if not r:
        return
    try:
        r.setex(key, _CACHE_TTL, value)
    except Exception:
        pass

log = logging.getLogger(__name__)

# ── Planner prompt (deepseek-r1) ───────────────────────────────────────────────

PLANNER_SYSTEM = """You are a song planning assistant. Given the user's request and settings, write a SHORT creative brief for the songwriter.
Cover: core emotion/story, key imagery to avoid clichés, tone and vocal delivery style, any structural suggestions.
Be concise — 3 to 8 sentences. Plain text only. No JSON. No markdown. No lists."""


def _strip_think(text: str) -> str:
    """Remove <think>...</think> blocks output by deepseek-r1 before the response."""
    return re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()


# ── Banned phrases ─────────────────────────────────────────────────────────────

BANNED = [
    "sun sets", "broken heart", "tears fall", "ghosts of memories",
    "empty inside", "without you", "pain remains", "my world is cold",
]

# ── Genre → song structure ────────────────────────────────────────────────────

GENRE_STRUCTURES = {
    # Hip-Hop family
    "hip-hop":     ["[Intro]","[Verse 1]","[Hook]","[Verse 2]","[Hook]","[Outro]"],
    "boom-bap":    ["[Intro]","[Verse 1]","[Hook]","[Verse 2]","[Hook]","[Outro]"],
    "trap":        ["[Intro]","[Verse 1]","[Hook]","[Verse 2]","[Hook]","[Bridge]","[Hook]","[Outro]"],
    "drill":       ["[Intro]","[Verse 1]","[Hook]","[Verse 2]","[Hook]","[Outro]"],
    "lo-fi":       ["[Intro]","[Verse 1]","[Hook]","[Verse 2]","[Hook]","[Outro]"],
    # Pop / Rock family
    "pop":         ["[Intro]","[Verse 1]","[Pre-Chorus]","[Chorus]","[Verse 2]","[Pre-Chorus]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "indie":       ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "alternative": ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "rock":        ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Guitar Solo]","[Bridge]","[Chorus]","[Outro]"],
    "metal":       ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Guitar Solo]","[Bridge]","[Chorus]","[Outro]"],
    "punk":        ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "folk":        ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "country":     ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "disco":       ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    # Soul / R&B family
    "r&b":         ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "soul":        ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "funk":        ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "blues":       ["[Intro]","[Verse 1]","[Hook]","[Verse 2]","[Hook]","[Verse 3]","[Outro]"],
    "gospel":      ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "jazz":        ["[Intro]","[Verse 1]","[Hook]","[Verse 2]","[Solo]","[Hook]","[Outro]"],
    # Electronic family
    "electronic":  ["[Intro]","[Verse 1]","[Build-Up]","[Drop]","[Break]","[Build-Up]","[Drop]","[Outro]"],
    "house":       ["[Intro]","[Verse 1]","[Build-Up]","[Drop]","[Break]","[Build-Up]","[Drop]","[Outro]"],
    "techno":      ["[Intro]","[Build-Up]","[Drop]","[Break]","[Build-Up]","[Drop]","[Outro]"],
    "dubstep":     ["[Intro]","[Verse 1]","[Build-Up]","[Drop]","[Break]","[Build-Up]","[Drop]","[Outro]"],
    "drum & bass": ["[Intro]","[Verse 1]","[Build-Up]","[Drop]","[Break]","[Drop]","[Outro]"],
    "synthwave":   ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "ambient":     ["[Intro]","[Part 1]","[Part 2]","[Part 3]","[Outro]"],
    # Latin family (Spanish sections)
    "bachata":     ["[Intro]","[Verso 1]","[Coro]","[Verso 2]","[Coro]","[Puente]","[Coro]","[Final]"],
    "salsa":       ["[Intro]","[Verso 1]","[Coro]","[Verso 2]","[Coro]","[Mambo]","[Coro]","[Final]"],
    "merengue":    ["[Intro]","[Verso 1]","[Coro]","[Verso 2]","[Coro]","[Puente]","[Coro]","[Final]"],
    "cumbia":      ["[Intro]","[Verso 1]","[Coro]","[Verso 2]","[Coro]","[Puente]","[Coro]","[Final]"],
    "reggaeton":   ["[Intro]","[Verso 1]","[Coro]","[Verso 2]","[Coro]","[Break]","[Coro]","[Final]"],
    "latin pop":   ["[Intro]","[Verso 1]","[Pre-Coro]","[Coro]","[Verso 2]","[Pre-Coro]","[Coro]","[Puente]","[Coro]","[Final]"],
    "bossa nova":  ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    # World / Other
    "reggae":      ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "dancehall":   ["[Intro]","[Verse 1]","[Hook]","[Verse 2]","[Hook]","[Outro]"],
    "afrobeats":   ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"],
    "k-pop":       ["[Intro]","[Verse 1]","[Pre-Chorus]","[Chorus]","[Verse 2]","[Pre-Chorus]","[Chorus]","[Bridge]","[Rap Break]","[Chorus]","[Outro]"],
    "classical":   ["[Intro]","[Part 1]","[Part 2]","[Part 3]","[Outro]"],
}
_DEFAULT_STRUCTURE = ["[Intro]","[Verse 1]","[Chorus]","[Verse 2]","[Chorus]","[Bridge]","[Chorus]","[Outro]"]

# ── Genre → lyrics language ───────────────────────────────────────────────────

GENRE_LANGUAGE = {
    "bachata":    "Spanish",
    "salsa":      "Spanish",
    "merengue":   "Spanish",
    "cumbia":     "Spanish",
    "reggaeton":  "Spanish",
    "latin pop":  "Spanish",
    "bossa nova": "Portuguese",
    "k-pop":      "Korean",
}
# Genres not listed above → English by default.

# ── BPM defaults by genre ──────────────────────────────────────────────────────

BPM_DEFAULTS = {
    "boom-bap": 90,  "trap": 145,    "drill": 145,   "lo-fi": 80,
    "reggaeton": 92, "salsa": 180,   "bachata": 126, "merengue": 158,
    "cumbia": 100,   "latin pop": 110,"pop": 120,     "rock": 130,
    "indie": 120,    "punk": 168,    "metal": 155,   "alternative": 125,
    "electronic": 128,"house": 128,  "techno": 138,  "dubstep": 140,
    "drum & bass": 174,"synthwave": 110,"ambient": 70,
    "r&b": 90,       "soul": 85,     "funk": 110,    "blues": 75,
    "gospel": 90,    "jazz": 100,    "classical": 80,"reggae": 76,
    "dancehall": 90, "afrobeats": 102,"bossa nova": 128,"folk": 90,
    "country": 100,  "k-pop": 120,   "disco": 120,
}

# ── System prompts ─────────────────────────────────────────────────────────────

# Compact prompt for small models (≤3B params) — fewer rules = more reliable output
SYSTEM_PROMPT_SMALL = """You are a professional music co-writer. Output ONLY valid JSON — no markdown, no explanations.

JSON SCHEMA (copy this structure exactly):
{"assistant_message":"one sentence about the song","song":{"title":"Song Title Here","voice":"neutral","genre":"pop","bpm":120,"mood_tags":["sad","emotional"],"sound_description":"soft piano, slow tempo, melancholic strings"},"lyrics":{"structure":["Verse 1","Chorus","Verse 2","Chorus","Bridge","Chorus"],"text":"[Verse 1]\nLine one of verse here\nLine two of verse here\nLine three of verse here\nLine four of verse here\n\n[Chorus]\nLine one of chorus here\nLine two of chorus here\nLine three of chorus here\nLine four of chorus here\n\n[Verse 2]\nLine one of second verse\nLine two of second verse\nLine three of second verse\nLine four of second verse\n\n[Chorus]\nLine one of chorus here\nLine two of chorus here\nLine three of chorus here\nLine four of chorus here\n\n[Bridge]\nLine one of bridge here\nLine two of bridge here\nLine three of bridge here\nLine four of bridge here\n\n[Chorus]\nLine one of chorus here\nLine two of chorus here\nLine three of chorus here\nLine four of chorus here"},"production_notes":{"arrangement":"describe arrangement","mix_notes":"describe mix"},"need_clarification":false,"clarifying_question":""}

CRITICAL RULES:
1. LANGUAGE: If lyrics_language=Spanish → ALL lyrics in Spanish. Portuguese → Portuguese. Korean → Korean.
2. STRUCTURE: The "text" field MUST contain the section headers from song_structure (e.g. [Verse 1], [Chorus]) on their own lines, exactly as shown in the schema above. Replace each section with real lyrics — keep the \\n format.
3. LYRICS: Write real, emotional, specific lyrics. Minimum 4 lines per section. NO placeholder text like "Line one here".
4. JSON: Output ONLY the JSON object. Nothing before or after."""

SYSTEM_PROMPT = """You are "Secret Helper", a music co-writer inside a song generator app.
Your job: help the user create a complete song concept and lyrics that match their request and UI settings.

ABSOLUTE RULES:
- Output VALID JSON only. No markdown fences. No extra keys beyond the schema.
- If you cannot comply, output valid JSON with need_clarification=true and a clarifying_question.
- Respect UI settings (voice/genre/bpm/model_size/instrumental_only) unless user explicitly asks to change.
- Never write generic filler or clichés. Forbidden phrases (and close variants):
  "sun sets", "broken heart", "tears fall", "ghosts of memories",
  "empty inside", "without you", "pain remains", "my world is cold".
- Lyrics must include specificity: at least 2 concrete objects + 2 actions + 1 sensory detail per verse.
- Keep a consistent POV and coherent story arc across all sections.
- Hook must be strong, repeatable, emotionally direct. No corny lines.
- If instrumental_only is true: lyrics.text must be "" and assistant_message describes the arrangement.
- LANGUAGE RULE: Write lyrics in the language specified by "lyrics_language" in the user message.
  bachata/salsa/merengue/cumbia/reggaeton/latin pop → Spanish.
  bossa nova → Portuguese. k-pop → Korean. All others → English.
  Never ignore this rule even if the user's request is in English.

LYRIC FORMAT (MANDATORY):
- Use EXACTLY the section headers listed in "song_structure" in the user message.
- Each section header must be on its own line with nothing else on that line.
- Ad-libs go inline in parentheses: (yeah), (uh), (ayy), (let's go), (no more)
- Vocal performance guides go inline in brackets after a word: [raspy], [whisper], [falsetto], [spoken], [ad lib]
- Example format:
  [Intro]
  Standing at the edge [spoken]
  [Verse 1]
  I count the tiles on the kitchen floor (one, two, three)
  The coffee's cold, been sitting since you left [raspy]
  (yeah) Every shelf still holds the shape of you
  [Chorus]
  Numb after use, hollow as a drum (hollow, hollow)
  ...
- The lyrics.structure JSON field must list section names without brackets matching what you used in text.

QUALITY RULES by model_size:
- small:  shorter output, simpler rhyme, structure=[Verse 1,Chorus,Verse 2,Chorus], minimal notes.
- medium: full structure, polished, consistent theme, moderate detail.
- large:  artist-grade; stronger imagery; optional internal rhymes; tighter cadence; deep production notes.

OUTPUT JSON SHAPE (MUST MATCH EXACTLY — no extra keys, no markdown wrapper):
{"assistant_message":"string","song":{"title":"string","voice":"string","genre":"string","bpm":0,"mood_tags":["string"],"sound_description":"string"},"lyrics":{"structure":["Verse 1","Chorus","Verse 2","Chorus","Bridge","Chorus"],"text":"string"},"production_notes":{"arrangement":"string","mix_notes":"string"},"need_clarification":false,"clarifying_question":""}"""

# ── Safe fallback ──────────────────────────────────────────────────────────────

_FALLBACK: dict = {
    "assistant_message": "",
    "song": {
        "title": "", "voice": "neutral", "genre": "pop",
        "bpm": 100, "mood_tags": [], "sound_description": "",
    },
    "lyrics": {
        "structure": ["Verse 1", "Chorus", "Verse 2", "Chorus", "Bridge", "Chorus"],
        "text": "",
    },
    "production_notes": {"arrangement": "", "mix_notes": ""},
    "need_clarification": False,
    "clarifying_question": "",
}


# ── Public API ─────────────────────────────────────────────────────────────────

def generate(user_message: str, ui_settings: dict, current_song: dict = None) -> dict:
    """Main entry: plan (deepseek-r1) → write (qwen2.5) → parse → lint → return dict."""
    import hashlib
    size  = ui_settings.get("model_size", "medium")
    sys_p = SYSTEM_PROMPT_SMALL if size == "small" else SYSTEM_PROMPT

    # Top-level cache check (skips both planner + writer on hit)
    cache_key = "sh:" + hashlib.sha256(
        (str(ui_settings) + user_message + str(current_song)).encode()
    ).hexdigest()
    cached = _cache_get(cache_key)
    if cached:
        log.info("[helper] Redis cache hit")
        try:
            return _normalize(json.loads(cached))
        except Exception:
            pass

    # Stage 1 — deepseek-r1: plan / creative brief
    brief = _plan(user_message, ui_settings)
    log.debug("[helper] brief: %s", brief[:200] if brief else "(skipped)")

    # Stage 2 — qwen2.5: write lyrics
    user_msg = _user_message(user_message, ui_settings, current_song, brief=brief)
    raw      = _call_ollama(user_msg, system=sys_p)
    log.debug("[helper] raw: %.500s", raw)

    _cache_set(cache_key, raw)

    parsed = _parse(raw)
    if not parsed["need_clarification"] and not ui_settings.get("instrumental_only"):
        parsed = _lint(parsed)
    return parsed


# ── Prompt builders ────────────────────────────────────────────────────────────

def _user_message(msg: str, ui: dict, current: dict, brief: str = "") -> str:
    voice = ui.get("voice") or "auto"
    genre = ui.get("genre") or "auto"
    bpm   = ui.get("bpm")   or "auto"
    size  = ui.get("model_size", "medium")
    instr = str(ui.get("instrumental_only", False)).lower()
    lang      = GENRE_LANGUAGE.get(str(genre).lower(), "English")
    structure = GENRE_STRUCTURES.get(str(genre).lower(), _DEFAULT_STRUCTURE)

    # Also detect language from message text (covers when genre dropdown is "auto")
    if lang == "English":
        msg_lower = msg.lower()
        for kw, detected_lang in [
            ("bachata", "Spanish"), ("salsa", "Spanish"), ("merengue", "Spanish"),
            ("cumbia", "Spanish"), ("reggaeton", "Spanish"), ("latin pop", "Spanish"),
            ("bossa nova", "Portuguese"), ("k-pop", "Korean"),
        ]:
            if kw in msg_lower:
                lang = detected_lang
                if structure == _DEFAULT_STRUCTURE:
                    structure = GENRE_STRUCTURES.get(kw, _DEFAULT_STRUCTURE)
                break

    # For small model, trim to a shorter structure
    if size == "small":
        structure = [s for s in structure if s not in ("[Pre-Chorus]","[Pre-Coro]","[Guitar Solo]","[Rap Break]","[Solo]","[Part 3]")][:6]

    lines = [
        f"User request: {msg}",
        "",
        "UI settings:",
        f"- voice: {voice}",
        f"- genre: {genre}",
        f"- bpm: {bpm}",
        f"- model_size: {size}",
        f"- instrumental_only: {instr}",
        f"- lyrics_language: {lang}  ← MANDATORY — write ALL lyrics ONLY in {lang}. Not English unless {lang} is English.",
        f"- song_structure: {' → '.join(structure)}  ← use EXACTLY these section headers, each on its own line",
    ]
    if brief:
        lines += ["", f"Creative brief (planning stage): {brief}"]
    if current:
        lines += ["", f"Current song draft (JSON): {json.dumps(current)}"]
    lines += [
        "",
        "Instructions:",
        "- Revise only what the user requested; keep everything else coherent.",
        "- For 'regenerate hook/verse/sound': update only that section.",
        "- Output VALID JSON only. No markdown fences.",
    ]
    return "\n".join(lines)


# ── AI calls ───────────────────────────────────────────────────────────────────

def _call_ollama(prompt: str, system: str = None, model: str = None) -> str:
    r = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model":  model or OLLAMA_MODEL,
            "system": system or SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.72,
                "top_p": 0.9,
                "num_predict": 2500,
                "num_ctx": 4096,
            },
        },
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["response"].strip()


def _plan(user_message: str, ui_settings: dict) -> str:
    """Stage 1 — deepseek-r1 builds a creative brief for the writer."""
    try:
        genre = ui_settings.get("genre") or "auto"
        mood  = ui_settings.get("mood")  or "auto"
        voice = ui_settings.get("voice") or "auto"
        brief_prompt = (
            f"User request: {user_message}\n"
            f"Genre: {genre} | Voice: {voice} | Mood: {mood}\n\n"
            "Write a creative brief for the songwriter."
        )
        raw = _call_ollama(brief_prompt, system=PLANNER_SYSTEM,
                           model=OLLAMA_PLANNER_MODEL)
        return _strip_think(raw)
    except Exception as e:
        log.warning("[helper] Planner skipped (%s)", e)
        return ""


def _call_ai(prompt: str, system: str = None) -> str:
    """Try cache → Ollama."""
    import hashlib
    cache_key = "sh:" + hashlib.sha256((str(system) + prompt).encode()).hexdigest()

    cached = _cache_get(cache_key)
    if cached:
        log.info("[helper] Redis cache hit")
        return cached

    result = _call_ollama(prompt, system)
    _cache_set(cache_key, result)
    return result


# ── JSON parsing + repair ──────────────────────────────────────────────────────

def _close_truncated_json(raw: str) -> str:
    """Close a JSON string that was cut off before its closing brackets."""
    s = raw.rstrip()
    if not s:
        return s
    # Walk through to track open strings and brackets
    in_string = False
    escape    = False
    stack     = []   # track open { and [
    for ch in s:
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
        elif not in_string:
            if ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                if stack:
                    stack.pop()
    if in_string:
        s += '"'
    for opener in reversed(stack):
        s += "}" if opener == "{" else "]"
    return s


def _parse(raw: str) -> dict:
    # 1. Direct parse
    try:
        return _normalize(json.loads(raw))
    except Exception:
        pass

    # 2. Try to close truncated JSON then parse
    try:
        return _normalize(json.loads(_close_truncated_json(raw)))
    except Exception:
        pass

    # 3. Extract first {...} block and try closing it
    m = re.search(r"\{[\s\S]*", raw)
    if m:
        for candidate in (m.group(), _close_truncated_json(m.group())):
            try:
                return _normalize(json.loads(candidate))
            except Exception:
                pass

    # 4. Repair call
    try:
        repair = (
            "Return ONLY valid JSON matching the schema. "
            f"Here is the broken output to fix:\n{raw}\n\nFix it. Return ONLY corrected JSON."
        )
        return _normalize(json.loads(_call_ai(repair)))
    except Exception:
        pass

    # 5. Safe fallback
    fb = dict(_FALLBACK)
    fb["need_clarification"]  = True
    fb["clarifying_question"] = "I had trouble formatting my response. Could you rephrase your request?"
    return fb


_PLACEHOLDERS = {
    "string", "short description of song", "song title", "full lyrics here",
    "describe the sound/beat", "arrangement notes", "mix notes",
}

def _normalize(d: dict) -> dict:
    """Fill any missing keys with safe defaults."""
    song  = d.get("song", {})
    lyr   = d.get("lyrics", {})
    prod  = d.get("production_notes", {})
    genre = str(song.get("genre", "pop"))

    def _clean(val: str) -> str:
        """Return empty string if value is a schema placeholder."""
        v = str(val).strip()
        return "" if v.lower() in _PLACEHOLDERS else v

    return {
        "assistant_message": _clean(d.get("assistant_message", "")),
        "song": {
            "title":             _clean(song.get("title", "")),
            "voice":             str(song.get("voice", "neutral")),
            "genre":             genre,
            "bpm":               int(song.get("bpm") or BPM_DEFAULTS.get(genre, 100)),
            "mood_tags":         list(song.get("mood_tags", [])),
            "sound_description": _clean(song.get("sound_description", "")),
        },
        "lyrics": {
            "structure": list(lyr.get("structure",
                              ["Verse 1", "Chorus", "Verse 2", "Chorus", "Bridge", "Chorus"])),
            "text": _clean(lyr.get("text", "")),
        },
        "production_notes": {
            "arrangement": _clean(prod.get("arrangement", "")),
            "mix_notes":   _clean(prod.get("mix_notes", "")),
        },
        "need_clarification": bool(d.get("need_clarification", False)),
        "clarifying_question": str(d.get("clarifying_question", "")),
    }


# ── Cliché lint + rewrite ──────────────────────────────────────────────────────

def _lint(parsed: dict) -> dict:
    text  = parsed["lyrics"]["text"].lower()
    found = [p for p in BANNED if p in text]
    if not found:
        return parsed
    log.info("[helper] clichés detected: %s — rewriting", found)
    fix = (
        f"Rewrite only the lines containing these clichés: {found}.\n"
        "Replace with concrete, specific imagery. Keep rhyme scheme and meaning.\n"
        "Return the COMPLETE updated JSON (same schema). No markdown.\n\n"
        f"Current JSON:\n{json.dumps(parsed)}"
    )
    fixed = _parse(_call_ai(fix))
    return fixed if fixed["lyrics"]["text"] else parsed
