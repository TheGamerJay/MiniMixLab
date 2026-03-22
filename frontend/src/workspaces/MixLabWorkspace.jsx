import React, { useState, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Layers, Upload, Play, X, Plus, Trash2,
  Music2, Loader2, AudioLines, Sliders, Clock,
  RotateCcw, ChevronDown, ChevronRight, AlertTriangle
} from "lucide-react";
import { useProject } from "../contexts/ProjectContext";
import axios from "axios";

const SLOT_LABELS = ["A", "B", "C"];
const SLOT_COLORS = ["var(--cyan)", "var(--pink)", "var(--amber)"];

export default function MixLabWorkspace() {
  const {
    activeProject, activeProjectId,
    compareSlots, clearCompareSlot,
    updateProject, updateAudioFile,
    addTimelineItem, removeTimelineItem, clearTimeline,
    toast, addAudioFile, sendToMixLab,
  } = useProject();
  const navigate = useNavigate();

  const [analyzing,  setAnalyzing]  = useState({});   // slotIdx or trackId -> bool
  const [expanded,   setExpanded]   = useState({ 0: true, 1: true, 2: true });
  const [rendering,  setRendering]  = useState(false);
  const fileRef = useRef();

  const project = activeProject;

  // ── Panels: combine compare slots + project mixlab tracks ──────────────────
  // Compare slots take priority. If a slot is empty, show nothing for that slot.
  const panels = SLOT_LABELS.map((_, i) => {
    const slot = compareSlots[i];
    if (!slot) return null;
    return { slotIdx: i, ...slot };
  }).filter(Boolean);

  // Also show any mixlab tracks not already in a slot
  const slotFileIds = new Set(panels.map(p => p.backendFileId).filter(Boolean));
  const extraTracks = (project?.audioFiles ?? [])
    .filter(f => f.inMixLab && f.fileId && !slotFileIds.has(f.fileId));

  // ── Analyze segments for a compare-slot panel ─────────────────────────────
  async function analyzeSlot(slotIdx) {
    const slot = compareSlots[slotIdx];
    if (!slot?.backendFileId) { toast("No audio file in this slot", "error"); return; }
    setAnalyzing(prev => ({ ...prev, [slotIdx]: true }));
    try {
      const res = await axios.get(`/api/segment?file_id=${slot.backendFileId}`);
      const segs = res.data.segments ?? [];
      // Update the compare slot's segments in project audioFiles
      if (slot.projectId && slot.fileId) {
        updateAudioFile(slot.projectId, slot.fileId, { segments: segs });
      }
      // Also update the slot itself via a re-trigger (segments now in audioFile)
      toast("Segments analyzed", "success");
    } catch {
      toast("Analysis failed", "error");
    } finally {
      setAnalyzing(prev => ({ ...prev, [slotIdx]: false }));
    }
  }

  // ── Preview ────────────────────────────────────────────────────────────────
  function previewSegment(fileId, start, end) {
    if (!fileId) { toast("No audio file for preview", "error"); return; }
    const audio = new Audio(`/api/preview?file_id=${fileId}&start=${start}&end=${end}`);
    audio.play().catch(() => toast("Preview failed — check backend", "error"));
  }

  // ── Add to timeline ────────────────────────────────────────────────────────
  function addToTimeline(slot, seg, laneIdx) {
    if (!project) { toast("No active project", "error"); return; }
    addTimelineItem(activeProjectId, {
      trackName:  slot.trackName,
      fileId:     slot.backendFileId,
      label:      seg.label,
      start:      seg.start,
      end:        seg.end,
      lane:       laneIdx ?? slot.slotIdx ?? 0,
      color:      tlClass(seg.label),
    });
  }

  // ── Upload directly into MixLab ────────────────────────────────────────────
  async function handleUpload(file) {
    if (!file || !project) { toast("Select or create a project first", "error"); return; }
    const fd = new FormData();
    fd.append("file", file);
    setAnalyzing(prev => ({ ...prev, upload: true }));
    try {
      const res  = await axios.post("/api/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      const d    = res.data;
      let segs   = [];
      try { const sr = await axios.get(`/api/segment?file_id=${d.file_id}`); segs = sr.data.segments ?? []; } catch {}

      const af = addAudioFile(activeProjectId, {
        fileId: d.file_id, name: file.name,
        bpm: d.analysis?.bpm ?? 120, key: d.analysis?.key ?? "C",
        duration: d.duration ?? 0, segments: segs,
      });
      sendToMixLab(activeProjectId, af.id);
      toast(`Loaded: ${file.name}`, "success");
    } catch {
      toast("Upload failed", "error");
    } finally {
      setAnalyzing(prev => ({ ...prev, upload: false }));
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  async function handleRender() {
    const items = project?.timelineItems ?? [];
    if (items.length === 0) { toast("Add segments to the timeline first", "error"); return; }
    setRendering(true);
    try {
      await axios.post("/api/arrange/render", {
        bpm:   project.targetBpm ?? 120,
        key:   project.targetKey ?? "Am",
        items: items.map(i => ({ file_id: i.fileId, start: i.start, end: i.end, lane: i.lane })),
      });
      toast("Render complete!", "success");
    } catch {
      toast("Render failed — check backend", "error");
    } finally {
      setRendering(false);
    }
  }

  // ── Empty state ────────────────────────────────────────────────────────────
  if (!project) {
    return (
      <div className="page-wrap">
        <div className="ws-header"><h1><span className="grad-text-primary">MixLab</span></h1></div>
        <div className="empty-state card">
          <div className="empty-icon"><Layers size={22} /></div>
          <h3>No active project</h3>
          <p>Create a project in Create, then send tracks here.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-wrap wide">
      {/* Header */}
      <div className="ws-header">
        <div className="row row-between row-wrap" style={{ gap: 12 }}>
          <div>
            <h1><span className="grad-text-primary">MixLab</span></h1>
            <p style={{ marginTop: 4 }}>Compare tracks side-by-side, pick the best segments, arrange on the timeline.</p>
          </div>
          <div className="row row-3 row-wrap">
            {/* BPM + Key */}
            <div className="row row-2" style={{
              background: "var(--bg-card)", border: "1px solid var(--border-2)",
              borderRadius: "var(--radius-md)", padding: "6px 12px", gap: 12,
            }}>
              <Sliders size={13} style={{ color: "var(--text-2)" }} />
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.82rem", color: "var(--text-2)" }}>
                BPM
                <input type="number" min={60} max={300} value={project.targetBpm ?? 120}
                       onChange={e => updateProject(activeProjectId, { targetBpm: +e.target.value })}
                       style={{ width: 50, background: "transparent", border: "none", outline: "none", color: "var(--text-1)", fontWeight: 600, fontSize: "0.85rem", fontFamily: "var(--font)" }} />
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.82rem", color: "var(--text-2)" }}>
                Key
                <select value={project.targetKey ?? "Am"}
                        onChange={e => updateProject(activeProjectId, { targetKey: e.target.value })}
                        style={{ background: "transparent", border: "none", outline: "none", color: "var(--text-1)", fontWeight: 600, fontSize: "0.85rem", fontFamily: "var(--font)", cursor: "pointer" }}>
                  {["C","C#","D","D#","E","F","F#","G","G#","A","A#","B","Am","Bm","Cm","Dm","Em","Fm","Gm"].map(k => <option key={k} value={k}>{k}</option>)}
                </select>
              </label>
            </div>

            {/* Upload */}
            <button className="btn btn-secondary btn-sm"
                    onClick={() => fileRef.current?.click()}
                    disabled={analyzing.upload}>
              {analyzing.upload ? <Loader2 size={13} className="spin" /> : <Upload size={13} />}
              Load Track
            </button>
            <input ref={fileRef} type="file" accept="audio/*,.mp3,.wav,.m4a,.flac"
                   style={{ display: "none" }} onChange={e => handleUpload(e.target.files?.[0])} />
          </div>
        </div>
      </div>

      {/* ── Compare slot hint ───────────────────────────────── */}
      {panels.length === 0 && extraTracks.length === 0 && (
        <div className="card" style={{ display: "flex", alignItems: "center", gap: 14, padding: "16px 20px", marginBottom: 20, borderColor: "rgba(245,158,11,0.2)" }}>
          <AlertTriangle size={18} style={{ color: "var(--amber)", flexShrink: 0 }} />
          <div>
            <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>No tracks loaded</div>
            <div style={{ fontSize: "0.8rem", color: "var(--text-2)" }}>
              Go to <strong style={{ color: "var(--text-1)" }}>Library</strong> and click <strong style={{ color: "var(--text-1)" }}>Slot A / B / C</strong> on a project, or load a track above.
            </div>
          </div>
          <button className="btn btn-secondary btn-sm" style={{ marginLeft: "auto", flexShrink: 0 }}
                  onClick={() => navigate("/library")}>
            Go to Library <ChevronRight size={13} />
          </button>
        </div>
      )}

      {/* ── Compare panels ───────────────────────────────────── */}
      {panels.length > 0 && (
        <div style={{
          display: "grid",
          gridTemplateColumns: `repeat(${Math.min(panels.length, 3)}, 1fr)`,
          gap: 16, marginBottom: 24,
        }}>
          {panels.map(panel => {
            // Resolve segments: check project audioFiles for live segment data
            const liveFile = project.audioFiles?.find(f => f.id === panel.fileId);
            const segments = liveFile?.segments ?? panel.segments ?? [];
            return (
              <SlotPanel
                key={panel.slotIdx}
                panel={panel}
                segments={segments}
                slotIdx={panel.slotIdx}
                isAnalyzing={!!analyzing[panel.slotIdx]}
                isExpanded={expanded[panel.slotIdx] ?? true}
                onToggle={() => setExpanded(prev => ({ ...prev, [panel.slotIdx]: !prev[panel.slotIdx] }))}
                onAnalyze={() => analyzeSlot(panel.slotIdx)}
                onPreview={previewSegment}
                onAddToTimeline={(seg) => addToTimeline(panel, seg)}
                onClearSlot={() => clearCompareSlot(panel.slotIdx)}
              />
            );
          })}
        </div>
      )}

      {/* ── Extra MixLab tracks (not in compare slots) ────── */}
      {extraTracks.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: "0.75rem", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600, marginBottom: 10 }}>
            Also in MixLab
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 12 }}>
            {extraTracks.map(f => (
              <MiniTrackCard key={f.id} file={f} onAddToTimeline={(seg) =>
                addTimelineItem(activeProjectId, {
                  trackName: f.name, fileId: f.fileId, label: seg.label,
                  start: seg.start, end: seg.end, lane: 0, color: tlClass(seg.label),
                })
              } onPreview={previewSegment} />
            ))}
          </div>
        </div>
      )}

      {/* ── Timeline ──────────────────────────────────────── */}
      <TimelinePanel
        project={project}
        projectId={activeProjectId}
        onRemoveItem={removeTimelineItem}
        onClear={clearTimeline}
        onRender={handleRender}
        rendering={rendering}
      />
    </div>
  );
}

