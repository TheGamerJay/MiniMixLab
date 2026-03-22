"""
Music Generator — Meta MusicGen via HuggingFace Transformers.
Supports runtime model switching (small / medium / large).
CPU-ready; set DEVICE = "cuda" in config.py for ~10x speedup.
"""
import gc

import numpy as np
import torch

from config import DEVICE, MUSICGEN_MODEL

# Map UI size label → HuggingFace model ID
MUSICGEN_MODELS = {
    "small":  "facebook/musicgen-small",
    "medium": "facebook/musicgen-medium",
    "large":  "facebook/musicgen-large",
}

_processor         = None
_model             = None
_loaded_model_name = None


def load(model_size: str = None):
    """Load (or hot-swap) the MusicGen model. model_size: 'small'|'medium'|'large'."""
    global _processor, _model, _loaded_model_name

    if model_size in MUSICGEN_MODELS:
        model_name = MUSICGEN_MODELS[model_size]
    elif model_size and model_size.startswith("facebook/"):
        model_name = model_size
    else:
        model_name = MUSICGEN_MODEL

    if _model is not None and _loaded_model_name == model_name:
        return  # already loaded, nothing to do

    # Unload previous model to free memory before loading the new one
    if _model is not None:
        print(f"[music] Unloading {_loaded_model_name}…")
        del _model, _processor
        _model = _processor = None
        gc.collect()
        if DEVICE == "cuda":
            torch.cuda.empty_cache()

    print(f"[music] Loading MusicGen ({model_name}) on {DEVICE}…")
    from transformers import AutoProcessor, MusicgenForConditionalGeneration

    _processor = AutoProcessor.from_pretrained(model_name)
    _model = MusicgenForConditionalGeneration.from_pretrained(
        model_name,
        torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
    ).to(DEVICE)
    _loaded_model_name = model_name
    print(f"[music] MusicGen ready ({model_name}).")


def generate(prompt: str, duration: int = 30, model_size: str = None) -> tuple:
    """
    Returns (audio_np, sample_rate).
    audio_np: mono float32 in [-1, 1].
    """
    load(model_size)

    # 256 tokens ≈ 5 s → scale linearly
    max_tokens = max(64, int(256 * duration / 5))

    inputs = _processor(text=[prompt], padding=True, return_tensors="pt")
    inputs = {k: v.to(DEVICE) for k, v in inputs.items()}

    with torch.no_grad():
        audio_values = _model.generate(**inputs, max_new_tokens=max_tokens)

    # Shape: [batch, channels, samples] — take first item, first channel
    audio       = audio_values[0, 0].cpu().float().numpy()
    sample_rate = _model.config.audio_encoder.sampling_rate
    return audio, sample_rate
