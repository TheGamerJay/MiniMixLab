import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Library, Music2, Layers, Plus, Search, Trash2, Edit3,
  Calendar, FileAudio, Tag, Mic2, ChevronRight, Check,
  AudioLines, FolderOpen, Disc3, X
} from "lucide-react";
import { useProject } from "../contexts/ProjectContext";

const SLOT_LABELS = ["A", "B", "C"];
const SLOT_COLORS = ["var(--cyan)", "var(--pink)", "var(--amber)"];

export default function LibraryWorkspace() {
  const {
    projects, activeProjectId, compareSlots,
    createProject, selectProject, deleteProject, updateProject,
    addToCompareSlot, setCompareSlot, clearCompareSlot, toast,
  } = useProject();
  const navigate = useNavigate();

  const [search,    setSearch]    = useState("");
  const [renaming,  setRenaming]  = useState(null);
  const [renameVal, setRenameVal] = useState("");

  const filtered = projects.filter(p =>
    p.title.toLowerCase().includes(search.toLowerCase()) ||
    p.genre?.toLowerCase().includes(search.toLowerCase())
  );

  function handleOpen(id) { selectProject(id); navigate("/create"); }
  function handleMixLab(id) { selectProject(id); navigate("/mixlab"); }

  function handleDelete(e, id) {
    e.stopPropagation();
    if (projects.length === 1) { toast("Can't delete your only project", "error"); return; }
    deleteProject(id);
    toast("Project deleted", "info");
  }

  function startRename(e, p) {
    e.stopPropagation();
    setRenaming(p.id);
    setRenameVal(p.title);
  }

  function commitRename(id) {
    if (renameVal.trim()) updateProject(id, { title: renameVal.trim() });
    setRenaming(null);
  }

  // Assign an audio file to a specific compare slot
  function assignSlot(e, project, slotIdx) {
    e.stopPropagation();
    const files = project.audioFiles ?? [];
    if (files.length === 0) { toast("No audio files in this project", "error"); return; }
    // pick the first file with a real fileId, else the first file
    const file = files.find(f => f.fileId) ?? files[0];
    setCompareSlot(slotIdx, {
      projectId:    project.id,
      fileId:       file.id,
      backendFileId: file.fileId,
      trackName:    file.name,
      bpm:          file.bpm,
      key:          file.key,
      duration:     file.duration,
      segments:     file.segments,
      projectTitle: project.title,
    });
    toast(`Loaded "${file.name}" → Slot ${SLOT_LABELS[slotIdx]}`, "success");
  }

  return (
    <div className="page-wrap">
      {/* Header */}
      <div className="ws-header">
        <div className="row row-between row-wrap" style={{ gap: 12 }}>
          <div>
            <h1><span className="grad-text-primary">Library</span></h1>
            <p style={{ marginTop: 4 }}>All your projects, audio files, and saved sessions.</p>
          </div>
          <div className="row row-3 row-wrap">
            {/* Compare slot status bar */}
            <CompareSlotsBar slots={compareSlots} onClear={clearCompareSlot} onOpenMixLab={() => navigate("/mixlab")} />
            <div style={{ position: "relative" }}>
              <Search size={14} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--text-3)", pointerEvents: "none" }} />
              <input className="input" style={{ paddingLeft: 32, width: 200 }}
                     placeholder="Search..." value={search} onChange={e => setSearch(e.target.value)} />
            </div>
            <button className="btn btn-primary btn-sm" onClick={() => { createProject(); navigate("/create"); }}>
              <Plus size={14} /> New Project
            </button>
          </div>
        </div>
      </div>

      {/* Empty */}
      {filtered.length === 0 && (
        <div className="empty-state card">
          <div className="empty-icon">{search ? <Search size={22} /> : <FolderOpen size={22} />}</div>
          <h3>{search ? "No projects match" : "No projects yet"}</h3>
          <p>{search ? "Try a different search term." : "Start in the Create workspace."}</p>
          {!search && (
            <button className="btn btn-primary" style={{ marginTop: 8 }}
                    onClick={() => { createProject(); navigate("/create"); }}>
              <Plus size={14} /> Create Project
            </button>
          )}
        </div>
      )}

      {/* Project grid */}
      <div className="stack stack-3">
        {filtered.map(project => (
          <ProjectCard
            key={project.id}
            project={project}
            isActive={project.id === activeProjectId}
            compareSlots={compareSlots}
            renaming={renaming}
            renameVal={renameVal}
            setRenameVal={setRenameVal}
            onOpen={() => handleOpen(project.id)}
            onMixLab={() => handleMixLab(project.id)}
            onDelete={e => handleDelete(e, project.id)}
            onStartRename={e => startRename(e, project)}
            onCommitRename={() => commitRename(project.id)}
            onCancelRename={() => setRenaming(null)}
            onAssignSlot={(e, slotIdx) => assignSlot(e, project, slotIdx)}
            onClearSlot={(e, slotIdx) => { e.stopPropagation(); clearCompareSlot(slotIdx); }}
          />
        ))}
      </div>
    </div>
  );
}