// ── Slot Panel ─────────────────────────────────────────────────────────────
function SlotPanel({ panel, segments, slotIdx, isAnalyzing, isExpanded, onToggle, onAnalyze, onPreview, onAddToTimeline, onClearSlot }) {
  const color = SLOT_COLORS[slotIdx];
  const label = SLOT_LABELS[slotIdx];

  const bars = Array.from({ length: 60 }, (_, i) =>
    15 + Math.sin(i * 0.5 + slotIdx) * 18 + Math.abs(Math.sin(i * 1.3)) * 22
  );

  return (
    <div className="card" style={{ padding: 0, overflow: "hidden", borderColor: `${color}30` }}>
      {/* Header */}
      <div style={{
        padding: "12px 14px", display: "flex", alignItems: "center", gap: 10,
        borderBottom: "1px solid var(--border-1)", cursor: "pointer",
        background: `${color}08`,
      }} onClick={onToggle}>
        <div style={{
          width: 28, height: 28, borderRadius: "50%",
          background: `${color}22`, border: `1px solid ${color}55`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: "0.75rem", fontWeight: 800, color, flexShrink: 0,
        }}>{label}</div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: "0.85rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {panel.trackName}
          </div>
          <div style={{ fontSize: "0.72rem", color: "var(--text-3)" }}>
            {panel.projectTitle}
            {panel.bpm && ` · ${Math.round(panel.bpm)} BPM`}
            {panel.key  && ` · ${panel.key}`}
          </div>
        </div>

        <div className="row row-2" onClick={e => e.stopPropagation()}>
          <button className="btn btn-ghost btn-icon btn-sm" title="Clear slot" onClick={onClearSlot}>
            <X size={13} />
          </button>
          {isExpanded ? <ChevronDown size={14} style={{ color: "var(--text-2)" }} />
                      : <ChevronRight size={14} style={{ color: "var(--text-2)" }} />}
        </div>
      </div>

      {isExpanded && (
        <div style={{ padding: "12px 14px" }}>
          {/* Waveform */}
          <div className="waveform-placeholder" style={{ height: 52, marginBottom: 10 }}>
            <div className="waveform-bars">
              {bars.map((h, i) => (
                <div key={i} className="waveform-bar"
                     style={{ height: `${Math.min(h, 90)}%`, background: `${color}${Math.floor((0.2 + h / 60) * 255).toString(16).padStart(2, "0")}` }} />
              ))}
            </div>
          </div>

          {/* Analyze button */}
          {panel.backendFileId && segments.length === 0 && !isAnalyzing && (
            <button className="btn btn-secondary btn-sm" style={{ width: "100%", marginBottom: 10 }} onClick={onAnalyze}>
              <AudioLines size={13} /> Detect Sections
            </button>
          )}

          {isAnalyzing && (
            <div style={{ display: "flex", justifyContent: "center", padding: "14px 0" }}>
              <Loader2 size={20} className="spin" style={{ color: "var(--indigo)" }} />
            </div>
          )}

          {!isAnalyzing && segments.length > 0 && (
            <div>
              <div style={{ fontSize: "0.7rem", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 7, fontWeight: 600 }}>
                Sections — click + to add to timeline
              </div>
              <div className="stack" style={{ gap: 4 }}>
                {segments.map((seg, i) => {
                  const base = seg.label?.replace(/\s+\d+$/, "") ?? "Section";
                  const cls  = ["Intro","Verse","Chorus","Bridge","Rap","Outro"].includes(base) ? base : "Section";
                  return (
                    <div key={i} style={{
                      display: "flex", alignItems: "center", gap: 8,
                      padding: "5px 8px", background: "var(--bg-input)",
                      border: "1px solid var(--border-1)", borderRadius: "var(--radius-sm)",
                    }}>
                      <span className={`seg-chip seg-${cls}`} style={{ fontSize: "0.72rem", padding: "2px 7px" }}>
                        {seg.label}
                      </span>
                      <span style={{ flex: 1, fontSize: "0.72rem", color: "var(--text-3)" }}>
                        {fmt(seg.start)} – {fmt(seg.end)} ({fmt(seg.end - seg.start)})
                      </span>
                      <div className="row row-2">
                        {panel.backendFileId && (
                          <button className="btn btn-ghost btn-icon btn-sm" title="Preview"
                                  onClick={() => onPreview(panel.backendFileId, seg.start, seg.end)}>
                            <Play size={11} />
                          </button>
                        )}
                        <button className="btn btn-primary btn-icon btn-sm" title="Add to timeline"
                                onClick={() => onAddToTimeline(seg)}>
                          <Plus size={11} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {!isAnalyzing && segments.length === 0 && !panel.backendFileId && (
            <div style={{ textAlign: "center", padding: "12px 0", fontSize: "0.8rem", color: "var(--text-2)" }}>
              Generated track — no real audio. Upload audio for segment analysis.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Mini track card (extra mixlab tracks) ──────────────────────────────────
function MiniTrackCard({ file, onAddToTimeline, onPreview }) {
  return (
    <div className="card" style={{ padding: "12px 14px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <Music2 size={14} style={{ color: "var(--text-2)" }} />
        <span style={{ fontWeight: 600, fontSize: "0.85rem", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {file.name}
        </span>
        <span style={{ fontSize: "0.72rem", color: "var(--text-3)" }}>
          {Math.round(file.bpm)} BPM · {file.key}
        </span>
      </div>
      {file.segments?.map((seg, i) => {
        const base = seg.label?.replace(/\s+\d+$/, "") ?? "Section";
        const cls  = ["Intro","Verse","Chorus","Bridge","Rap","Outro"].includes(base) ? base : "Section";
        return (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
            <span className={`seg-chip seg-${cls}`} style={{ fontSize: "0.7rem", padding: "2px 6px" }}>{seg.label}</span>
            <span style={{ flex: 1, fontSize: "0.7rem", color: "var(--text-3)" }}>{fmt(seg.end - seg.start)}</span>
            {file.fileId && (
              <button className="btn btn-ghost btn-icon btn-sm" onClick={() => onPreview(file.fileId, seg.start, seg.end)}><Play size={10} /></button>
            )}
            <button className="btn btn-primary btn-icon btn-sm" onClick={() => onAddToTimeline(seg)}><Plus size={10} /></button>
          </div>
        );
      })}
    </div>
  );
}

// ── Timeline Panel ─────────────────────────────────────────────────────────
function TimelinePanel({ project, projectId, onRemoveItem, onClear, onRender, rendering }) {
  const items        = project?.timelineItems ?? [];
  const LANE_COUNT   = 3;
  const totalDur     = items.reduce((max, it) => Math.max(max, it.end ?? 0), 0) || 60;
  const lanes        = Array.from({ length: LANE_COUNT }, (_, i) => items.filter(it => it.lane === i));

  return (
    <div className="timeline-wrap">
      <div className="timeline-header">
        <div className="row row-3">
          <Clock size={15} style={{ color: "var(--text-2)" }} />
          <span style={{ fontWeight: 700, fontSize: "0.95rem" }}>Timeline</span>
          <span className="badge badge-muted">{items.length} segments</span>
        </div>
        <div className="row row-2">
          {items.length > 0 && (
            <button className="btn btn-ghost btn-sm" onClick={() => onClear(projectId)}>
              <RotateCcw size={12} /> Clear
            </button>
          )}
          <button className="btn btn-primary btn-sm" onClick={onRender}
                  disabled={rendering || items.length === 0}>
            {rendering ? <><Loader2 size={13} className="spin" /> Rendering...</> : "Render Mix"}
          </button>
        </div>
      </div>

      {/* Ruler */}
      <div className="timeline-ruler">
        {Array.from({ length: 9 }, (_, i) => (
          <div key={i} style={{ flex: 1, borderLeft: "1px solid var(--border-1)", paddingLeft: 4 }}>
            {fmt((totalDur / 8) * i)}
          </div>
        ))}
      </div>

      {/* Lanes */}
      <div className="timeline-lanes">
        {items.length === 0 ? (
          <div style={{
            textAlign: "center", padding: "28px", fontSize: "0.875rem", color: "var(--text-2)",
            border: "1px dashed var(--border-2)", borderRadius: "var(--radius-md)",
          }}>
            Click <strong style={{ color: "var(--text-1)" }}>+</strong> on a section above to start building your arrangement.
          </div>
        ) : (
          lanes.map((laneItems, laneIdx) => (
            <div key={laneIdx} className="timeline-lane">
              <div className="timeline-lane-label">
                {laneIdx < 3
                  ? <span style={{ color: SLOT_COLORS[laneIdx], fontWeight: 700 }}>{SLOT_LABELS[laneIdx]}</span>
                  : `Lane ${laneIdx + 1}`}
              </div>
              <div style={{ position: "relative", flex: 1, marginLeft: 68, height: "100%" }}>
                {laneItems.map(item => {
                  const left  = ((item.start ?? 0) / totalDur) * 100;
                  const width = (((item.end ?? 0) - (item.start ?? 0)) / totalDur) * 100;
                  return (
                    <div key={item.id}
                         className={`timeline-item ${item.color ?? "tl-Section"}`}
                         style={{ left: `${left}%`, width: `max(${width}%, 36px)` }}
                         title={`${item.trackName} — ${item.label} (${fmt(item.start)} – ${fmt(item.end)})`}>
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", flex: 1 }}>{item.label}</span>
                      <button style={{ background: "none", border: "none", cursor: "pointer", color: "inherit", opacity: 0.7, padding: 0, marginLeft: 3, display: "flex", alignItems: "center" }}
                              onClick={() => onRemoveItem(projectId, item.id)}>
                        <X size={9} />
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function tlClass(label) {
  const base = label?.replace(/\s+\d+$/, "") ?? "";
  return { Intro: "tl-Intro", Verse: "tl-Verse", Chorus: "tl-Chorus", Bridge: "tl-Bridge", Rap: "tl-Rap", Outro: "tl-Outro" }[base] ?? "tl-Section";
}

function fmt(s) {
  if (!s && s !== 0) return "";
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}
