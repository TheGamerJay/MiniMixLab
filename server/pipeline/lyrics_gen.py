"""
Lyrics Generator — three backends, falling back automatically:
  1. ollama       – best quality (needs Ollama installed locally)
  2. transformers – GPT-2, downloaded once (~500 MB)
  3. template     – instant, no model, always works as final fallback

Also provides check_rhymes() for the UI rhyme-analysis panel.
"""
import random
import re
import requests

from config import LYRICS_BACKEND, LYRICS_MODEL, OLLAMA_URL, OLLAMA_MODEL


# ── Public API ────────────────────────────────────────────────────────────────

def generate(theme: str, genre: str, mood: str) -> str:
    if LYRICS_BACKEND == "ollama":
        try:
            return _ollama(theme, genre, mood)
        except Exception as e:
            print(f"[lyrics] Ollama failed ({e}), falling back to transformers")

    if LYRICS_BACKEND in ("transformers", "ollama"):
        try:
            return _transformers(theme, genre, mood)
        except Exception as e:
            print(f"[lyrics] Transformers failed ({e}), using template")

    return _template(theme, genre, mood)


def check_rhymes(lyrics: str) -> list:
    """
    Analyse lyrics for rhymes.
    Returns list of (text, label) tuples for gr.HighlightedText.
    Labels: 'section' | 'rhymes' | 'no-rhyme'
    """
    result       = []
    recent_ends  = []  # last words of recent content lines (for rhyme comparison)

    for line in lyrics.split("\n"):
        stripped = line.strip()

        if not stripped:
            result.append(("\n", None))
            continue

        # Section headers like [Verse 1]
        if stripped.startswith("[") and stripped.endswith("]"):
            result.append((stripped + "\n", "section"))
            recent_ends = []  # reset per section
            continue

        words    = stripped.split()
        last_raw = words[-1] if words else ""
        last     = last_raw.lower().rstrip(".,!?;:'\"")

        # Check if last syllable matches any recent line (simple 2-char ending match)
        rhymes = False
        for prev in recent_ends[-4:]:
            if (last and prev and
                    len(last) >= 2 and len(prev) >= 2 and
                    last[-2:] == prev[-2:] and last != prev):
                rhymes = True
                break

        recent_ends.append(last)
        result.append((stripped + "\n", "rhymes" if rhymes else "no-rhyme"))

    return result


# ── Backend: Ollama ───────────────────────────────────────────────────────────

def _ollama(theme: str, genre: str, mood: str) -> str:
    resp = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": _ollama_prompt(theme, genre, mood), "stream": False},
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()["response"].strip()


def _ollama_prompt(theme: str, genre: str, mood: str) -> str:
    """Few-shot structured prompt for highest-quality lyrics."""
    return f"""You are a professional songwriter. Write complete song lyrics.

STYLE: {mood} {genre}
THEME: {theme}

RULES:
- Sections: [Verse 1], [Chorus], [Verse 2], [Chorus], [Bridge], [Chorus]
- Each section: exactly 4 lines
- Lines rhyme in ABAB or AABB pattern
- Keep lines short (6-10 words)
- Mood must feel like: {mood}
- Return ONLY the lyrics — no explanations, no title, no notes

EXAMPLE FORMAT:
[Verse 1]
Walking through the city rain
Neon lights reflecting low
Wondering if we'd meet again
Watching all the people go

[Chorus]
This is what I'm reaching for
Something I can't explain
Every time I close the door
I find myself back again

Now write the full song about "{theme}":"""


# ── Backend: Transformers ─────────────────────────────────────────────────────

_pipe = None