// ── Compare slots status bar ────────────────────────────────────────────────
function CompareSlotsBar({ slots, onClear, onOpenMixLab }) {
  const filled = slots.filter(Boolean);
  if (filled.length === 0) return null;
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 6,
      background: "var(--bg-card)", border: "1px solid var(--border-2)",
      borderRadius: "var(--radius-md)", padding: "6px 10px",
    }}>
      <span style={{ fontSize: "0.72rem", color: "var(--text-3)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
        Compare
      </span>
      {slots.map((slot, i) => (
        <div key={i} style={{
          display: "flex", alignItems: "center", gap: 4,
          padding: "2px 8px", borderRadius: "var(--radius-pill)",
          background: slot ? SLOT_COLORS[i] + "18" : "var(--bg-input)",
          border: `1px solid ${slot ? SLOT_COLORS[i] + "50" : "var(--border-1)"}`,
          fontSize: "0.72rem", color: slot ? SLOT_COLORS[i] : "var(--text-3)",
          fontWeight: 700,
        }}>
          <span style={{ width: 12, height: 12, borderRadius: "50%", background: SLOT_COLORS[i] + (slot ? "88" : "33"), border: `1px solid ${SLOT_COLORS[i]}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: "0.6rem" }}>
            {SLOT_LABELS[i]}
          </span>
          {slot
            ? <><span style={{ maxWidth: 60, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{slot.trackName}</span>
                <button onClick={() => onClear(i)} style={{ background: "none", border: "none", cursor: "pointer", color: "inherit", opacity: 0.6, padding: 0, display: "flex" }}><X size={9} /></button>
              </>
            : <span style={{ opacity: 0.4 }}>Empty</span>
          }
        </div>
      ))}
      {filled.length > 0 && (
        <button className="btn btn-primary btn-sm" style={{ padding: "3px 8px", fontSize: "0.72rem" }} onClick={onOpenMixLab}>
          <Layers size={11} /> Open MixLab
        </button>
      )}
    </div>
  );
}

// ── Project card ────────────────────────────────────────────────────────────
function ProjectCard({
  project, isActive, compareSlots,
  renaming, renameVal, setRenameVal,
  onOpen, onMixLab, onDelete,
  onStartRename, onCommitRename, onCancelRename,
  onAssignSlot, onClearSlot,
}) {
  const files      = project.audioFiles ?? [];
  const hasSegs    = files.some(f => f.segments?.length > 0);
  const slotLabels = compareSlots.map((s, i) =>
    s?.projectId === project.id ? SLOT_LABELS[i] : null
  ).filter(Boolean);

  const createdDate = new Date(project.created_at ?? project.createdAt ?? Date.now())
    .toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });

  return (
    <div
      className={`card${isActive ? " card-glow-indigo" : ""}`}
      style={{ cursor: "pointer" }}
      onClick={onOpen}
    >
      {/* Top row */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 14 }}>
        <div style={{
          width: 44, height: 44, borderRadius: "var(--radius-md)",
          background: "var(--grad-primary)",
          display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
        }}>
          <Disc3 size={20} style={{ color: "#fff" }} />
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          {renaming === project.id ? (
            <input
              className="input"
              style={{ padding: "4px 8px", fontSize: "1rem", fontWeight: 700, height: "auto" }}
              value={renameVal}
              autoFocus
              onChange={e => setRenameVal(e.target.value)}
              onBlur={onCommitRename}
              onKeyDown={e => {
                if (e.key === "Enter")  onCommitRename();
                if (e.key === "Escape") onCancelRename();
                e.stopPropagation();
              }}
              onClick={e => e.stopPropagation()}
            />
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <h3 style={{ fontSize: "1rem", fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 280 }}>
                {project.title}
              </h3>
              {isActive && <span className="badge badge-indigo">Active</span>}
              {slotLabels.map(l => (
                <span key={l} className="badge" style={{ background: SLOT_COLORS[SLOT_LABELS.indexOf(l)] + "18", color: SLOT_COLORS[SLOT_LABELS.indexOf(l)], border: `1px solid ${SLOT_COLORS[SLOT_LABELS.indexOf(l)]}44`, fontSize: "0.68rem", fontWeight: 700 }}>
                  Slot {l}
                </span>
              ))}
            </div>
          )}
          <div className="row row-2 row-wrap" style={{ marginTop: 4, gap: 10 }}>
            <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: "0.75rem", color: "var(--text-3)" }}>
              <Calendar size={11} /> {createdDate}
            </span>
            {project.genre && (
              <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: "0.75rem", color: "var(--text-3)" }}>
                <Tag size={11} /> {project.genre}
              </span>
            )}
            {project.voice && (
              <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: "0.75rem", color: "var(--text-3)" }}>
                <Mic2 size={11} /> {project.voice}
              </span>
            )}
          </div>
        </div>

        {/* Action buttons */}
        <div className="row row-2" onClick={e => e.stopPropagation()}>
          <button className="btn btn-ghost btn-icon btn-sm" title="Rename" onClick={onStartRename}><Edit3 size={13} /></button>
          <button className="btn btn-danger btn-icon btn-sm" title="Delete" onClick={onDelete}><Trash2 size={13} /></button>
        </div>
      </div>

      {/* Stats row */}
      <div className="row row-2 row-wrap" style={{ marginBottom: 14, gap: 8 }}>
        <span className="badge badge-muted">
          <FileAudio size={10} /> {files.length} file{files.length !== 1 ? "s" : ""}
        </span>
        {hasSegs && <span className="badge badge-cyan"><AudioLines size={10} /> Segments ready</span>}
        {project.mood_tags?.length > 0 && project.mood_tags.slice(0, 3).map(t => (
          <span key={t} className="badge badge-violet" style={{ fontSize: "0.68rem" }}>{t}</span>
        ))}
      </div>

      {/* Audio files list */}
      {files.length > 0 && (
        <div style={{ borderTop: "1px solid var(--border-1)", paddingTop: 10, marginBottom: 14 }}
             onClick={e => e.stopPropagation()}>
          <div style={{ fontSize: "0.7rem", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600, marginBottom: 6 }}>
            Audio Files
          </div>
          <div className="stack" style={{ gap: 4 }}>
            {files.map(f => (
              <div key={f.id} style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "5px 10px",
                background: "var(--bg-input)", border: "1px solid var(--border-1)",
                borderRadius: "var(--radius-sm)",
              }}>
                <Music2 size={12} style={{ color: "var(--text-3)", flexShrink: 0 }} />
                <span style={{ flex: 1, fontSize: "0.82rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {f.name}
                </span>
                <span style={{ fontSize: "0.72rem", color: "var(--text-3)", whiteSpace: "nowrap", flexShrink: 0 }}>
                  {Math.round(f.bpm)} BPM · {f.key}
                  {f.segments?.length > 0 && ` · ${f.segments.length} segs`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Compare slot assignment + nav buttons */}
      <div className="row row-between row-wrap" style={{ gap: 8 }} onClick={e => e.stopPropagation()}>

        {/* Slot A / B / C buttons */}
        <div className="row row-2 row-wrap">
          <span style={{ fontSize: "0.72rem", color: "var(--text-3)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Compare:
          </span>
          {[0, 1, 2].map(i => {
            const filled = compareSlots[i]?.projectId === project.id;
            return (
              <button
                key={i}
                className="btn btn-sm"
                style={{
                  padding: "4px 10px",
                  borderRadius: "var(--radius-pill)",
                  border: `1px solid ${filled ? SLOT_COLORS[i] : "var(--border-2)"}`,
                  background: filled ? SLOT_COLORS[i] + "18" : "var(--bg-input)",
                  color: filled ? SLOT_COLORS[i] : "var(--text-2)",
                  fontSize: "0.78rem",
                  fontWeight: 700,
                  gap: 4,
                }}
                onClick={e => {
                  if (filled) onClearSlot(e, i);
                  else onAssignSlot(e, i);
                }}
                title={filled ? `Clear Slot ${SLOT_LABELS[i]}` : `Add to Slot ${SLOT_LABELS[i]}`}
              >
                {filled && <Check size={11} />}
                Slot {SLOT_LABELS[i]}
              </button>
            );
          })}
        </div>

        {/* Open buttons */}
        <div className="row row-2">
          <button
            className="btn btn-secondary btn-sm"
            onClick={onMixLab}
          >
            <Layers size={13} /> Open in MixLab
          </button>
          <button className="btn btn-primary btn-sm" onClick={onOpen}>
            Open <ChevronRight size={13} />
          </button>
        </div>
      </div>
    </div>
  );
}
