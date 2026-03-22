import React, { createContext, useContext, useState, useEffect, useCallback } from "react";

// ── Project model ─────────────────────────────────────────────────────────────
// {
//   id, title, lyrics, voice, genre,
//   mood_tags: [],  production_notes: "",  secretWriter: "",
//   modelSize, instrumentalOnly,
//   audioFiles: [{ id, fileId, name, bpm, key, duration, segments[], createdAt, inMixLab }]
//   mixLabTracks: [],  timelineItems: [],  targetBpm, targetKey,
//   created_at, updated_at
// }
//
// compareSlots (global, not per-project):
//   [null | { projectId, fileId, trackName, projectTitle }, x3]

const CTX        = createContext(null);
const PROJ_KEY   = "mas_projects_v2";
const SLOTS_KEY  = "mas_compare_slots";
const ACTIVE_KEY = "mas_active_project";

function load(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; }
  catch { return fallback; }
}
function save(key, val) {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch {}
}
function newId() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

// ── Migration: convert v1 projects (name/voicePreset/tracks) → v2 ─────────────
function migrate(p) {
  return {
    ...p,
    title:            p.title            ?? p.name       ?? "Untitled Project",
    voice:            p.voice            ?? p.voicePreset ?? "neutral",
    audioFiles:       p.audioFiles       ?? p.tracks     ?? [],
    mood_tags:        p.mood_tags        ?? [],
    production_notes: p.production_notes ?? "",
    secretWriter:     p.secretWriter     ?? p.secretHelper ?? "",
  };
}

function loadProjects() {
  const raw = load(PROJ_KEY, null);
  // Also check old key
  const old = raw ?? load("mini_ai_studio_projects", []);
  return old.map(migrate);
}

