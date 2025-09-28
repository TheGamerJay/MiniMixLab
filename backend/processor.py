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
# ---------------- FULL-SONG SECTIONER (appended) ----------------
import numpy as np, librosa
from scipy.signal import find_peaks
from pathlib import Path
from typing import List
from config import ANALYSIS_SR
# Reuse KEYS, Section, Analysis from earlier in this file.

def _beatsync_features(y, sr):
    """Beat-sync chroma+mfcc(+delta) and return (Fsync, beat_times, tempo, beats)."""
    hop = 512
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop, trim=False)
    if len(beats) < 4:
        beats = np.arange(0, max(4, int(len(y)//hop)))
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    mfcc  = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    dmfcc = librosa.feature.delta(mfcc)
    F = np.vstack([chroma, mfcc, dmfcc])
    Fsync = librosa.util.sync(F, beats, aggregate=np.mean)
    times = librosa.frames_to_time(beats, sr=sr, hop_length=hop)
    return Fsync, times, float(tempo), beats

def _adjacent_novelty(F):
    """1 - cosine similarity between consecutive beat-synchronous frames, smoothed."""
    F = F + 1e-9
    F = F / (np.linalg.norm(F, axis=0, keepdims=True) + 1e-9)
    sim = np.sum(F[:,1:]*F[:,:-1], axis=0).clip(-1,1)
    nov = 1.0 - sim
    nov = np.r_[nov[0], nov]  # pad to frame length
    # simple median smoothing; window  1% of length, odd
    win = max(3, int(len(nov)*0.01))
    if win % 2 == 0: win += 1
    if len(nov) >= win:
        nov = librosa.decompose.nn_filter(nov[None,:], aggregate=np.median, metric='cosine', width=win)[0]
    return nov

def _choose_min_distance(tempo, n_beats):
    """Pick a min-peak distance so sections are ~816 bars depending on length."""
    bars_total = n_beats / 4.0
    target_sections = int(np.clip(bars_total/8.0, 5, 12))  # aim
    min_bars = max(6, int(bars_total/target_sections))     # at least 6 bars
    return int(min_bars*4)  # bars  beats

def analyze_audio(path: Path) -> Analysis:
    """Full-song structural segmentation with beat-synchronous novelty."""
    y, sr = librosa.load(path.as_posix(), sr=ANALYSIS_SR, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)

    # Tempo
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, trim=False)
    bpm = float(tempo)

    # Key (quick heuristic)
    hpcp = librosa.feature.chroma_cqt(y=y, sr=sr)
    pitch_class = int(np.argmax(hpcp.sum(axis=1)))
    brightness = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    suffix = "m" if brightness < 2000 else "M"
    key = f"{KEYS[pitch_class]}{suffix}"

    # If too few beats, fall back to 4 equal parts
    if len(beat_frames) < 16:
        cuts = np.linspace(0, duration, num=5)
        labels_cycle = ["Intro","Verse","Chorus","Bridge"]
        sections = [Section(label=labels_cycle[i%len(labels_cycle)],
                            start=float(cuts[i]), end=float(cuts[i+1]))
                    for i in range(len(cuts)-1)]
        return Analysis(bpm=bpm, key=key, sections=sections, duration=duration)

    # Beat-sync features & novelty
    Fsync, beat_times, tempo2, beats = _beatsync_features(y, sr)
    nov = _adjacent_novelty(Fsync)

    # Peak pick with distance ~ chosen bars and moderate prominence
    min_dist_beats = _choose_min_distance(bpm, len(beat_times))
    prom = float(np.percentile(nov, 60)) if len(nov) > 8 else 0.1
    peaks, _ = find_peaks(nov, distance=max(4, min_dist_beats), prominence=prom)

    # Build boundary indices (ensure 0 and end)
    b_inds = [0] + [int(p) for p in peaks if 0 < p < len(beat_times)-1] + [len(beat_times)-1]
    b_inds = sorted(set(b_inds))
    # prune boundaries closer than 4 beats
    pruned = [b_inds[0]]
    for idx in b_inds[1:]:
        if idx - pruned[-1] >= 4:
            pruned.append(idx)
    b_inds = pruned

    # Convert to time cuts; ensure full coverage [0, duration]
    cuts = [0.0] + [float(beat_times[i]) for i in b_inds[1:-1]] + [duration]
    cuts = np.clip(np.array(cuts), 0, duration)

    # Label sequence cycles to cover long songs
    labels_cycle = ["Intro","Verse","Chorus","Verse","Chorus","Bridge","Chorus","Outro"]
    sections: List[Section] = []
    for i in range(len(cuts)-1):
        s = float(cuts[i]); e = float(cuts[i+1])
        if e - s < 0.5:   # drop ultra-short fragments
            continue
        label = labels_cycle[i % len(labels_cycle)]
        sections.append(Section(label=label, start=s, end=e))

    return Analysis(bpm=bpm, key=key, sections=sections, duration=duration)
# --------------- END FULL-SONG SECTIONER ----------------
import shutil
from math import isclose

def rubberband_time_pitch(in_wav: Path, out_wav: Path, bpm_ratio: float = 1.0, semitones: float = 0.0):
    # Identity transform? just copy.
    if isclose(bpm_ratio, 1.0, rel_tol=1e-6, abs_tol=1e-6) and abs(semitones) < 1e-3:
        shutil.copyfile(in_wav, out_wav); return
    if shutil.which(RUBBERBAND_BIN) is None:
        raise RuntimeError(f"Rubber Band binary '{RUBBERBAND_BIN}' not found on PATH")
    args = [
        RUBBERBAND_BIN, "--no-transients", "--multi",
        *(["-t", f"{bpm_ratio:.6f}"] if not isclose(bpm_ratio, 1.0, rel_tol=1e-6, abs_tol=1e-6) else []),
        *(["-p", f"{semitones:.2f}"] if abs(semitones) > 1e-3 else []),
        in_wav.as_posix(), out_wav.as_posix()
    ]
    subprocess.run(args, check=True)

def slice_wav(src: Path, dest: Path, start: float, end: float):
    dur = max(0.05, end - start)  # at least 50ms
    y, sr = librosa.load(src.as_posix(), sr=None, mono=False, offset=max(0.0, start), duration=dur)
    sf.write(dest.as_posix(), y.T if y.ndim==1 else y.T, sr)
