"""
Secret Helper — Central Configuration
========================================
CPU-ready, GPU-upgradeable.
Change DEVICE here to switch between runtimes — propagates everywhere.
"""
import os
import torch

# ──────────────────────────────────────────────────────────────────────────────
#  DEVICE  ←  change this one line to switch CPU / GPU / Apple Silicon
# ──────────────────────────────────────────────────────────────────────────────
DEVICE = "cpu"          # "cpu" | "cuda" | "mps"

# ── MusicGen model ────────────────────────────────────────────────────────────
# "facebook/musicgen-small"  (~300 MB  — fastest, CPU-friendly)
# "facebook/musicgen-medium" (~1.5 GB  — better quality)
# "facebook/musicgen-large"  (~3.3 GB  — best quality, recommend GPU)
MUSICGEN_MODEL = "facebook/musicgen-small"

# ── Bark vocal model ──────────────────────────────────────────────────────────
# "suno/bark-small"  (~900 MB  — CPU-friendly)
# "suno/bark"        (~1.8 GB  — richer voice, better on GPU)
BARK_MODEL = "suno/bark-small"

# ── Lyrics backend ────────────────────────────────────────────────────────────
# "template"       – instant, no model, always works
# "transformers"   – GPT-2, downloaded once (~500 MB)
# "ollama"         – best quality (requires Ollama installed locally)
LYRICS_BACKEND = "ollama"
LYRICS_MODEL   = "gpt2"

# ── Ollama (optional) ─────────────────────────────────────────────────────────
# Locally: http://localhost:11434  |  Railway: set OLLAMA_BASE_URL env var
OLLAMA_URL           = os.environ.get("OLLAMA_BASE_URL",      "http://localhost:11434")
OLLAMA_MODEL         = os.environ.get("OLLAMA_MODEL",         "qwen2.5:3b")      # writer
OLLAMA_PLANNER_MODEL = os.environ.get("OLLAMA_PLANNER_MODEL", "deepseek-r1:1.5b") # planner

# ── Audio output ──────────────────────────────────────────────────────────────
OUTPUT_SAMPLE_RATE = 44100   # Hz
VOCAL_VOLUME       = 0.75    # default vocal level  (overridable in UI)
MUSIC_VOLUME       = 0.60    # default music level  (overridable in UI)
DEFAULT_DURATION   = 30      # seconds

# ── History ───────────────────────────────────────────────────────────────────
HISTORY_FILE = "output/history.json"
MAX_HISTORY  = 100           # keep last N songs in history

# ── Sharing ───────────────────────────────────────────────────────────────────
# Set True to get a public Gradio URL (requires internet connection)
SHARE_LINK = False
