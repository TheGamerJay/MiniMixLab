import { useEffect, useRef, useState } from "react";
import io from "socket.io-client";
import {
  uploadFile, previewUrl, fetchSections, getProject,
  fetchSegments, renderArrangement
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
        {piece.label || "Section"} — {dur}s
        <span className="opacity-60 ml-2">{piece.name}</span>
      </div>
      <button className="text-xs underline" onClick={()=>onRemove(index)}>remove</button>
    </div>
  );
}

function AppInner(){
  const audioRef = useRef(null);
  const [uploaded, setUploaded] = useState([]); // {file_id,name,duration,segments?}
  const [activeSong, setActiveSong] = useState(null);
  const [timeline, setTimeline] = useState([]); // ordered chosen pieces
  const [xfade, setXfade] = useState(200);

  useEffect(() => { (async () => { await getProject(); await fetchSections(); })(); }, []);

  async function onUpload(e){
    const file = e.target.files?.[0]; if(!file) return;
    const meta = await uploadFile(file);
    const item = { ...meta, name: file.name };
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
      speed: 1.0, gain: -3.0, label: seg.label
    }]);
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
      file_id: p.file_id, start: p.start, end: p.end,
      speed: p.speed, gain: p.gain
    }));
    const { url } = await renderArrangement(pieces, xfade);
    window.open(url, "_blank");
  }

  const active = uploaded.find(u => u.file_id === activeSong);

  return (
    <div className="min-h-screen bg-[#0b0b11] text-slate-100 p-6">
      <h1 className="text-3xl font-bold">MiniMixLab — Section Builder</h1>

      <div className="mt-4 flex flex-wrap gap-3 items-center">
        <input type="file" accept="audio/*" onChange={onUpload}/>
        <label>Crossfade (ms)</label>
        <input type="number" className="text-black w-24" value={xfade} onChange={e=>setXfade(+e.target.value)}/>
        <button className="px-3 py-2 rounded bg-cyan-500/20" onClick={onRenderArrangement}>Render Arrangement</button>
      </div>

      <div className="grid md:grid-cols-2 gap-6 mt-6">
        {/* Left: Segment libraries for each uploaded song */}
        <div>
          <h3 className="font-semibold mb-2">Segment Libraries</h3>
          <div className="space-y-4">
            {uploaded.map(song => (
              <div key={song.file_id} className="border border-white/10 rounded-lg p-3">
                <div className="flex items-center justify-between">
                  <div className="font-mono">{song.name}</div>
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