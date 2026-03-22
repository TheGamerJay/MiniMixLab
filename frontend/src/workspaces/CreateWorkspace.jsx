import React, { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Mic2, Upload, Wand2, Send, Music2, Loader2,
  X, ChevronRight, Sparkles, AlertCircle, Check,
  Plus, Trash2, FileAudio
} from "lucide-react";
import { useProject } from "../contexts/ProjectContext";
import axios from "axios";

// Fallback lists — overridden by /api/voices + /api/genres on mount
const DEFAULT_VOICES = [
  "neutral",
  "male", "male – deep", "male – warm", "male – bright", "male – smooth",
  "male – raw", "male – raspy",
  "female", "female – soft", "female – strong", "female – raw", "female – breathy",
  "sad", "sad – female", "painful", "vulnerable", "anguished",
  "gothic", "dark", "whispery", "powerful", "spoken word", "choir", "trap – ad libs",
];
const DEFAULT_GENRES = [
  "auto", "hip-hop", "trap", "drill", "boom-bap", "lo-fi",
  "reggaeton", "salsa", "bachata", "merengue", "latin pop",
  "pop", "rock", "indie", "alternative", "electronic", "house",
  "synthwave", "ambient", "r&b", "soul", "funk", "blues",
  "jazz", "afrobeats", "dancehall", "k-pop", "folk", "country",
];

const MODEL_SIZES = [
  { id: "small",  label: "Fast",    desc: "~30s  · Draft" },
  { id: "medium", label: "Balanced", desc: "~90s  · Good" },
  { id: "large",  label: "Premium", desc: "~3min · Best" },
];