def _transformers(theme: str, genre: str, mood: str) -> str:
    global _pipe
    if _pipe is None:
        from transformers import pipeline
        import torch
        from config import DEVICE
        print(f"[lyrics] Loading {LYRICS_MODEL} on {DEVICE}…")
        _pipe = pipeline(
            "text-generation",
            model=LYRICS_MODEL,
            device=0 if DEVICE == "cuda" else -1,
            torch_dtype=torch.float32,
        )

    seed = (
        f"Song lyrics – genre: {genre}, mood: {mood}, theme: {theme}\n\n"
        "[Verse 1]\n"
    )
    result = _pipe(
        seed,
        max_new_tokens=280,
        temperature=0.92,
        do_sample=True,
        pad_token_id=50256,
    )
    raw = result[0]["generated_text"][len(seed):]
    return "[Verse 1]\n" + raw.strip()


# ── Backend: Template ─────────────────────────────────────────────────────────

WORD_BANKS = {
    "lo-fi":      ["midnight", "lamplight", "coffee", "vinyl", "quiet", "pages", "rain"],
    "pop":        ["heart", "light", "dance", "dream", "shine", "fire", "sky"],
    "rock":       ["road", "steel", "thunder", "fire", "storm", "fight", "speed"],
    "jazz":       ["smoke", "blue", "notes", "moon", "rain", "silk", "glass"],
    "classical":  ["grace", "silence", "echo", "breath", "time", "soul", "wave"],
    "hip-hop":    ["grind", "real", "streets", "hustle", "truth", "gold", "bars"],
    "electronic": ["pulse", "waves", "neon", "signal", "current", "code", "grid"],
    "r&b":        ["honey", "skin", "flame", "night", "close", "hold", "slow"],
    "country":    ["dust", "truck", "home", "field", "sky", "road", "creek"],
    "metal":      ["chaos", "iron", "rage", "void", "shadow", "blaze", "wraith"],
}

MOOD_PHRASES = {
    "chill":        ["take it slow", "breathe it in", "let it go", "find your peace"],
    "happy":        ["feel it now", "light up the sky", "you and I", "let's fly"],
    "sad":          ["can't hold on", "it all fades", "alone again", "I miss you"],
    "energetic":    ["push it hard", "burn it bright", "never stop", "feel alive"],
    "romantic":     ["hold me close", "just us two", "in your arms", "never let go"],
    "dark":         ["lost in shadows", "truth lies deep", "no way back", "the descent"],
    "motivational": ["rise up now", "break the chain", "reach the sky", "you can fly"],
}


def _template(theme: str, genre: str, mood: str) -> str:
    words   = WORD_BANKS.get(genre, WORD_BANKS["pop"])
    phrases = MOOD_PHRASES.get(mood, MOOD_PHRASES["chill"])
    topic   = " ".join(theme.split()[:3])

    def w(n=2):
        return ", ".join(random.sample(words, min(n, len(words))))

    def p():
        return random.choice(phrases)

    v1 = (
        f"{w(3)}, thinking of {topic}\n"
        f"{p()}, underneath the {random.choice(words)}\n"
        f"{w(2)}, chasing after {random.choice(words)}\n"
        f"{p()}, till the morning comes"
    )
    chorus = (
        f"Oh, {topic}, {p()}\n"
        f"Yeah, {random.choice(words)}, {p()}\n"
        f"{w(2)}, {p()}\n"
        f"Oh, {random.choice(words)}, {p()}"
    )
    v2 = (
        f"{w(3)}, lost in {topic}\n"
        f"{p()}, {random.choice(words)} in my mind\n"
        f"{w(2)}, {p()}\n"
        f"{random.choice(words)}, {p()}"
    )
    bridge = (
        f"Maybe it's the {random.choice(words)}\n"
        f"Maybe it's the {random.choice(words)}\n"
        f"{p()}\n"
        f"Yeah, {p()}"
    )

    return (
        f"[Verse 1]\n{v1}\n\n"
        f"[Chorus]\n{chorus}\n\n"
        f"[Verse 2]\n{v2}\n\n"
        f"[Chorus]\n{chorus}\n\n"
        f"[Bridge]\n{bridge}\n\n"
        f"[Chorus]\n{chorus}"
    )
