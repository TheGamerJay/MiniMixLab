from __future__ import annotations

from fastapi import FastAPI, UploadFile, File, HTTPException, Path
from fastapi.responses import FileResponse, ORJSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from pathlib import Path as SysPath
import asyncio
import aiofiles
import traceback

from config import CACHE, DATA
from processor import (
    analyze_audio,           # must return dict OR an object with attrs (bpm/key/duration/sections)
    file_hash_bytes,
    file_hash,
    slice_wav,
    rubberband_time_pitch,
)
from renderer import ArrItem, render_mix

# ---------------- App & CORS ----------------
app = FastAPI(default_response_class=ORJSONResponse)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
SEM = asyncio.Semaphore(3)  # analyze up to 3 at once

# ---------------- Models ----------------
class SectionModel(BaseModel):
    label: str
    start: float
    end: float

class TrackAnalysisModel(BaseModel):
    name: str
    bpm: float
    key: str
    duration: float
    hash: str
    sections: List[SectionModel]

class BatchResult(BaseModel):
    tracks: List[TrackAnalysisModel]

class AlignRequest(BaseModel):
    file_hash: str
    start: float
    end: float
    target_bpm: float
    source_bpm: float
    semitones: float = 0.0

class ArrangeItemModel(BaseModel):
    file_hash: str
    start: float
    end: float
    source_bpm: float
    semitones: float = 0.0
    at_bar: int
    loop_times: int = 1  # extend/loop this item

class ArrangeRequest(BaseModel):
    project_bpm: float
    crossfade_ms: int = 120
    bars: int | None = None
    master_fade_out_ms: int = 0
    items: List[ArrangeItemModel]

# ---------------- Helpers ----------------
async def _save_upload(f: UploadFile) -> SysPath:
    """
    Save uploaded file bytes into CACHE using a content hash for dedupe.
    Returns the saved path.
    """
    raw = await f.read()
    h = file_hash_bytes(raw)
    dst = CACHE / f"{h}{SysPath(f.filename).suffix or ''}"
    async with aiofiles.open(dst, "wb") as out:
        await out.write(raw)
    return dst

def _analysis_to_dict(a) -> dict:
    """
    Normalize analyze_audio() result to dict with:
      { bpm, key, duration, sections: [{label,start,end}] }
    Works with either a dict or a simple object/dataclass.
    """
    if isinstance(a, dict):
        return a
    # dataclass / simple object fallback
    return {
        "bpm": float(getattr(a, "bpm")),
        "key": str(getattr(a, "key")),
        "duration": float(getattr(a, "duration")),
        "sections": [
            {
                "label": getattr(s, "label"),
                "start": float(getattr(s, "start")),
                "end": float(getattr(s, "end")),
            }
            for s in getattr(a, "sections")
        ],
    }

# ---------------- Routes ----------------
@app.post("/analyze/batch", response_model=BatchResult)
async def analyze_batch(files: List[UploadFile] = File(...)):
    if not files or len(files) > 3:
        raise HTTPException(400, "Upload 1–3 files")

    async def _one(f: UploadFile) -> TrackAnalysisModel:
        if not f.filename.lower().endswith((".wav", ".aiff", ".aif", ".mp3", ".flac")):
            raise HTTPException(400, f"Unsupported format: {f.filename}")
        async with SEM:
            p = await _save_upload(f)
            a_raw = analyze_audio(p)
            a = _analysis_to_dict(a_raw)
            h = file_hash(p)
            return TrackAnalysisModel(
                name=f.filename,
                bpm=a["bpm"],
                key=a["key"],
                duration=a["duration"],
                hash=h,
                sections=[SectionModel(**s) for s in a["sections"]],
            )

    results = await asyncio.gather(*(_one(f) for f in files))
    return BatchResult(tracks=results)

@app.post("/align/preview")
async def align_preview(req: AlignRequest):
    src = next(iter(CACHE.glob(f"{req.file_hash}.*")), None)
    if not src:
        raise HTTPException(404, "Source not found. Analyze first.")

    tmp_in = DATA / f"slice_{req.file_hash}_{int(req.start*1000)}_{int(req.end*1000)}.wav"
    tmp_out = DATA / f"prev_{req.file_hash}_{int(req.start*1000)}_{int(req.end*1000)}.wav"

    try:
        # Make the slice
        slice_wav(src, tmp_in, req.start, req.end)

        # Stretch / pitch
        ratio = req.target_bpm / max(1e-6, req.source_bpm)
        rubberband_time_pitch(tmp_in, tmp_out, bpm_ratio=ratio, semitones=req.semitones)

        return FileResponse(
            tmp_out,
            media_type="audio/wav",
            filename=f"preview_{req.file_hash}_{int(req.start*1000)}_{int(req.end*1000)}.wav",
        )
    except FileNotFoundError:
        raise HTTPException(500, "rubberband-cli not found in server image.")
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, detail=f"/align/preview failed: {e}")
    finally:
        tmp_in.unlink(missing_ok=True)

@app.post("/arrange/render")
async def arrange_render(req: ArrangeRequest):
    if not req.items:
        raise HTTPException(400, "No items to render")

    arr: List[ArrItem] = []
    for it in req.items:
        src = next(iter(CACHE.glob(f"{it.file_hash}.*")), None)
        if not src:
            raise HTTPException(404, f"Missing cached source {it.file_hash}")
        arr.append(
            ArrItem(
                file_hash=it.file_hash,
                src_path=src,
                start=it.start,
                end=it.end,
                source_bpm=it.source_bpm,
                semitones=it.semitones,
                at_bar=it.at_bar,
                loop_times=max(1, int(it.loop_times)),
            )
        )

    out_path = render_mix(
        project_bpm=req.project_bpm,
        items=arr,
        bars=req.bars,
        crossfade_ms=req.crossfade_ms,
        master_fade_out_ms=max(0, int(req.master_fade_out_ms)),
    )

    return FileResponse(
        out_path,
        media_type="audio/wav",
        filename="MiniMixLab_mix.wav",
    )

@app.delete("/cache/{file_hash}")
def delete_cache(file_hash: str = Path(..., min_length=8, max_length=64)):
    """
    Delete any cached source files for this hash, and clean temp preview/slice files.
    Returns {"deleted": True/False} indicating if any file was removed from CACHE.
    """
    deleted = False
    for p in CACHE.glob(f"{file_hash}.*"):
        try:
            p.unlink(missing_ok=True)
            deleted = True
        except Exception:
            pass
    for p in DATA.glob(f"slice_{file_hash}_*.wav"):
        p.unlink(missing_ok=True)
    for p in DATA.glob(f"prev_{file_hash}_*.wav"):
        p.unlink(missing_ok=True)
    return {"deleted": deleted}

# ---------------- Health & Frontend ----------------
@app.get("/healthz")
def healthz():
    return {"ok": True}

FRONTEND_BUILD = SysPath(__file__).resolve().parent.parent / "frontend_dist"
# Serve React build at root
app.mount("/", StaticFiles(directory=FRONTEND_BUILD, html=True), name="frontend")