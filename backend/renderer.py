from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple
import numpy as np, soundfile as sf, librosa
from processor import slice_wav, rubberband_time_pitch
from config import DATA, RENDERS

TARGET_SR, TARGET_CH = 44100, 2

@dataclass
class ArrItem:
    file_hash: str
    src_path: Path
    start: float
    end: float
    source_bpm: float
    semitones: float
    at_bar: int
    loop_times: int = 1          # NEW: Extend by looping this many times (>=1)

def _read_resample_stereo(path: Path, sr: int = TARGET_SR) -> np.ndarray:
    y, in_sr = sf.read(path.as_posix(), always_2d=True)
    if y.shape[1] == 1:
        y = np.repeat(y, 2, axis=1)
    if in_sr != sr:
        ch0 = librosa.resample(y[:,0], orig_sr=in_sr, target_sr=sr)
        ch1 = librosa.resample(y[:,1], orig_sr=in_sr, target_sr=sr)
        y = np.stack([ch0, ch1], axis=1)
    return y.astype(np.float32)

def _ensure_len(buf: np.ndarray, length: int) -> np.ndarray:
    if buf.shape[0] >= length: return buf
    extra = np.zeros((length - buf.shape[0], buf.shape[1]), dtype=buf.dtype)
    return np.concatenate([buf, extra], axis=0)

def _lin_fade(n: int):
    if n <= 0: return np.array([], dtype=np.float32), np.array([], dtype=np.float32)
    fi = np.linspace(0.0, 1.0, n, dtype=np.float32)
    fo = 1.0 - fi
    return fi, fo

def render_mix(
    project_bpm: float,
    items: List[ArrItem],
    bars: int | None = None,
    crossfade_ms: int = 120,
    master_fade_out_ms: int = 0,          # NEW: master fade out at end
) -> Path:
    bar_dur = 60.0 / project_bpm * 4.0  # 4/4
    rendered: List[Tuple[int, np.ndarray]] = []
    max_end = 0
    xfade_n = int(TARGET_SR * (crossfade_ms / 1000.0))

    for it in items:
        # 1) slice original
        tmp_in = DATA / f"arr_in_{it.file_hash}_{int(it.start*1000)}_{int(it.end*1000)}.wav"
        tmp_out = DATA / f"arr_out_{it.file_hash}_{int(it.start*1000)}_{int(it.end*1000)}.wav"
        slice_wav(it.src_path, tmp_in, it.start, it.end)

        # 2) time/pitch to project
        ratio = project_bpm / max(1e-6, it.source_bpm)
        rubberband_time_pitch(tmp_in, tmp_out, bpm_ratio=ratio, semitones=it.semitones)
        y = _read_resample_stereo(tmp_out)
        tmp_in.unlink(missing_ok=True); tmp_out.unlink(missing_ok=True)

        # 3) EXTEND: loop/duplicate end-to-end
        loops = max(1, int(it.loop_times or 1))
        if loops > 1 and y.shape[0] > 0:
            y = np.tile(y, (loops, 1))

        # 4) place on timeline
        start_sample = int(it.at_bar * bar_dur * TARGET_SR)
        rendered.append((start_sample, y))
        max_end = max(max_end, start_sample + y.shape[0])

    if bars is not None:
        max_end = max(max_end, int(bars * bar_dur * TARGET_SR))

    mix = np.zeros((max_end + 1, TARGET_CH), dtype=np.float32)

    # 5) sum with gentle crossfades at segment starts
    for start, y in rendered:
        end = start + y.shape[0]
        mix = _ensure_len(mix, end)
        seg = mix[start:end, :]
        xfade = min(xfade_n, y.shape[0])
        if xfade > 0:
            fi, fo = _lin_fade(xfade)
            for c in range(TARGET_CH):
                seg[:xfade, c] = seg[:xfade, c] * fo + y[:xfade, c] * fi
            seg[xfade:, :] += y[xfade:, :]
        else:
            seg[:, :] += y[:, :]
        mix[start:end, :] = seg

    # 6) MASTER FADE OUT (optional)
    if master_fade_out_ms > 0 and mix.shape[0] > 0:
        n = int(TARGET_SR * (master_fade_out_ms / 1000.0))
        n = min(n, mix.shape[0])
        if n > 0:
            fade = np.linspace(1.0, 0.0, n, dtype=np.float32)
            mix[-n:, 0] *= fade
            mix[-n:, 1] *= fade

    # 7) gentle normalization
    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    if peak > 0.99:
        mix *= (0.99 / peak)

    out = RENDERS / f"mix_{librosa.util.random.uuid()}.wav"
    sf.write(out.as_posix(), mix, TARGET_SR, subtype="PCM_16")
    return out