"""
Vocal Generator — Suno Bark via HuggingFace Transformers.
Lyrics are split by section and rendered one chunk at a time
(Bark has a ~200-word token limit per call).

Expanded voice presets covering all 10 Bark EN speakers.
CPU-ready; set DEVICE = "cuda" in config.py for GPU.
"""
import re

import numpy as np
import torch

from config import DEVICE, BARK_MODEL

BARK_SAMPLE_RATE = 24000   # Bark always outputs at 24 kHz

# All 10 Bark EN speakers mapped to descriptive names.
# Bark has exactly 10 EN speakers (0–9); extra presets reuse the closest
# base speaker but apply stage-direction hints to shift the feel.
VOICE_PRESETS = {
    # ── Neutral ──────────────────────────────────────────────────────────────
    "neutral":              "v2/en_speaker_0",

    # ── Male styles ──────────────────────────────────────────────────────────
    "male":                 "v2/en_speaker_6",
    "male – deep":          "v2/en_speaker_1",
    "male – warm":          "v2/en_speaker_2",
    "male – bright":        "v2/en_speaker_3",
    "male – smooth":        "v2/en_speaker_4",
    "male – raw":           "v2/en_speaker_1",   # deep + no embellishment
    "male – raspy":         "v2/en_speaker_3",

    # ── Female styles ─────────────────────────────────────────────────────────
    "female":               "v2/en_speaker_9",
    "female – soft":        "v2/en_speaker_7",
    "female – strong":      "v2/en_speaker_8",
    "female – raw":         "v2/en_speaker_8",
    "female – breathy":     "v2/en_speaker_7",

    # ── Emotional styles ──────────────────────────────────────────────────────
    "sad":                  "v2/en_speaker_4",   # smooth male, subdued
    "sad – female":         "v2/en_speaker_7",   # soft female
    "painful":              "v2/en_speaker_0",   # neutral + [crying] hint
    "painful – female":     "v2/en_speaker_9",
    "vulnerable":           "v2/en_speaker_5",   # whispery + sighing
    "vulnerable – female":  "v2/en_speaker_7",
    "anguished":            "v2/en_speaker_2",   # warm male breaking down
    "anguished – female":   "v2/en_speaker_8",

    # ── Dark / Gothic ─────────────────────────────────────────────────────────
    "gothic":               "v2/en_speaker_1",   # deep male, no softening
    "gothic – female":      "v2/en_speaker_7",   # soft female, eerie
    "dark":                 "v2/en_speaker_1",
    "dark – female":        "v2/en_speaker_9",

    # ── Character styles ──────────────────────────────────────────────────────
    "whispery":             "v2/en_speaker_5",
    "powerful":             "v2/en_speaker_6",
    "spoken word":          "v2/en_speaker_6",   # narrative, less sung
    "choir":                "v2/en_speaker_9",
    "trap – ad libs":       "v2/en_speaker_2",
}

# Stage-direction hints injected per section to nudge Bark's rendering.
# Keys match VOICE_PRESETS keys; missing = no hint added.
_STYLE_HINTS = {
    "sad":                 "[sighing]",
    "sad – female":        "[sighing]",
    "painful":             "[crying]",
    "painful – female":    "[crying]",
    "vulnerable":          "[whispering]",
    "vulnerable – female": "[whispering]",
    "anguished":           "[gasps]",
    "anguished – female":  "[gasps]",
    "gothic":              "",
    "gothic – female":     "",
    "dark":                "",
    "dark – female":       "",
    "whispery":            "[whispering]",
    "spoken word":         "",
}

_processor = None
_model     = None


def load():
    global _processor, _model
    if _model is not None:
        return
    print(f"[vocals] Loading Bark ({BARK_MODEL}) on {DEVICE}…")
    from transformers import AutoProcessor, BarkModel

    _processor = AutoProcessor.from_pretrained(BARK_MODEL)
    _model = BarkModel.from_pretrained(
        BARK_MODEL,
        torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
    ).to(DEVICE)
    print("[vocals] Bark ready.")


def generate(lyrics: str, voice: str = "neutral") -> tuple:
    """
    Returns (audio_np, sample_rate).
    audio_np: mono float32.
    """
    load()
    preset   = VOICE_PRESETS.get(voice, VOICE_PRESETS["neutral"])
    sections = _split_lyrics(lyrics)
    chunks   = []

    for section in sections:
        if not section.strip():
            continue
        hint   = _STYLE_HINTS.get(voice, "")
        text   = _format_for_bark(section, hint)
        inputs = _processor(text, voice_preset=preset, return_tensors="pt")
        inputs = {k: v.to(DEVICE) for k, v in inputs.items()}

        with torch.no_grad():
            audio = _model.generate(**inputs)

        chunk = audio.cpu().float().numpy().squeeze()
        if chunk.ndim > 1:
            chunk = chunk[0]
        chunks.append(chunk)
        # Short silence gap between sections (0.35 s)
        chunks.append(np.zeros(int(BARK_SAMPLE_RATE * 0.35), dtype=np.float32))

    if not chunks:
        return np.zeros(BARK_SAMPLE_RATE, dtype=np.float32), BARK_SAMPLE_RATE

    return np.concatenate(chunks).astype(np.float32), BARK_SAMPLE_RATE


def _split_lyrics(lyrics: str) -> list:
    """Split only on section headers that occupy their own line: [Verse 1], [Coro], etc.
    Inline guides like [raspy] embedded mid-line are preserved for _format_for_bark to handle."""
    parts = re.split(r"(?m)^\[.*?\]\s*$", lyrics)
    return [p.strip() for p in parts if p.strip()]


def _format_for_bark(text: str, hint: str = "") -> str:
    """Prepare a lyrics section for Bark TTS.
    - Strip inline vocal guides [guide] — they're for display only; Bark stage direction
      comes from the hint parameter (_STYLE_HINTS).
    - Unwrap ad-lib parens (yeah) → yeah so Bark speaks them naturally.
    - Join lines with ♪ for more musical rendering.
    """
    # Remove inline guide tags like [raspy], [whisper], [falsetto]
    text = re.sub(r"\[[^\]]+\]", "", text)
    # Unwrap ad-lib parentheses: (yeah) → yeah
    text = re.sub(r"\(([^)]+)\)", r"\1", text)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    joined = " ♪ ".join(lines) + " ♪"
    return f"{hint} {joined}".strip() if hint else joined
