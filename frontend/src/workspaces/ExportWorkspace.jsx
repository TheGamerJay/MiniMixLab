import React, { useState } from "react";
import {
  Download, FileAudio, Settings2, Loader2,
  CheckCircle2, AlertTriangle, Music2, Clock
} from "lucide-react";
import { useProject } from "../contexts/ProjectContext";
import axios from "axios";

const FORMATS   = ["MP3 (320kbps)", "MP3 (192kbps)", "WAV (16-bit)", "WAV (24-bit)", "FLAC"];
const FADE_OPTS = ["None", "0.5s", "1s", "2s", "3s"];

export default function ExportWorkspace() {
  const { activeProject, activeProjectId, toast } = useProject();
  const [format, setFormat]       = useState("MP3 (320kbps)");
  const [fadeOut, setFadeOut]     = useState("2s");
  const [normalize, setNormalize] = useState(true);
  const [rendering, setRendering] = useState(false);
  const [rendered, setRendered]   = useState(null);   // { url, filename }

  const project = activeProject;
  const items   = project?.timelineItems ?? [];
  const tracks  = project?.mixLabTracks ?? [];
  const hasTimeline = items.length > 0;

  async function handleExport() {
    if (!hasTimeline) {
      toast("Build a timeline in MixLab first", "error");
      return;
    }

    setRendering(true);
    setRendered(null);

    try {
      const payload = {
        bpm:       project.targetBpm ?? 120,
        key:       project.targetKey ?? "Am",
        normalize,
        fade_out:  parseFade(fadeOut),
        items:     items.map(i => ({
          file_id:  i.fileId,
          start:    i.start,
          end:      i.end,
          lane:     i.lane ?? 0,
        })),
      };

      const res = await axios.post("/api/arrange/render", payload, {
        responseType: "blob",
      });

      const blobUrl  = URL.createObjectURL(res.data);
      const filename = `${project.name ?? "mix"}_render.mp3`;
      setRendered({ url: blobUrl, filename });
      toast("Export ready!", "success");
    } catch (err) {
      toast("Export failed — check backend is running", "error");
    } finally {
      setRendering(false);
    }
  }

  function parseFade(val) {
    if (val === "None") return 0;
    return parseFloat(val.replace("s", "")) || 0;
  }

  return (
    <div className="page-wrap">
      <div className="ws-header">
        <h1><span className="grad-text-primary">Export</span></h1>
        <p style={{ marginTop: 4 }}>Render and download your final arrangement.</p>
      </div>

      {/* Status card */}
      {!project ? (
        <div className="empty-state card">
          <div className="empty-icon"><Download size={22} /></div>
          <h3>No active project</h3>
          <p>Open or create a project first.</p>
        </div>
      ) : (
        <div className="grid-2" style={{ gap: 20 }}>
          {/* Left: settings */}
          <div className="stack stack-4">
            <div className="card stack stack-4">
              <div className="row row-3">
                <Settings2 size={15} style={{ color: "var(--text-2)" }} />
                <span style={{ fontWeight: 700, fontSize: "1rem" }}>Export Settings</span>
              </div>

              <div className="form-group">
                <label className="label">Format</label>
                <select className="select" value={format} onChange={e => setFormat(e.target.value)}>
                  {FORMATS.map(f => <option key={f} value={f}>{f}</option>)}
                </select>
              </div>

              <div className="form-group">
                <label className="label">Fade Out</label>
                <select className="select" value={fadeOut} onChange={e => setFadeOut(e.target.value)}>
                  {FADE_OPTS.map(f => <option key={f} value={f}>{f}</option>)}
                </select>
              </div>

              <label className="toggle-wrap" onClick={() => setNormalize(n => !n)}>
                <div>
                  <div className="toggle-label">Normalize Audio</div>
                  <div className="toggle-sub">Auto-level peaks to -1 dBFS</div>
                </div>
                <div className="toggle">
                  <input type="checkbox" checked={normalize} readOnly />
                  <span className="toggle-track" />
                  <span className="toggle-thumb" />
                </div>
              </label>
            </div>

            {/* Project summary */}
            <div className="card stack stack-3">
              <span style={{ fontWeight: 700, fontSize: "0.9rem" }}>Project Summary</span>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                {[
                  { label: "Project", value: project.name },
                  { label: "BPM", value: project.targetBpm ?? 120 },
                  { label: "Key", value: project.targetKey ?? "Am" },
                  { label: "Tracks", value: `${tracks.length} in MixLab` },
                  { label: "Timeline", value: `${items.length} segments` },
                ].map(({ label, value }) => (
                  <div key={label} style={{
                    background: "var(--bg-input)",
                    border: "1px solid var(--border-1)",
                    borderRadius: "var(--radius-sm)",
                    padding: "8px 10px",
                  }}>
                    <div style={{ fontSize: "0.7rem", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 2 }}>{label}</div>
                    <div style={{ fontWeight: 600, fontSize: "0.88rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{String(value)}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right: export action */}
          <div className="stack stack-4">
            {/* Timeline preview */}
            <div className="card" style={{ padding: 16 }}>
              <div className="row row-3" style={{ marginBottom: 12 }}>
                <Clock size={14} style={{ color: "var(--text-2)" }} />
                <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>Timeline preview</span>
              </div>

              {!hasTimeline ? (
                <div style={{
                  padding: "24px",
                  textAlign: "center",
                  border: "1px dashed var(--border-2)",
                  borderRadius: "var(--radius-md)",
                }}>
                  <AlertTriangle size={22} style={{ color: "var(--amber)", margin: "0 auto 8px" }} />
                  <div style={{ fontSize: "0.875rem", color: "var(--text-2)" }}>
                    No timeline items. Build your arrangement in MixLab first.
                  </div>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {items.map((item, i) => {
                    const colorMap = {
                      "tl-Intro":   "var(--cyan)",
                      "tl-Verse":   "var(--indigo)",
                      "tl-Chorus":  "var(--pink)",
                      "tl-Bridge":  "var(--amber)",
                      "tl-Rap":     "var(--violet)",
                      "tl-Outro":   "var(--teal)",
                    };
                    const col = colorMap[item.color] ?? "var(--text-3)";
                    return (
                      <div key={item.id} style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        padding: "5px 10px",
                        background: "var(--bg-input)",
                        border: "1px solid var(--border-1)",
                        borderRadius: "var(--radius-sm)",
                      }}>
                        <div style={{ width: 8, height: 8, borderRadius: "50%", background: col, flexShrink: 0 }} />
                        <span style={{ fontSize: "0.82rem", fontWeight: 600 }}>{item.label}</span>
                        <span style={{ fontSize: "0.75rem", color: "var(--text-3)", flex: 1 }}>
                          {item.trackName}
                        </span>
                        <span style={{ fontSize: "0.75rem", color: "var(--text-3)" }}>
                          {formatDuration(item.start)} – {formatDuration(item.end)}
                        </span>
                        <Music2 size={11} style={{ color: "var(--text-3)" }} />
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Export button */}
            <button
              className="btn btn-primary btn-lg"
              style={{ width: "100%" }}
              onClick={handleExport}
              disabled={rendering || !hasTimeline}
            >
              {rendering ? (
                <><Loader2 size={18} className="spin" /> Rendering...</>
              ) : (
                <><Download size={18} /> Export Mix</>
              )}
            </button>

            {/* Download result */}
            {rendered && (
              <div className="card" style={{
                borderColor: "rgba(34,197,94,0.35)",
                boxShadow: "0 0 0 1px rgba(34,197,94,0.2)",
                padding: 16,
              }}>
                <div className="row row-3" style={{ marginBottom: 12 }}>
                  <CheckCircle2 size={16} style={{ color: "var(--green)" }} />
                  <span style={{ fontWeight: 700 }}>Export Ready</span>
                </div>
                <a
                  href={rendered.url}
                  download={rendered.filename}
                  className="btn btn-neon"
                  style={{ width: "100%", textAlign: "center", display: "flex", justifyContent: "center" }}
                >
                  <Download size={16} />
                  Download {rendered.filename}
                </a>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function formatDuration(secs) {
  if (!secs && secs !== 0) return "";
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
