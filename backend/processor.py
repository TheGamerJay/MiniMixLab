from __future__ import annotations
from pathlib import Path
import hashlib, subprocess
import numpy as np, librosa, soundfile as sf
from typing import Dict, Any
from config import ANALYSIS_SR

KEYS = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]

def file_hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]

def file_hash(path: Path) -> str:
    return file_hash_bytes(path.read_bytes())

def analyze_audio(path: Path) -> Dict[str, Any]:
    y, sr = librosa.load(path.as_posix(), sr=ANALYSIS_SR, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)

    # Tempo
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, trim=False)

    # Very light key estimate
    hpcp = librosa.feature.chroma_cqt(y=y, sr=sr)
    pitch_class = int(np.argmax(hpcp.sum(axis=1)))
    brightness = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    key = f"{KEYS[pitch_class]}{'m' if brightness < 2000 else 'M'}"

    # Coarse sections: 4 equal bins (Intro/Verse/Chorus/Bridge)
    labels = ["Intro","Verse","Chorus","Bridge"]
    edges = np.linspace(0, duration, num=5)
    sections = [{"label": labels[i], "start": float(edges[i]), "end": float(edges[i+1])} for i in range(4)]

    return {"bpm": float(tempo), "key": key, "duration": float(duration), "sections": sections}

def slice_wav(src: Path, out: Path, start: float, end: float):
    y, sr = librosa.load(src.as_posix(), sr=None, mono=False, offset=start, duration=max(0, end-start))
    if y.ndim == 1:
        y = y[:, None]
    sf.write(out.as_posix(), y, sr)

def rubberband_time_pitch(infile: Path, outfile: Path, bpm_ratio=1.0, semitones=0.0):
    # Try to use system rubberband CLI first, fallback to librosa if not available
    try:
        args = ["rubberband"]
        if abs(bpm_ratio - 1.0) > 1e-6:
            args += ["--tempo", f"{bpm_ratio*100:.6f}"]
        if abs(semitones) > 1e-3:
            args += ["--pitch", f"{semitones:.2f}"]
        args += [infile.as_posix(), outfile.as_posix()]
        subprocess.run(args, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback to librosa for basic time/pitch shifting
        print(f"Warning: rubberband not found, using librosa fallback (lower quality)")
        y, sr = librosa.load(infile.as_posix(), sr=None, mono=False)

        # Apply time stretching if needed
        if abs(bpm_ratio - 1.0) > 1e-6:
            y = librosa.effects.time_stretch(y, rate=1.0/bpm_ratio)

        # Apply pitch shifting if needed
        if abs(semitones) > 1e-3:
            y = librosa.effects.pitch_shift(y, sr=sr, n_steps=semitones)

        # Save the result
        if y.ndim == 1:
            y = y[:, None]
        sf.write(outfile.as_posix(), y, sr)