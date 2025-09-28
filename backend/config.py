from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = ROOT / "cache"
RENDERS = ROOT / "renders"
SEPARATIONS = ROOT / "separations"

for p in [DATA, CACHE, RENDERS, SEPARATIONS]:
    p.mkdir(exist_ok=True)

# Analysis
ANALYSIS_SR = 22050  # CPU-friendly analysis sample rate