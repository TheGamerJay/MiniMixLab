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

function SegmentCard({ seg, onPreview }) {
  const dur = (seg.end - seg.start).toFixed(1);
  return (
    <div className="p-2 rounded-lg bg-white/5 hover:bg-white/10 cursor-grab">
      <div className="text-xs opacity-70">{seg.label} • {dur}s</div>
      <div className="flex gap-2 mt-1">
        <button className="text-xs underline" onClick={onPreview}>Preview</button>
      </div>
    </div>
  );
}

function SortablePiece({ piece, index, onRemove }){
  const {attributes, listeners, setNodeRef, transform, transition} = useSortable({id: piece.id});
  const style = { transform: CSS.Transform.toString(transform), transition };
  const dur = (piece.end - piece.start).toFixed(1);
  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}
         className="p-2 rounded bg-cyan-500/10 flex items-center justify-between">
      <div className="text-sm">
        <div>{piece.label || "Section"} — {dur}s</div>
        <div className="text-xs opacity-70 mt-1">
          {(piece.end - piece.start).toFixed(1)}s • speed {(piece.speed ?? 1).toFixed(2)}× • pitch {(piece.pitch ?? 0)} st
        </div>
        <span className="opacity-60 text-xs">{piece.name}</span>
      </div>
      <button className="text-xs underline" onClick={()=>onRemove(index)}>remove</button>
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
    const url = previewUrl(file_id, seg.start, seg.end, 1.0);
    const el = audioRef.current; el.src = url; el.load(); el.play();
  }

  function addSegToTimeline(song, seg){
    setTimeline(t => [...t, {
      id: crypto.randomUUID(),
      file_id: song.file_id,
      name: song.name,
      start: seg.start, end: seg.end,
      speed: 1.0, gain: -3.0, label: seg.label,
      pitch: 0
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

  async function onRenderArrangement(){
    if (!timeline.length) return;
    const pieces = timeline.map(p => ({
      file_id: p.file_id,
      start: p.start,
      end: p.end,
      speed: p.speed ?? 1.0,
      gain: p.gain ?? -3.0,
      pitch: p.pitch ?? 0
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
    <div className="min-h-screen bg-[#0b0b11] text-slate-100 p-6">
      <h1 className="text-3xl font-bold">MiniMixLab — Section Builder</h1>

      <div className="mt-4 flex flex-wrap gap-3 items-center text-sm">
        <input type="file" accept="audio/*" onChange={onUpload}/>

        <label>Project BPM</label>
        <input type="number" className="text-black w-20" value={project.bpm} onChange={updateProjectBPM}/>

        <label>Key</label>
        <select className="text-black" value={project.key} onChange={updateProjectKey}>
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

        <label>Crossfade (ms)</label>
        <input type="number" className="text-black w-20" value={xfade} onChange={e=>setXfade(+e.target.value)}/>

        <label>Beats/Bar</label>
        <input type="number" className="text-black w-16" value={beatsPerBar} onChange={e=>setBeatsPerBar(+e.target.value || 4)} />

        <label className="flex items-center gap-1">
          <input type="checkbox" checked={barAware} onChange={e=>setBarAware(e.target.checked)} />
          Bar-aware
        </label>

        <label className="flex items-center gap-1">
          <input type="checkbox" checked={snapBars} onChange={e=>setSnapBars(e.target.checked)} />
          Snap to bars
        </label>

        <label className="flex items-center gap-1">
          <input type="checkbox" checked={hqPitch} onChange={e=>setHqPitch(e.target.checked)} />
          HQ Pitch
        </label>
      </div>

      <div className="mt-4 flex flex-wrap gap-3">
        <button className="px-3 py-2 rounded bg-cyan-500/20 hover:bg-cyan-500/30"
                onClick={()=>lineUpTimeline({ snap: true, beatsPerBar })}>
          Line Up (match BPM + snap)
        </button>

        <button className="px-3 py-2 rounded bg-cyan-500/20 hover:bg-cyan-500/30"
                onClick={onPitchMatch}>
          Pitch-match to {project.key}
        </button>

        <button className="px-3 py-2 rounded bg-cyan-500/20 hover:bg-cyan-500/30"
                onClick={onRenderArrangement}>
          Render Arrangement
        </button>
      </div>

      <div className="grid md:grid-cols-2 gap-6 mt-6">
        {/* Left: Segment libraries for each uploaded song */}
        <div>
          <h3 className="font-semibold mb-2">Segment Libraries</h3>
          <div className="space-y-4">
            {uploaded.map(song => (
              <div key={song.file_id} className="border border-white/10 rounded-lg p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-mono">{song.name}</div>
                    {song.analysis && (
                      <div className="text-xs opacity-80">
                        BPM: {song.analysis.bpm.toFixed(1)} • Key: {song.analysis.key}
                      </div>
                    )}
                  </div>
                  <button className="text-xs underline" onClick={()=>setActiveSong(song.file_id)}>
                    {activeSong===song.file_id ? "active" : "set active"}
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-2 mt-2">
                  {song.segments?.map((seg, idx) => (
                    <div key={idx} onDoubleClick={()=>addSegToTimeline(song, seg)}>
                      <SegmentCard seg={seg} onPreview={()=>previewSeg(song.file_id, seg)} />
                      <div className="text-[10px] opacity-60 mt-1">double-click to add</div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4">
            <audio ref={audioRef} controls preload="none" className="w-full"/>
          </div>
        </div>

        {/* Right: Timeline (draggable) */}
        <div>
          <h3 className="font-semibold mb-2">Timeline</h3>
          <DndContext collisionDetection={closestCenter} onDragEnd={onDragEnd}>
            <SortableContext items={timeline.map(x=>x.id)} strategy={verticalListSortingStrategy}>
              <div className="space-y-2">
                {timeline.map((p, idx) => (
                  <SortablePiece key={p.id} piece={p} index={idx} onRemove={removeFromTimeline}/>
                ))}
              </div>
            </SortableContext>
          </DndContext>
          {!timeline.length && <div className="opacity-60 text-sm mt-2">
            Tip: double-click any segment to add it here, then drag to reorder.
          </div>}
        </div>
      </div>
    </div>
  );
}

export default function App(){ return <ErrorBoundary><AppInner/></ErrorBoundary>; }