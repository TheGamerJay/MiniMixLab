import { useEffect, useRef, useState } from "react";
import io from "socket.io-client";
import {
  uploadFile, previewUrl, fetchSections, getProject, setProject,
  fetchSegments, renderArrangement, autoPitch
} from "./api";
import { DndContext, closestCenter } from "@dnd-kit/core";
import { SortableContext, arrayMove, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import ErrorBoundary from "./ErrorBoundary";
import logoImage from "./assets/MiniMixLabLogo.png";

function SegmentCard({ seg, onPreview }) {
  const dur = (seg.end - seg.start).toFixed(1);
  return (
    <div className="p-3 rounded-lg bg-gradient-to-r from-indigo-600/20 to-cyan-600/20 hover:from-indigo-500/30 hover:to-cyan-500/30 cursor-grab border border-indigo-400/20 hover:border-cyan-400/40 transition-all duration-200 group">
      <div className="text-sm font-medium text-cyan-200 mb-1">{seg.label}</div>
      <div className="text-xs text-gray-400 mb-2">Duration: {dur}s</div>
      <button
        className="text-xs bg-pink-500/20 hover:bg-pink-500/40 text-pink-300 px-2 py-1 rounded transition-colors"
        onClick={onPreview}
      >
        ▶ Preview
      </button>
    </div>
  );
}

function SortablePiece({ piece, index, onRemove, onUpdatePiece }){
  const {attributes, listeners, setNodeRef, transform, transition} = useSortable({id: piece.id});
  const style = { transform: CSS.Transform.toString(transform), transition };
  const dur = (piece.end - piece.start).toFixed(1);

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}
         className="p-4 rounded-xl bg-gradient-to-r from-pink-600/20 to-indigo-600/20 border border-pink-400/20 hover:border-pink-400/40 cursor-grab transition-all duration-200 group hover:shadow-lg">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-lg font-semibold text-pink-200">{piece.label || "Section"}</span>
            <span className="text-sm text-gray-400">({dur}s)</span>
          </div>

          <div className="text-xs text-gray-400 mb-2">
            <span className="inline-flex items-center gap-1">
              ⏱️ {(piece.end - piece.start).toFixed(1)}s
            </span>
            <span className="ml-3 inline-flex items-center gap-1">
              🚀 {(piece.speed ?? 1).toFixed(2)}×
            </span>
            <span className="ml-3 inline-flex items-center gap-1">
              🎹 {(piece.pitch ?? 0)} st
            </span>
          </div>

          <div className="text-xs text-cyan-300 mb-3 font-mono">{piece.name}</div>

          <div className="flex gap-3 items-center">
            <label className="text-xs text-gray-300 font-medium">Audio Preset:</label>
            <select
              className="text-xs px-2 py-1 bg-slate-700/50 border border-indigo-400/30 rounded text-white focus:border-pink-400 focus:ring-1 focus:ring-pink-400 transition-colors"
              value={piece.preset || "default"}
              onChange={e => onUpdatePiece(index, { preset: e.target.value })}
              onClick={e => e.stopPropagation()}
            >
              <option value="default">🎵 Default</option>
              <option value="vocals">🎤 Vocals</option>
              <option value="drums">🥁 Drums</option>
              <option value="pads">🎹 Pads</option>
            </select>
          </div>
        </div>

        <button
          className="ml-4 px-3 py-1 bg-red-500/20 hover:bg-red-500/40 text-red-300 text-xs rounded transition-colors"
          onClick={()=>onRemove(index)}
        >
          ✕ Remove
        </button>
      </div>
    </div>
  );
}

