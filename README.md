# MiniMixLab 🎶

MiniMixLab is a lightweight, CPU-friendly remixing lab.  

---

## ✨ Features
- Upload up to **3 tracks**
- Auto-detect **sections** (Intro, Verse, Chorus, Bridge)
- **Drag & drop** into a bar-grid timeline
- **Mute/Solo** & audition slices without overlap
- Optional **per-stem placement** (vocals, drums, bass, other)
- Optional **key assist** (suggest semitone shifts towards project key)
- Export **full WAV mixdowns** (44.1 kHz, stereo, 16-bit)

---

## 🛠 Tech Stack
- **Backend**: FastAPI + Python (`librosa`, `soundfile`, `rubberband`, optional `demucs`)
- **Frontend**: React + Vite
- **Deployment**: Railway (single Dockerfile builds front + back)

---

## 🚀 Quick Start

### Clone
```bash
git clone https://github.com/TheGamerJay/MiniMixLab.git
cd MiniMixLab