export function ProjectProvider({ children }) {
  const [projects,         setProjects]         = useState(loadProjects);
  const [activeProjectId,  setActiveProjectId]  = useState(() => load(ACTIVE_KEY, null));
  const [compareSlots,     setCompareSlots]     = useState(() => load(SLOTS_KEY, [null, null, null]));
  const [toasts,           setToasts]           = useState([]);

  useEffect(() => { save(PROJ_KEY,   projects);        }, [projects]);
  useEffect(() => { save(ACTIVE_KEY, activeProjectId); }, [activeProjectId]);
  useEffect(() => { save(SLOTS_KEY,  compareSlots);    }, [compareSlots]);

  // Auto-select first project if active is gone
  useEffect(() => {
    if (projects.length > 0 && !projects.find(p => p.id === activeProjectId)) {
      setActiveProjectId(projects[0].id);
    }
  }, [projects, activeProjectId]);

  const activeProject = projects.find(p => p.id === activeProjectId) ?? null;

  // ── Toast ──────────────────────────────────────────────────────────────────
  const toast = useCallback((msg, type = "info") => {
    const id = newId();
    setToasts(t => [...t, { id, msg, type }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 3500);
  }, []);

  // ── Project CRUD ───────────────────────────────────────────────────────────
  const createProject = useCallback((title = "Untitled Project") => {
    const p = {
      id:               newId(),
      title,
      lyrics:           "",
      voice:            "neutral",
      genre:            "hip-hop",
      mood_tags:        [],
      production_notes: "",
      secretWriter:     "",
      modelSize:        "medium",
      instrumentalOnly: false,
      audioFiles:       [],
      mixLabTracks:     [],
      timelineItems:    [],
      targetBpm:        120,
      targetKey:        "Am",
      created_at:       new Date().toISOString(),
      updated_at:       new Date().toISOString(),
    };
    setProjects(prev => [p, ...prev]);
    setActiveProjectId(p.id);
    return p;
  }, []);

  const updateProject = useCallback((id, patch) => {
    setProjects(prev => prev.map(p =>
      p.id === id ? { ...p, ...patch, updated_at: new Date().toISOString() } : p
    ));
  }, []);

  const deleteProject = useCallback((id) => {
    setProjects(prev => prev.filter(p => p.id !== id));
    // Clear compare slots that referenced this project
    setCompareSlots(prev => prev.map(s => s?.projectId === id ? null : s));
    setActiveProjectId(prev => prev === id ? null : prev);
  }, []);

  const selectProject = useCallback((id) => setActiveProjectId(id), []);

  // ── Audio file CRUD ────────────────────────────────────────────────────────
  const addAudioFile = useCallback((projectId, fileData) => {
    const file = {
      id:        newId(),
      fileId:    fileData.fileId    ?? null,
      name:      fileData.name      ?? "Untitled",
      bpm:       fileData.bpm       ?? 120,
      key:       fileData.key       ?? "C",
      duration:  fileData.duration  ?? 0,
      segments:  fileData.segments  ?? [],
      createdAt: new Date().toISOString(),
      inMixLab:  false,
    };
    setProjects(prev => prev.map(p => {
      if (p.id !== projectId) return p;
      return { ...p, audioFiles: [...p.audioFiles, file], updated_at: new Date().toISOString() };
    }));
    return file;
  }, []);

  const updateAudioFile = useCallback((projectId, fileId, patch) => {
    setProjects(prev => prev.map(p => {
      if (p.id !== projectId) return p;
      return {
        ...p,
        audioFiles: p.audioFiles.map(f => f.id === fileId ? { ...f, ...patch } : f),
        updated_at: new Date().toISOString(),
      };
    }));
  }, []);

  const removeAudioFile = useCallback((projectId, fileId) => {
    setProjects(prev => prev.map(p => {
      if (p.id !== projectId) return p;
      return {
        ...p,
        audioFiles:   p.audioFiles.filter(f => f.id !== fileId),
        mixLabTracks: p.mixLabTracks.filter(id => id !== fileId),
        updated_at:   new Date().toISOString(),
      };
    }));
    // Remove from compare slots
    setCompareSlots(prev => prev.map(s =>
      s?.fileId === fileId && s?.projectId === projectId ? null : s
    ));
  }, []);

  // ── Compare slots ──────────────────────────────────────────────────────────
  const setCompareSlot = useCallback((slotIdx, data) => {
    // data: { projectId, fileId, trackName, projectTitle } | null
    setCompareSlots(prev => {
      const next = [...prev];
      next[slotIdx] = data;
      return next;
    });
  }, []);

  const clearCompareSlot = useCallback((slotIdx) => {
    setCompareSlots(prev => {
      const next = [...prev];
      next[slotIdx] = null;
      return next;
    });
  }, []);

  const addToCompareSlot = useCallback((projectId, audioFile) => {
    // Auto-picks the first empty slot; returns slot index or -1 if all full
    setCompareSlots(prev => {
      const idx = prev.findIndex(s => s === null);
      if (idx === -1) return prev;
      const next = [...prev];
      next[idx] = {
        projectId,
        fileId:       audioFile.id,
        backendFileId: audioFile.fileId,
        trackName:    audioFile.name,
        bpm:          audioFile.bpm,
        key:          audioFile.key,
        duration:     audioFile.duration,
        segments:     audioFile.segments,
        projectTitle: projects.find(p => p.id === projectId)?.title ?? "Project",
      };
      return next;
    });
  }, [projects]);

  // ── Send to MixLab (per-project track toggle) ──────────────────────────────
  const sendToMixLab = useCallback((projectId, audioFileId) => {
    setProjects(prev => prev.map(p => {
      if (p.id !== projectId) return p;
      const already = p.mixLabTracks.includes(audioFileId);
      if (already) return p;
      return {
        ...p,
        audioFiles:   p.audioFiles.map(f => f.id === audioFileId ? { ...f, inMixLab: true } : f),
        mixLabTracks: [...p.mixLabTracks, audioFileId],
        updated_at:   new Date().toISOString(),
      };
    }));
    toast("Track sent to MixLab", "success");
  }, [toast]);

  const removeFromMixLab = useCallback((projectId, audioFileId) => {
    setProjects(prev => prev.map(p => {
      if (p.id !== projectId) return p;
      return {
        ...p,
        audioFiles:   p.audioFiles.map(f => f.id === audioFileId ? { ...f, inMixLab: false } : f),
        mixLabTracks: p.mixLabTracks.filter(id => id !== audioFileId),
        updated_at:   new Date().toISOString(),
      };
    }));
  }, []);

  // ── Timeline ───────────────────────────────────────────────────────────────
  const addTimelineItem = useCallback((projectId, item) => {
    setProjects(prev => prev.map(p => {
      if (p.id !== projectId) return p;
      return {
        ...p,
        timelineItems: [...p.timelineItems, { id: newId(), ...item }],
        updated_at:    new Date().toISOString(),
      };
    }));
  }, []);

  const removeTimelineItem = useCallback((projectId, itemId) => {
    setProjects(prev => prev.map(p => {
      if (p.id !== projectId) return p;
      return {
        ...p,
        timelineItems: p.timelineItems.filter(i => i.id !== itemId),
        updated_at:    new Date().toISOString(),
      };
    }));
  }, []);

  const clearTimeline = useCallback((projectId) => {
    setProjects(prev => prev.map(p => {
      if (p.id !== projectId) return p;
      return { ...p, timelineItems: [], updated_at: new Date().toISOString() };
    }));
  }, []);

  return (
    <CTX.Provider value={{
      projects,
      activeProject,
      activeProjectId,
      compareSlots,
      // project ops
      createProject,
      updateProject,
      deleteProject,
      selectProject,
      // audio file ops
      addAudioFile,
      updateAudioFile,
      removeAudioFile,
      // compare slots
      setCompareSlot,
      clearCompareSlot,
      addToCompareSlot,
      // mixlab
      sendToMixLab,
      removeFromMixLab,
      // timeline
      addTimelineItem,
      removeTimelineItem,
      clearTimeline,
      // ui
      toast,
      toasts,
    }}>
      {children}
    </CTX.Provider>
  );
}

export function useProject() {
  const ctx = useContext(CTX);
  if (!ctx) throw new Error("useProject must be used inside ProjectProvider");
  return ctx;
}