function AppInner(){
  const audioRef = useRef(null);
  const [uploaded, setUploaded] = useState([]); // {file_id,name,duration,segments?,analysis?}
  const [activeSong, setActiveSong] = useState(null);
  const [timeline, setTimeline] = useState([]); // ordered chosen pieces
  const [xfade, setXfade] = useState(200);
  const [project, setProjectState] = useState({ bpm: 120, key: "Am" });
  const [beatsPerBar, setBeatsPerBar] = useState(4);
  const [barAware, setBarAware] = useState(true);
  const [snapBars, setSnapBars] = useState(true);
  const [hqPitch, setHqPitch] = useState(true);

  // Beat/bar helpers using the Project BPM
  function secondsPerBeat(projectBpm){
    return 60 / Math.max(projectBpm || 120, 1e-6);
  }

  function quantizeLenToBeats(lenSec, projectBpm, beatsPerBar = 4){
    const spb = secondsPerBeat(projectBpm);
    const beats = Math.max(1, Math.round(lenSec / spb)); // at least 1 beat
    return beats * spb;
  }

  useEffect(() => { (async () => {
    const { sections } = await fetchSections();
    const p = await getProject();
    setProjectState(p);
  })(); }, []);

  async function onUpload(e){
    const file = e.target.files?.[0]; if(!file) return;
    const meta = await uploadFile(file);
    const item = { ...meta, name: file.name }; // meta.analysis contains bpm/key/first_beat
    // fetch segments for this song
    const { segments } = await fetchSegments(item.file_id);
    item.segments = segments;
    setUploaded(u => [...u, item]);
    setActiveSong(item.file_id);
  }

  function previewSeg(file_id, seg){
    // find current piece settings if previewing from timeline, else defaults
    const piece = timeline.find(p => p.file_id === file_id);
    const opts = {
      hq: hqPitch,
      pitch: piece?.pitch ?? 0,
      preset: piece?.preset ?? "default"
    };
    const url = previewUrl(file_id, seg.start, seg.end, 1.0, opts);
    const el = audioRef.current; el.src = url; el.load(); el.play();
  }

  function addSegToTimeline(song, seg){
    setTimeline(t => [...t, {
      id: crypto.randomUUID(),
      file_id: song.file_id,
      name: song.name,
      start: seg.start, end: seg.end,
      speed: 1.0, gain: -3.0, label: seg.label,
      pitch: 0, preset: "default"
    }]);
  }

  async function lineUpTimeline({ snap = true, beatsPerBar = 4 } = {}){
    if (!timeline.length) return;
    setTimeline(items => items.map(p => {
      const src = uploaded.find(u => u.file_id === p.file_id);
      const srcBpm = (src?.analysis?.bpm || project.bpm || 120);
      const speed = project.bpm / Math.max(srcBpm, 1e-6); // time-stretch to Project BPM

      // keep start/end time window but optionally quantize its duration to beat grid
      let start = p.start;
      let end = p.end;
      if (snap){
        const rawLen = Math.max(0.5, end - start);
        const snappedLen = quantizeLenToBeats(rawLen, project.bpm, beatsPerBar);
        end = start + snappedLen;
      }

      return { ...p, speed, start, end };
    }));
  }

  async function onPitchMatch(){
    if (!timeline.length) return;
    const ids = Array.from(new Set(timeline.map(t => t.file_id)));
    const { tracks } = await autoPitch(ids, project.key);
    setTimeline(items => items.map(p => {
      const m = tracks.find(t => t.file_id === p.file_id);
      return m ? { ...p, pitch: m.semitones } : { ...p, pitch: 0 };
    }));
  }

  function onDragEnd(event){
    const {active, over} = event;
    if (!over || active.id === over.id) return;
    const oldIndex = timeline.findIndex(x => x.id === active.id);
    const newIndex = timeline.findIndex(x => x.id === over.id);
    setTimeline(items => arrayMove(items, oldIndex, newIndex));
  }

  function removeFromTimeline(idx){
    setTimeline(t => t.filter((_,i)=>i!==idx));
  }

  function updatePiece(idx, updates){
    setTimeline(t => t.map((piece, i) => i === idx ? { ...piece, ...updates } : piece));
  }

  async function onRenderArrangement(){
    if (!timeline.length) return;
    const pieces = timeline.map(p => ({
      file_id: p.file_id,
      start: p.start,
      end: p.end,
      speed: p.speed ?? 1.0,
      gain: p.gain ?? -3.0,
      pitch: p.pitch ?? 0,
      preset: p.preset ?? "default"
    }));

    const { url } = await renderArrangement(pieces, {
      xfade_ms: xfade,
      bar_aware: barAware,
      project_bpm: project.bpm,
      beats_per_bar: beatsPerBar,
      snap_to_bars: snapBars,
      align_key: true,
      project_key: project.key,
      hq_pitch: hqPitch
    });
    window.open(url, "_blank");
  }

  async function updateProjectBPM(e){
    const bpm = +e.target.value;
    const p = await setProject(bpm, project.key);
    setProjectState(p);
  }

  async function updateProjectKey(e){
    const key = e.target.value;
    const p = await setProject(project.bpm, key);
    setProjectState(p);
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-950 via-slate-950 to-cyan-950 text-white">
      {/* Header Section */}
      <div className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-r from-indigo-600/20 via-pink-500/10 to-cyan-500/20"></div>
        <div className="relative z-10 flex flex-col items-center py-8 px-6">
          <h1 className="text-5xl font-bold bg-gradient-to-r from-indigo-400 via-pink-400 to-cyan-400 bg-clip-text text-transparent mb-4">
            MiniMixLab
          </h1>
          <img src={logoImage} alt="MiniMixLab Logo" className="h-24 w-auto drop-shadow-2xl" />
          <p className="text-gray-300 mt-2 text-center max-w-md">
            Professional audio mixing with AI-powered segmentation and beat matching
          </p>
        </div>
      </div>

      <div className="px-6 pb-8">
        {/* Control Panel */}
        <div className="bg-gradient-to-r from-indigo-900/40 to-cyan-900/40 backdrop-blur-sm border border-indigo-500/20 rounded-2xl p-6 mb-8 shadow-2xl">
          <h2 className="text-xl font-semibold text-indigo-200 mb-4 flex items-center gap-2">
            <span className="w-2 h-2 bg-pink-400 rounded-full"></span>
            Project Settings
          </h2>

          {/* File Upload */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-300 mb-2">Upload Audio File</label>
            <input
              type="file"
              accept="audio/*"
              onChange={onUpload}
              className="block w-full text-sm text-gray-300 file:mr-4 file:py-3 file:px-6 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-gradient-to-r file:from-indigo-600 file:to-cyan-600 file:text-white hover:file:from-indigo-700 hover:file:to-cyan-700 file:cursor-pointer file:shadow-lg"
            />
          </div>

          {/* Settings Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mb-6">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">Project BPM</label>
              <input
                type="number"
                className="w-full px-3 py-2 bg-slate-800/50 border border-indigo-500/30 rounded-lg text-white focus:border-pink-400 focus:ring-1 focus:ring-pink-400 transition-colors"
                value={project.bpm}
                onChange={updateProjectBPM}
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">Key</label>
              <select
                className="w-full px-3 py-2 bg-slate-800/50 border border-indigo-500/30 rounded-lg text-white focus:border-pink-400 focus:ring-1 focus:ring-pink-400 transition-colors"
                value={project.key}
                onChange={updateProjectKey}
              >
                <option value="C">C</option>
                <option value="C#">C#</option>
                <option value="D">D</option>
                <option value="D#">D#</option>
                <option value="E">E</option>
                <option value="F">F</option>
                <option value="F#">F#</option>
                <option value="G">G</option>
                <option value="G#">G#</option>
                <option value="A">A</option>
                <option value="A#">A#</option>
                <option value="B">B</option>
                <option value="Am">Am</option>
                <option value="Bm">Bm</option>
                <option value="Cm">Cm</option>
                <option value="Dm">Dm</option>
                <option value="Em">Em</option>
                <option value="Fm">Fm</option>
                <option value="Gm">Gm</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">Crossfade (ms)</label>
              <input
                type="number"
                className="w-full px-3 py-2 bg-slate-800/50 border border-indigo-500/30 rounded-lg text-white focus:border-pink-400 focus:ring-1 focus:ring-pink-400 transition-colors"
                value={xfade}
                onChange={e=>setXfade(+e.target.value)}
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">Beats/Bar</label>
              <input
                type="number"
                className="w-full px-3 py-2 bg-slate-800/50 border border-indigo-500/30 rounded-lg text-white focus:border-pink-400 focus:ring-1 focus:ring-pink-400 transition-colors"
                value={beatsPerBar}
                onChange={e=>setBeatsPerBar(+e.target.value || 4)}
              />
            </div>
          </div>

          {/* Toggles */}
          <div className="flex flex-wrap gap-6 mb-6">
            <label className="flex items-center gap-2 cursor-pointer group">
              <input
                type="checkbox"
                checked={barAware}
                onChange={e=>setBarAware(e.target.checked)}
                className="w-4 h-4 text-pink-500 bg-slate-800 border-indigo-500/30 rounded focus:ring-pink-400 focus:ring-2"
              />
              <span className="text-sm text-gray-300 group-hover:text-pink-300 transition-colors">Bar-aware</span>
            </label>

            <label className="flex items-center gap-2 cursor-pointer group">
              <input
                type="checkbox"
                checked={snapBars}
                onChange={e=>setSnapBars(e.target.checked)}
                className="w-4 h-4 text-pink-500 bg-slate-800 border-indigo-500/30 rounded focus:ring-pink-400 focus:ring-2"
              />
              <span className="text-sm text-gray-300 group-hover:text-pink-300 transition-colors">Snap to bars</span>
            </label>

            <label className="flex items-center gap-2 cursor-pointer group">
              <input
                type="checkbox"
                checked={hqPitch}
                onChange={e=>setHqPitch(e.target.checked)}
                className="w-4 h-4 text-pink-500 bg-slate-800 border-indigo-500/30 rounded focus:ring-pink-400 focus:ring-2"
              />
              <span className="text-sm text-gray-300 group-hover:text-pink-300 transition-colors">HQ Pitch</span>
            </label>
          </div>

          {/* Action Buttons */}
          <div className="flex flex-wrap gap-3">
            <button
              className="px-6 py-3 bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-700 hover:to-cyan-700 rounded-lg font-medium transition-all duration-200 shadow-lg hover:shadow-xl transform hover:scale-105"
              onClick={()=>lineUpTimeline({ snap: true, beatsPerBar })}
            >
              🎵 Line Up (match BPM + snap)
            </button>

            <button
              className="px-6 py-3 bg-gradient-to-r from-pink-600 to-indigo-600 hover:from-pink-700 hover:to-indigo-700 rounded-lg font-medium transition-all duration-200 shadow-lg hover:shadow-xl transform hover:scale-105"
              onClick={onPitchMatch}
            >
              🎹 Pitch-match to {project.key}
            </button>

            <button
              className="px-6 py-3 bg-gradient-to-r from-cyan-600 to-pink-600 hover:from-cyan-700 hover:to-pink-700 rounded-lg font-medium transition-all duration-200 shadow-lg hover:shadow-xl transform hover:scale-105"
              onClick={onRenderArrangement}
            >
              🎧 Render Arrangement
            </button>
          </div>
        </div>

        {/* Main Content Grid */}
        <div className="grid lg:grid-cols-2 gap-8">
          {/* Left: Segment Libraries */}
          <div className="space-y-6">
            <h3 className="text-2xl font-bold text-indigo-200 flex items-center gap-2">
              <span className="w-3 h-3 bg-cyan-400 rounded-full"></span>
              Segment Libraries
            </h3>

            <div className="space-y-4">
              {uploaded.map(song => (
                <div key={song.file_id} className="bg-gradient-to-r from-slate-800/50 to-slate-700/50 backdrop-blur-sm border border-cyan-500/20 rounded-xl p-4 shadow-xl">
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <div className="font-mono text-lg text-cyan-200">{song.name}</div>
                      {song.analysis && (
                        <div className="text-sm text-gray-400">
                          <span className="inline-flex items-center gap-1">
                            🎵 BPM: {song.analysis.bpm.toFixed(1)}
                          </span>
                          <span className="ml-3 inline-flex items-center gap-1">
                            🎹 Key: {song.analysis.key}
                          </span>
                        </div>
                      )}
                    </div>
                    <button
                      className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
                        activeSong === song.file_id
                          ? 'bg-pink-500 text-white shadow-lg'
                          : 'bg-slate-700 text-gray-300 hover:bg-pink-500/20 hover:text-pink-300'
                      }`}
                      onClick={()=>setActiveSong(song.file_id)}
                    >
                      {activeSong === song.file_id ? "✓ Active" : "Set Active"}
                    </button>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    {song.segments?.map((seg, idx) => (
                      <div key={idx} onDoubleClick={()=>addSegToTimeline(song, seg)} className="group">
                        <SegmentCard seg={seg} onPreview={()=>previewSeg(song.file_id, seg)} />
                        <div className="text-xs text-center text-gray-500 mt-1 group-hover:text-pink-400 transition-colors">
                          Double-click to add
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* Audio Player */}
            <div className="bg-slate-800/50 backdrop-blur-sm border border-indigo-500/20 rounded-xl p-4">
              <h4 className="text-sm font-medium text-indigo-200 mb-2">Preview Player</h4>
              <audio ref={audioRef} controls preload="none" className="w-full h-12 rounded-lg"/>
            </div>
          </div>

          {/* Right: Timeline */}
          <div className="space-y-6">
            <h3 className="text-2xl font-bold text-indigo-200 flex items-center gap-2">
              <span className="w-3 h-3 bg-pink-400 rounded-full"></span>
              Timeline
            </h3>

            <div className="bg-gradient-to-r from-slate-800/50 to-slate-700/50 backdrop-blur-sm border border-pink-500/20 rounded-xl p-4 min-h-[400px] shadow-xl">
              <DndContext collisionDetection={closestCenter} onDragEnd={onDragEnd}>
                <SortableContext items={timeline.map(x=>x.id)} strategy={verticalListSortingStrategy}>
                  <div className="space-y-3">
                    {timeline.map((p, idx) => (
                      <SortablePiece key={p.id} piece={p} index={idx} onRemove={removeFromTimeline} onUpdatePiece={updatePiece}/>
                    ))}
                  </div>
                </SortableContext>
              </DndContext>

              {!timeline.length && (
                <div className="flex flex-col items-center justify-center h-64 text-center">
                  <div className="text-6xl mb-4 opacity-20">🎵</div>
                  <div className="text-gray-400 text-lg mb-2">Your timeline is empty</div>
                  <div className="text-gray-500 text-sm max-w-sm">
                    Double-click any segment from the libraries to add it here, then drag to reorder your mix
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function App(){ return <ErrorBoundary><AppInner/></ErrorBoundary>; }