export default function CreateWorkspace() {
  const navigate = useNavigate();
  const {
    activeProject, activeProjectId,
    createProject, updateProject,
    addAudioFile, updateAudioFile, removeAudioFile,
    sendToMixLab, toast,
  } = useProject();
  const fileRef = useRef();

  const proj = activeProject;

  // Form state — always mirrors project fields
  const [form, setForm] = useState(() => ({
    lyrics:           proj?.lyrics           ?? "",
    voice:            proj?.voice            ?? "neutral",
    genre:            proj?.genre            ?? "hip-hop",
    modelSize:        proj?.modelSize        ?? "medium",
    instrumentalOnly: proj?.instrumentalOnly ?? false,
    secretWriter:     proj?.secretWriter     ?? "",
    production_notes: proj?.production_notes ?? "",
  }));

  const [voices, setVoices]           = useState(DEFAULT_VOICES);
  const [genres, setGenres]           = useState(DEFAULT_GENRES);
  const [dragOver, setDragOver]       = useState(false);
  const [uploading, setUploading]     = useState(false);
  const [generating, setGenerating]   = useState(false);
  const [writingLyrics, setWriting]   = useState(false);

  // Secret Writer panel
  const [swPrompt,  setSwPrompt]  = useState("");
  const [swLoading, setSwLoading] = useState(false);
  const [swResult,  setSwResult]  = useState(null);

  // Sync form when active project switches
  useEffect(() => {
    if (!proj) return;
    setForm({
      lyrics:           proj.lyrics           ?? "",
      voice:            proj.voice            ?? "neutral",
      genre:            proj.genre            ?? "hip-hop",
      modelSize:        proj.modelSize        ?? "medium",
      instrumentalOnly: proj.instrumentalOnly ?? false,
      secretWriter:     proj.secretWriter     ?? "",
      production_notes: proj.production_notes ?? "",
    });
  }, [activeProjectId]);

  // Load dynamic lists from backend
  useEffect(() => {
    axios.get("/api/voices").then(r => { if (r.data.voices?.length) setVoices(r.data.voices); }).catch(() => {});
    axios.get("/api/genres").then(r => { if (r.data.genres?.length) setGenres(r.data.genres); }).catch(() => {});
  }, []);

  // ── Helpers ────────────────────────────────────────────────────────────────
  function ensureProject() {
    if (activeProjectId && activeProject) return activeProject;
    return createProject();
  }

  function patch(key, value) {
    setForm(prev => ({ ...prev, [key]: value }));
    if (activeProjectId) updateProject(activeProjectId, { [key]: value });
  }

  // ── Secret Writer ──────────────────────────────────────────────────────────
  async function callSecretWriter() {
    if (!swPrompt.trim()) { toast("Describe what you need", "error"); return; }
    setSwLoading(true);
    setSwResult(null);
    try {
      const res = await axios.post("/api/secret-writer", {
        user_message: swPrompt,
        ui_settings: { voice: form.voice, genre: form.genre, model_size: form.modelSize, instrumental_only: form.instrumentalOnly },
        current_song: form.lyrics ? { lyrics: form.lyrics } : null,
      });
      setSwResult(res.data);
    } catch (err) {
      toast(err.response?.data?.error ?? "Secret Writer unavailable — check OPENAI_API_KEY", "error");
    } finally {
      setSwLoading(false);
    }
  }

  function applySwResult(result) {
    const song = result?.song ?? {};
    const lyr  = result?.lyrics?.text ?? "";
    const prod = result?.production_notes?.arrangement
      ? `${result.production_notes.arrangement}\n${result.production_notes.mix_notes ?? ""}`.trim()
      : "";
    const tags = result?.song?.mood_tags ?? [];
    const updates = {};
    if (song.voice && voices.includes(song.voice)) updates.voice = song.voice;
    if (song.genre) updates.genre = song.genre;
    if (lyr)        updates.lyrics = lyr;
    if (prod)       updates.production_notes = prod;
    if (tags.length) updates.mood_tags = tags;

    const projId = ensureProject().id ?? activeProjectId;
    setForm(prev => ({ ...prev, ...updates }));
    updateProject(projId, updates);
    setSwResult(null);
    toast("Secret Writer suggestions applied", "success");
  }

  // ── Write lyrics with AI ───────────────────────────────────────────────────
  async function handleWriteLyrics() {
    const projId = ensureProject().id ?? activeProjectId;
    setWriting(true);
    try {
      const res = await axios.post("/api/lyrics", {
        prompt: form.secretWriter || `Write a ${form.genre} song`,
        genre:  form.genre,
        voice:  form.voice,
        secret_writer_context: form.secretWriter,
      });
      patch("lyrics", res.data.lyrics);
      updateProject(projId, { lyrics: res.data.lyrics });
      toast("Lyrics written by AI", "success");
    } catch (err) {
      toast(err.response?.data?.error ?? "Lyrics generation failed — check OPENAI_API_KEY", "error");
    } finally {
      setWriting(false);
    }
  }

  // ── Generate (AI + save track) ─────────────────────────────────────────────
  async function handleGenerate() {
    if (!form.lyrics.trim() && !form.instrumentalOnly && !form.secretWriter.trim()) {
      toast("Add lyrics, a Secret Writer prompt, or enable Instrumental Only", "error");
      return;
    }
    const p = ensureProject();
    const projId = p.id ?? activeProjectId;
    setGenerating(true);

    // Save current settings to project
    updateProject(projId, {
      lyrics:           form.lyrics,
      voice:            form.voice,
      genre:            form.genre,
      modelSize:        form.modelSize,
      instrumentalOnly: form.instrumentalOnly,
      secretWriter:     form.secretWriter,
      production_notes: form.production_notes,
    });

    try {
      const res = await axios.post("/api/generate", {
        prompt:            form.secretWriter || `${form.genre} song`,
        lyrics:            form.instrumentalOnly ? "" : form.lyrics,
        voice:             form.voice,
        genre:             form.genre,
        model_size:        form.modelSize,
        instrumental_only: form.instrumentalOnly,
        secret_writer:     form.secretWriter,
        duration:          30,
      });

      const d = res.data;
      if (d.lyrics && !form.lyrics) {
        setForm(prev => ({ ...prev, lyrics: d.lyrics }));
        updateProject(projId, { lyrics: d.lyrics });
      }

      addAudioFile(projId, {
        fileId:   d.file_id ?? null,
        name:     `${form.genre} — ${form.voice}${d.has_audio ? "" : " (Lyrics)"}`,
        bpm:      d.bpm ?? 120,
        key:      d.key ?? "C",
        duration: d.duration ?? 30,
        segments: d.segments ?? [],
      });

      toast(d.has_audio ? "Track generated and saved!" : "Lyrics generated — no audio yet (connect music API)", "success");
    } catch (err) {
      toast(err.response?.data?.error ?? "Generation failed", "error");
    } finally {
      setGenerating(false);
    }
  }

  // ── Upload audio ───────────────────────────────────────────────────────────
  async function handleUpload(file) {
    if (!file) return;
    if (!file.type.startsWith("audio/") && !file.name.match(/\.(mp3|wav|m4a|flac|ogg|aac)$/i)) {
      toast("Audio files only (MP3, WAV, FLAC, M4A)", "error");
      return;
    }
    const p = ensureProject();
    const projId = p.id ?? activeProjectId;
    setUploading(true);

    const fd = new FormData();
    fd.append("file", file);

    try {
      const res = await axios.post("/api/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      const d   = res.data;

      // Get segments too
      let segs = [];
      try {
        const sr = await axios.get(`/api/segment?file_id=${d.file_id}`);
        segs = sr.data.segments ?? [];
      } catch {}

      addAudioFile(projId, {
        fileId:   d.file_id,
        name:     file.name,
        bpm:      d.analysis?.bpm ?? 120,
        key:      d.analysis?.key ?? "C",
        duration: d.duration ?? 0,
        segments: segs,
      });

      toast(`Uploaded: ${file.name}`, "success");
    } catch {
      toast("Upload failed — is the backend running?", "error");
    } finally {
      setUploading(false);
    }
  }

  const audioFiles = proj?.audioFiles ?? [];

  return (
    <div className="page-wrap">
      {/* Header */}
      <div className="ws-header">
        <div className="row row-between row-wrap" style={{ gap: 12 }}>
          <div>
            <h1><span className="grad-text-primary">Create</span></h1>
            <p style={{ marginTop: 4 }}>Set your style, write lyrics, upload audio, and save to your project.</p>
          </div>
          {proj && (
            <div className="row row-3">
              <span className="badge badge-indigo">
                <FileAudio size={11} /> {audioFiles.length} file{audioFiles.length !== 1 ? "s" : ""}
              </span>
              <button className="btn btn-secondary btn-sm" onClick={() => navigate("/mixlab")}>
                <Sparkles size={13} /> MixLab <ChevronRight size={13} />
              </button>
            </div>
          )}
        </div>
      </div>

      {!proj && (
        <div className="card" style={{ marginBottom: 20, display: "flex", alignItems: "center", gap: 12, padding: "14px 18px" }}>
          <AlertCircle size={18} style={{ color: "var(--amber)", flexShrink: 0 }} />
          <div>
            <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>No active project</div>
            <div style={{ fontSize: "0.8rem", color: "var(--text-2)" }}>A project will be created automatically when you generate or upload.</div>
          </div>
        </div>
      )}

      <div className="grid-2" style={{ gap: 20 }}>
        {/* ── Left: settings ────────────────────────────────── */}
        <div className="stack stack-4">

          {/* Song settings */}
          <div className="card stack stack-4">
            <div style={{ fontWeight: 700, fontSize: "1rem" }}>Song Settings</div>

            <div className="form-group">
              <label className="label">Voice</label>
              <select className="select" value={form.voice} onChange={e => patch("voice", e.target.value)}>
                {voices.map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>

            <div className="form-group">
              <label className="label">Genre</label>
              <select className="select" value={form.genre} onChange={e => patch("genre", e.target.value)}>
                {genres.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
            </div>

            <div className="form-group">
              <label className="label">Model Quality</label>
              <div className="radio-group">
                {MODEL_SIZES.map(m => (
                  <label key={m.id} className={`radio-pill${form.modelSize === m.id ? " selected" : ""}`}>
                    <input type="radio" name="modelSize" value={m.id}
                           checked={form.modelSize === m.id}
                           onChange={() => patch("modelSize", m.id)} />
                    <span>{m.label}</span>
                    <span style={{ fontSize: "0.72rem", color: "var(--text-3)" }}>{m.desc}</span>
                  </label>
                ))}
              </div>
            </div>

            <label className="toggle-wrap" onClick={() => patch("instrumentalOnly", !form.instrumentalOnly)}>
              <div>
                <div className="toggle-label">Instrumental Only</div>
                <div className="toggle-sub">No vocals — music only</div>
              </div>
              <div className="toggle">
                <input type="checkbox" checked={form.instrumentalOnly} readOnly />
                <span className="toggle-track" /><span className="toggle-thumb" />
              </div>
            </label>
          </div>

          {/* Secret Writer */}
          <div className="card stack stack-3">
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Wand2 size={15} style={{ color: "var(--violet)" }} />
              <span style={{ fontWeight: 700, fontSize: "0.9rem" }}>Secret Writer</span>
              <span className="badge badge-violet" style={{ marginLeft: "auto" }}>AI Co-Writer</span>
            </div>
            <div style={{ fontSize: "0.8rem", color: "var(--text-2)" }}>
              Describe your vision — AI plans the song and suggests lyrics, voice, and genre.
            </div>

            {/* Context box (also sent into generation) */}
            <textarea
              className="textarea mono"
              placeholder="e.g. Early Drake energy — melancholic but catchy. 808s, minimal beat."
              value={form.secretWriter}
              onChange={e => patch("secretWriter", e.target.value)}
              style={{ minHeight: 72 }}
            />

            {/* Ask the writer */}
            <div style={{ display: "flex", gap: 8 }}>
              <input
                className="input" style={{ flex: 1 }}
                placeholder="Ask Secret Writer — 'write me a sad trap chorus'"
                value={swPrompt}
                onChange={e => setSwPrompt(e.target.value)}
                onKeyDown={e => e.key === "Enter" && callSecretWriter()}
              />
              <button className="btn btn-primary btn-sm" onClick={callSecretWriter} disabled={swLoading} style={{ flexShrink: 0 }}>
                {swLoading ? <Loader2 size={13} className="spin" /> : <Sparkles size={13} />}
                Ask
              </button>
            </div>

            {/* Writer result */}
            {swResult && (
              <div style={{ background: "var(--bg-input)", border: "1px solid rgba(124,58,237,0.35)", borderRadius: "var(--radius-md)", padding: "12px 14px" }}>
                {swResult.assistant_message && (
                  <div style={{ fontSize: "0.82rem", color: "var(--text-1)", marginBottom: 10, lineHeight: 1.6 }}>
                    {swResult.assistant_message}
                  </div>
                )}
                {swResult.song && (
                  <div className="row row-2 row-wrap" style={{ marginBottom: 8 }}>
                    {swResult.song.genre && <span className="badge badge-indigo">{swResult.song.genre}</span>}
                    {swResult.song.voice && <span className="badge badge-violet">{swResult.song.voice}</span>}
                    {swResult.song.bpm   && <span className="badge badge-muted">{swResult.song.bpm} BPM</span>}
                    {swResult.song.mood_tags?.map(t => <span key={t} className="badge badge-cyan">{t}</span>)}
                  </div>
                )}
                {swResult.lyrics?.text && (
                  <div style={{
                    background: "var(--bg-card-2)", border: "1px solid var(--border-1)",
                    borderRadius: "var(--radius-sm)", padding: "8px 10px",
                    fontSize: "0.8rem", fontFamily: "var(--font-mono)", color: "var(--text-2)",
                    maxHeight: 110, overflowY: "auto", marginBottom: 10, whiteSpace: "pre-wrap",
                  }}>
                    {swResult.lyrics.text.slice(0, 400)}{swResult.lyrics.text.length > 400 ? "…" : ""}
                  </div>
                )}
                <div className="row row-2">
                  <button className="btn btn-ghost btn-sm" onClick={() => setSwResult(null)}>
                    <X size={12} /> Dismiss
                  </button>
                  <button className="btn btn-primary btn-sm" style={{ flex: 1 }} onClick={() => applySwResult(swResult)}>
                    <Check size={12} /> Apply to Song
                  </button>
                </div>
              </div>
            )}

            {/* Production notes (auto-filled by Secret Writer) */}
            {form.production_notes && (
              <div className="form-group">
                <label className="label">Production Notes</label>
                <textarea className="textarea mono" style={{ minHeight: 60 }}
                          value={form.production_notes}
                          onChange={e => patch("production_notes", e.target.value)} />
              </div>
            )}
          </div>
        </div>

        {/* ── Right: lyrics + upload + generate ─────────────── */}
        <div className="stack stack-4">

          {/* Lyrics */}
          <div className="card stack stack-3" style={{ flex: 1 }}>
            <div className="row row-between">
              <span style={{ fontWeight: 700, fontSize: "1rem" }}>Lyrics</span>
              {!form.instrumentalOnly && (
                <button className="btn btn-secondary btn-sm" disabled={writingLyrics || generating} onClick={handleWriteLyrics}>
                  {writingLyrics ? <Loader2 size={12} className="spin" /> : <Sparkles size={12} />}
                  Write with AI
                </button>
              )}
            </div>
            {form.instrumentalOnly ? (
              <div style={{ padding: "24px", textAlign: "center", color: "var(--text-2)", fontSize: "0.875rem", border: "1px dashed var(--border-2)", borderRadius: "var(--radius-md)" }}>
                <Music2 size={28} style={{ color: "var(--text-3)", marginBottom: 8 }} />
                <div>Instrumental mode — no lyrics needed.</div>
              </div>
            ) : (
              <textarea
                className="textarea"
                placeholder={"[Verse 1]\nWrite your lyrics here...\n\n[Chorus]\n..."}
                value={form.lyrics}
                onChange={e => patch("lyrics", e.target.value)}
                style={{ minHeight: 200, resize: "vertical" }}
              />
            )}
          </div>

          {/* Generate */}
          <button className="btn btn-primary btn-lg" style={{ width: "100%" }}
                  onClick={handleGenerate} disabled={generating || uploading}>
            {generating
              ? <><Loader2 size={18} className="spin" /> Generating...</>
              : <><Sparkles size={18} /> Generate</>}
          </button>

          {/* Divider */}
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <hr className="divider" style={{ flex: 1, margin: 0 }} />
            <span style={{ fontSize: "0.75rem", color: "var(--text-3)", whiteSpace: "nowrap" }}>or upload audio</span>
            <hr className="divider" style={{ flex: 1, margin: 0 }} />
          </div>

          {/* Upload zone — multi-file */}
          <div
            className={`upload-zone${dragOver ? " drag-over" : ""}`}
            onClick={() => fileRef.current?.click()}
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={e => {
              e.preventDefault(); setDragOver(false);
              Array.from(e.dataTransfer.files).forEach(handleUpload);
            }}
          >
            <input ref={fileRef} type="file" accept="audio/*,.mp3,.wav,.m4a,.flac,.ogg"
                   multiple style={{ display: "none" }}
                   onChange={e => Array.from(e.target.files).forEach(handleUpload)} />
            {uploading
              ? <><Loader2 size={32} style={{ color: "var(--indigo)" }} className="spin" /><h4>Uploading...</h4></>
              : <><Upload size={32} /><h4>Drop audio files here</h4><p>MP3, WAV, FLAC, M4A · Multiple files supported</p></>
            }
          </div>
        </div>
      </div>

      {/* ── Audio files ───────────────────────────────────────── */}
      {audioFiles.length > 0 && (
        <div style={{ marginTop: 36 }}>
          <div className="row row-between" style={{ marginBottom: 14 }}>
            <h2 style={{ fontSize: "1.1rem" }}>Audio Files</h2>
            <span className="badge badge-muted">{audioFiles.length}</span>
          </div>
          <div className="stack stack-3">
            {audioFiles.map(f => (
              <AudioFileRow key={f.id} file={f} projectId={proj.id} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Audio file row ──────────────────────────────────────────────────────────
function AudioFileRow({ file, projectId }) {
  const { removeAudioFile, sendToMixLab, addToCompareSlot, toast } = useProject();
  const navigate = useNavigate();

  const bars = Array.from({ length: 48 }, (_, i) =>
    20 + Math.sin(i * 0.7 + file.bpm * 0.01) * 14 + Math.abs(Math.sin(i * 1.4)) * 18
  );

  const SLOT_LABELS = ["A", "B", "C"];
  const SLOT_COLORS = ["var(--cyan)", "var(--pink)", "var(--amber)"];

  return (
    <div className={`track-card${file.inMixLab ? " in-mixlab" : ""}`}>
      <div className="track-meta">
        <div className="track-icon"><Music2 /></div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="track-name truncate">{file.name}</div>
          <div className="track-info">
            {Math.round(file.bpm)} BPM · {file.key}
            {file.duration > 0 && ` · ${fmt(file.duration)}`}
            {file.segments?.length > 0 && ` · ${file.segments.length} segments`}
          </div>
        </div>
        <div className="row row-2">
          {file.inMixLab  && <span className="badge badge-indigo">In MixLab</span>}
          {!file.fileId   && <span className="badge badge-violet">Generated</span>}
        </div>
      </div>

      {/* Waveform */}
      <div className="waveform-placeholder" style={{ marginBottom: 10 }}>
        <div className="waveform-bars">
          {bars.map((h, i) => (
            <div key={i} className="waveform-bar"
                 style={{ height: `${h}%`, background: file.inMixLab ? `rgba(79,70,229,${0.3 + h / 60})` : `rgba(236,72,153,${0.2 + h / 60})` }} />
          ))}
        </div>
      </div>

      {/* Segments */}
      {file.segments?.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
          {file.segments.map((s, i) => {
            const base = s.label?.replace(/\s+\d+$/, "") ?? "Section";
            const cls  = ["Intro","Verse","Chorus","Bridge","Rap","Outro"].includes(base) ? base : "Section";
            return (
              <span key={i} className={`seg-chip seg-${cls}`} title={`${fmt(s.start)} – ${fmt(s.end)}`}>
                {s.label} <span style={{ opacity: 0.6 }}>({fmt(s.end - s.start)})</span>
              </span>
            );
          })}
        </div>
      )}

      {/* Actions */}
      <div className="row row-2" style={{ justifyContent: "space-between" }}>
        <div className="row row-2">
          {/* Compare slot buttons */}
          {file.fileId && [0, 1, 2].map(i => (
            <button key={i} className="btn btn-sm" onClick={() => {
              addToCompareSlot(projectId, file);
              toast(`Added to Slot ${SLOT_LABELS[i]}`, "success");
            }}
            style={{
              padding: "4px 9px", borderRadius: "var(--radius-pill)", fontSize: "0.75rem",
              fontWeight: 700, border: `1px solid ${SLOT_COLORS[i]}44`,
              background: SLOT_COLORS[i] + "12", color: SLOT_COLORS[i],
            }}>
              {SLOT_LABELS[i]}
            </button>
          ))}
        </div>
        <div className="row row-2">
          <button className="btn btn-danger btn-sm" onClick={() => removeAudioFile(projectId, file.id)}>
            <Trash2 size={12} />
          </button>
          {file.inMixLab
            ? <button className="btn btn-secondary btn-sm" onClick={() => navigate("/mixlab")}>
                View in MixLab <ChevronRight size={12} />
              </button>
            : file.fileId
              ? <button className="btn btn-primary btn-sm" onClick={() => sendToMixLab(projectId, file.id)}>
                  <Send size={12} /> Send to MixLab
                </button>
              : null
          }
        </div>
      </div>
    </div>
  );
}

function fmt(s) {
  if (!s && s !== 0) return "";
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}
