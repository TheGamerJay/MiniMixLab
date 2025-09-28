from __future__ import annotations
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, ORJSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from pathlib import Path
import aiofiles, hashlib, asyncio

from config import CACHE, DATA
from processor import analyze_audio, file_hash_bytes, file_hash
from renderer import ArrItem, render_mix

app = FastAPI(default_response_class=ORJSONResponse)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)
SEM = asyncio.Semaphore(3)  # analyze up to 3 at once

# ---------- models ----------
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

# ---------- helpers ----------
async def _save_upload(f: UploadFile) -> Path:
    # Read all bytes (fine for typical song sizes on dev)
    raw = await f.read()
    h = file_hash_bytes(raw)
    dst = CACHE / f"{h}{Path(f.filename).suffix or ''}"
    async with aiofiles.open(dst, "wb") as out:
        await out.write(raw)
    return dst

# ---------- routes ----------
@app.post("/analyze/batch", response_model=BatchResult)
async def analyze_batch(files: List[UploadFile] = File(...)):
    if not files or len(files) > 3:
        raise HTTPException(400, "Upload 1–3 files")
    results: List[TrackAnalysisModel] = []

    async def _one(f: UploadFile):
        async with SEM:
            p = await _save_upload(f)
            a = analyze_audio(p)
            h = file_hash(p)
            return TrackAnalysisModel(
                name=f.filename, bpm=a["bpm"], key=a["key"], duration=a["duration"], hash=h,
                sections=[SectionModel(**s) for s in a["sections"]]
            )

    out = await asyncio.gather(*(_one(f) for f in files))
    return BatchResult(tracks=out)

class AlignRequest(BaseModel):
    file_hash: str
    start: float
    end: float
    target_bpm: float
    source_bpm: float
    semitones: float = 0.0

from processor import slice_wav, rubberband_time_pitch

@app.post("/align/preview")
async def align_preview(req: AlignRequest):
    src = next(iter(CACHE.glob(f"{req.file_hash}.*")), None)
    if not src: raise HTTPException(404, "Source not found")
    tmp_in = DATA / f"slice_{req.file_hash}_{int(req.start*1000)}_{int(req.end*1000)}.wav"
    tmp_out = DATA / f"prev_{req.file_hash}_{int(req.start*1000)}_{int(req.end*1000)}.wav"
    slice_wav(src, tmp_in, req.start, req.end)
    ratio = req.target_bpm / max(1e-6, req.source_bpm)
    rubberband_time_pitch(tmp_in, tmp_out, bpm_ratio=ratio, semitones=req.semitones)
    tmp_in.unlink(missing_ok=True)
    return FileResponse(tmp_out, media_type="audio/wav")

class ArrangeItemModel(BaseModel):
    file_hash: str
    start: float
    end: float
    source_bpm: float
    semitones: float = 0.0
    at_bar: int
    loop_times: int = 1         # NEW: Extend/loop this item

class ArrangeRequest(BaseModel):
    project_bpm: float
    crossfade_ms: int = 120
    bars: int | None = None
    master_fade_out_ms: int = 0  # NEW: master fade at end of mix
    items: List[ArrangeItemModel]

@app.post("/arrange/render")
async def arrange_render(req: ArrangeRequest):
    if not req.items:
        raise HTTPException(400, "No items to render")
    arr: List[ArrItem] = []
    for it in req.items:
        src = next(iter(CACHE.glob(f"{it.file_hash}.*")), None)
        if not src: raise HTTPException(404, f"Missing cached source {it.file_hash}")
        arr.append(ArrItem(
            file_hash=it.file_hash, src_path=src,
            start=it.start, end=it.end,
            source_bpm=it.source_bpm, semitones=it.semitones,
            at_bar=it.at_bar, loop_times=it.loop_times
        ))
    out = render_mix(
        req.project_bpm, arr,
        bars=req.bars,
        crossfade_ms=req.crossfade_ms,
        master_fade_out_ms=req.master_fade_out_ms
    )
    return FileResponse(out, media_type="audio/wav")

# ---------- serve frontend build if present ----------
FRONTEND = Path(__file__).resolve().parent.parent / "frontend_dist"
if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")

from fastapi.responses import FileResponse as FR
@app.get("/")
def index():
    f = FRONTEND / "index.html"
    if f.exists():
        return FR(f)
    return {"ok": True, "message": "Backend up. Build frontend to serve UI."}