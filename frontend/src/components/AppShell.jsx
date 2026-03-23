import React, { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Mic2, Layers, Library, Download, Plus, ChevronDown, X, Check, Disc3 } from "lucide-react";
import { useProject } from "../contexts/ProjectContext";
import logoImage from "../assets/MiniMixLabLogo.png";

const TABS = [
  { to: "/create",  label: "Create",  icon: Mic2 },
  { to: "/mixlab",  label: "MixLab",  icon: Layers },
  { to: "/library", label: "Library", icon: Library },
  { to: "/export",  label: "Export",  icon: Download },
];

// Slot label colours
const SLOT_COLORS = ["var(--cyan)", "var(--pink)", "var(--amber)"];
const SLOT_LABELS = ["A", "B", "C"];

export default function AppShell() {
  const { projects, activeProject, activeProjectId, compareSlots,
          createProject, selectProject, clearCompareSlot, toasts } = useProject();
  const navigate = useNavigate();
  const [projectMenuOpen, setProjectMenuOpen] = useState(false);

  function handleNewProject() {
    createProject();
    setProjectMenuOpen(false);
    navigate("/create");
  }

  function handleSelectProject(id) {
    selectProject(id);
    setProjectMenuOpen(false);
  }

  const filledSlots = compareSlots.filter(Boolean).length;

  return (
    <>
      {/* ── Top nav ─────────────────────────────────────────── */}
      <nav className="nav">
        {/* Logo */}
        <NavLink to="/create" className="nav-logo" style={{ textDecoration: "none" }}>
          <img src={logoImage} alt="Mini Mix Lab"
               onError={e => { e.target.style.display = "none"; }} />
          <span className="nav-logo-text">Mini Mix Lab</span>
        </NavLink>

        {/* Workspace tabs */}
        <div className="nav-tabs">
          {TABS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to} to={to}
              className={({ isActive }) => `nav-tab${isActive ? " active" : ""}`}
              style={{ textDecoration: "none" }}
            >
              <Icon /><span>{label}</span>
            </NavLink>
          ))}
        </div>

        {/* Right — compare slot indicators + project picker */}
        <div className="nav-right">
          {/* Compare slot pills */}
          {filledSlots > 0 && (
            <div className="row row-2" style={{ marginRight: 4 }}>
              {compareSlots.map((slot, i) => slot && (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                    padding: "4px 8px",
                    borderRadius: "var(--radius-pill)",
                    background: "var(--bg-card-2)",
                    border: `1px solid ${SLOT_COLORS[i]}44`,
                    fontSize: "0.72rem",
                    color: SLOT_COLORS[i],
                    fontWeight: 700,
                    cursor: "pointer",
                  }}
                  title={`Slot ${SLOT_LABELS[i]}: ${slot.trackName} — ${slot.projectTitle}`}
                >
                  <span style={{
                    width: 14, height: 14, borderRadius: "50%",
                    background: SLOT_COLORS[i] + "33",
                    border: `1px solid ${SLOT_COLORS[i]}`,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: "0.65rem", flexShrink: 0,
                  }}>
                    {SLOT_LABELS[i]}
                  </span>
                  <span style={{ maxWidth: 72, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {slot.trackName}
                  </span>
                  <button
                    style={{ background: "none", border: "none", cursor: "pointer",
                             color: "inherit", opacity: 0.6, padding: 0, display: "flex" }}
                    onClick={() => clearCompareSlot(i)}
                    title="Clear slot"
                  >
                    <X size={10} />
                  </button>
                </div>
              ))}
              <button
                className="btn btn-primary btn-sm"
                style={{ padding: "4px 10px", fontSize: "0.78rem" }}
                onClick={() => navigate("/mixlab")}
                title="Open compare slots in MixLab"
              >
                <Layers size={12} /> Mix
              </button>
            </div>
          )}

          {/* Project selector */}
          <div style={{ position: "relative" }}>
            <button
              className="btn btn-secondary btn-sm"
              style={{ gap: 6 }}
              onClick={() => setProjectMenuOpen(o => !o)}
            >
              <Disc3 size={13} style={{ color: "var(--indigo)", flexShrink: 0 }} />
              <span style={{
                maxWidth: 120, overflow: "hidden",
                textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--text-1)",
              }}>
                {activeProject?.title ?? "No project"}
              </span>
              <ChevronDown size={13} style={{ color: "var(--text-2)", flexShrink: 0 }} />
            </button>

            {projectMenuOpen && (
              <ProjectMenu
                projects={projects}
                activeId={activeProjectId}
                onSelect={handleSelectProject}
                onNew={handleNewProject}
                onClose={() => setProjectMenuOpen(false)}
              />
            )}
          </div>

          <button className="btn btn-primary btn-sm btn-icon" title="New project" onClick={handleNewProject}>
            <Plus size={15} />
          </button>
        </div>
      </nav>

      <main className="app-main"><Outlet /></main>

      {/* Toasts */}
      <div className="toast-stack">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.type}`}>
            {t.type === "success" && <Check size={14} style={{ color: "var(--green)", flexShrink: 0 }} />}
            {t.type === "error"   && <X    size={14} style={{ color: "var(--red)",   flexShrink: 0 }} />}
            <span>{t.msg}</span>
          </div>
        ))}
      </div>
    </>
  );
}

function ProjectMenu({ projects, activeId, onSelect, onNew, onClose }) {
  React.useEffect(() => {
    const h = (e) => { if (!e.target.closest(".proj-menu")) onClose(); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [onClose]);

  return (
    <div className="proj-menu" style={{
      position: "absolute", top: "calc(100% + 8px)", right: 0,
      minWidth: 230, background: "var(--bg-card-2)",
      border: "1px solid var(--border-3)", borderRadius: "var(--radius-lg)",
      padding: "6px", zIndex: 2000,
      boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
    }}>
      <div style={{ padding: "4px 10px 8px", borderBottom: "1px solid var(--border-1)", marginBottom: 6 }}>
        <span style={{ fontSize: "0.7rem", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600 }}>
          Projects
        </span>
      </div>
      <div style={{ maxHeight: 220, overflowY: "auto" }}>
        {projects.length === 0 && (
          <div style={{ padding: "10px", fontSize: "0.8rem", color: "var(--text-2)", textAlign: "center" }}>
            No projects yet
          </div>
        )}
        {projects.map(p => (
          <button key={p.id} onClick={() => onSelect(p.id)} style={{
            width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "8px 10px", borderRadius: "var(--radius-sm)", border: "none",
            background: p.id === activeId ? "var(--bg-active)" : "transparent",
            color: "var(--text-1)", fontSize: "0.85rem", cursor: "pointer", textAlign: "left",
          }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 160 }}>
                {p.title}
              </div>
              {p.genre && (
                <div style={{ fontSize: "0.72rem", color: "var(--text-3)", marginTop: 1 }}>
                  {p.genre} · {p.audioFiles?.length ?? 0} files
                </div>
              )}
            </div>
            {p.id === activeId && (
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--indigo)", flexShrink: 0 }} />
            )}
          </button>
        ))}
      </div>
      <div style={{ borderTop: "1px solid var(--border-1)", paddingTop: 6, marginTop: 6 }}>
        <button onClick={onNew} style={{
          width: "100%", display: "flex", alignItems: "center", gap: 8,
          padding: "8px 10px", borderRadius: "var(--radius-sm)", border: "none",
          background: "transparent", color: "var(--indigo)",
          fontSize: "0.85rem", cursor: "pointer", fontWeight: 600,
        }}>
          <Plus size={14} /> New project
        </button>
      </div>
    </div>
  );
}
