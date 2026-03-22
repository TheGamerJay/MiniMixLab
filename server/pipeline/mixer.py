"""
Mixer — combine instrumental + vocals into a final song.
Handles:
  • mono conversion & resampling
  • instrumental looping to match vocal length
  • per-call volume control (overrides config defaults)
  • peak normalisation
  • WAV export via soundfile
  • MP3 export via pydub (requires ffmpeg on PATH)
  • ID3 metadata tagging for MP3
"""
import os
from math import gcd

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from config import OUTPUT_SAMPLE_RATE, VOCAL_VOLUME, MUSIC_VOLUME


# ── Public API ────────────────────────────────────────────────────────────────

def mix(
    instrumental: np.ndarray,
    instr_sr: int,
    vocals: np.ndarray,
    vocal_sr: int,
    output_path: str,
    vocal_vol: float = None,
    music_vol: float = None,
    metadata: dict = None,
) -> str:
    """Mix instrumental + vocals, save, return actual output path."""
    vvol = vocal_vol if vocal_vol is not None else VOCAL_VOLUME
    mvol = music_vol if music_vol is not None else MUSIC_VOLUME

    instr = _prepare(instrumental, instr_sr)
    vox   = _prepare(vocals,       vocal_sr)

    # Loop instrumental to cover full vocal length
    if len(instr) < len(vox):
        repeats = int(np.ceil(len(vox) / len(instr)))
        instr = np.tile(instr, repeats)
    instr = instr[:len(vox)]

    mixed = _normalise(instr * mvol + vox * vvol)
    return _export(mixed, output_path, metadata)


def save_instrumental(audio: np.ndarray, sr: int, output_path: str, metadata: dict = None) -> str:
    """Prepare and save instrumental-only track. Returns actual output path."""
    return _export(_prepare(audio, sr), output_path, metadata)


# ── Export ────────────────────────────────────────────────────────────────────

def _export(audio: np.ndarray, path: str, metadata: dict = None) -> str:
    if path.endswith(".mp3"):
        return _save_mp3(audio, path, metadata)
    sf.write(path, audio, OUTPUT_SAMPLE_RATE, subtype="PCM_16")
    return path


def _save_mp3(audio: np.ndarray, mp3_path: str, metadata: dict = None) -> str:
    """Convert float32 audio → MP3 via pydub. Falls back to WAV if pydub/ffmpeg unavailable."""
    try:
        from pydub import AudioSegment

        tmp_wav = mp3_path.replace(".mp3", "_tmp.wav")
        sf.write(tmp_wav, audio, OUTPUT_SAMPLE_RATE, subtype="PCM_16")

        seg  = AudioSegment.from_wav(tmp_wav)
        tags = {}
        if metadata:
            tags = {
                "title":   metadata.get("title",  "Secret Helper Song"),
                "artist":  "Secret Helper",
                "genre":   metadata.get("genre",  ""),
                "comment": metadata.get("prompt", ""),
            }
        seg.export(mp3_path, format="mp3", bitrate="192k", tags=tags)
        os.remove(tmp_wav)
        return mp3_path

    except Exception as e:
        print(f"[mixer] MP3 export failed ({e}). Saving as WAV instead.")
        wav_path = mp3_path.replace(".mp3", ".wav")
        sf.write(wav_path, audio, OUTPUT_SAMPLE_RATE, subtype="PCM_16")
        return wav_path


# ── Audio helpers ─────────────────────────────────────────────────────────────

def _prepare(audio: np.ndarray, sr: int) -> np.ndarray:
    return _normalise(_resample(_to_mono(audio), sr, OUTPUT_SAMPLE_RATE))


def _to_mono(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return audio
    # (channels, samples) if first dim is small, else (samples, channels)
    return audio.mean(axis=0) if audio.shape[0] <= 8 else audio.mean(axis=-1)


def _resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr:
        return audio.astype(np.float32)
    g = gcd(orig_sr, target_sr)
    return resample_poly(audio, target_sr // g, orig_sr // g).astype(np.float32)


def _normalise(audio: np.ndarray, target: float = 0.95) -> np.ndarray:
    peak = np.max(np.abs(audio))
    return (audio / peak * target).astype(np.float32) if peak > 0 else audio.astype(np.float32)
