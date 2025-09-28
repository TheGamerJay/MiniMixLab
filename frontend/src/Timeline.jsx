import React, { useMemo, useRef } from "react";

/**
 * Safer DnD timeline:
 * - Only accepts drops that originate from our palette and were actually dragged.
 * - Adds click-to-place fallback: select chip, then click a bar.
 */
export default function Timeline({
  projectBpm,
  bars = 32,
  tracks,
  items,
  onDropSection,
  onRemoveItem,
  selected,            // { trackIdx, section } | null
  setSelected          // fn
}){
  const barSeconds = useMemo(()=> (60/projectBpm)*4, [projectBpm]);
  const draggingRef = useRef(false);          // was a real drag started?
  const dragMovedRef = useRef(false);         // passed threshold
  const startXY = useRef({x:0,y:0});

  function onDragStart(e, payload){
    draggingRef.current = true;
    dragMovedRef.current = false;
    startXY.current = { x: e.clientX, y: e.clientY };
    e.dataTransfer.setData("application/json", JSON.stringify(payload));
    e.dataTransfer.effectAllowed = "copy";
  }
  function onDrag(e){
    if (!draggingRef.current) return;
    const dx = Math.abs(e.clientX - startXY.current.x);
    const dy = Math.abs(e.clientY - startXY.current.y);
    if (dx + dy > 6) dragMovedRef.current = true;  // tiny threshold
  }
  function onDragEnd(){
    draggingRef.current = false;
    dragMovedRef.current = false;
  }
  function onDragOver(e){ e.preventDefault(); }
  function onDrop(e, barIndex){
    e.preventDefault();
    // Accept only real drags from our palette
    if (!draggingRef.current || !dragMovedRef.current) return;
    if (!e.dataTransfer.types.includes("application/json")) return;
    const data = e.dataTransfer.getData("application/json");
    if(!data) return;
    const { trackIdx, section } = JSON.parse(data);
    onDropSection(trackIdx, section, barIndex);
  }

  // Click-to-place (fallback): select a chip, then click a bar
  function onBarClick(i){
    if (!selected) return;
    onDropSection(selected.trackIdx, selected.section, i);
    setSelected(null);
  }

  return (
    <div className="timeline">
      <div className="bars">
        {Array.from({length: bars}).map((_,i)=>(
          <div key={i}
               className="bar"
               onDragOver={onDragOver}
               onDrop={(e)=>onDrop(e,i)}
               onClick={()=>onBarClick(i)}>
            <span className="bar-num">{i+1}</span>
          </div>
        ))}
      </div>

      <div className="palette">
        {tracks.map((t, ti)=>(
          <div key={t.name} className="pal-track">
            <div className="pal-title">{t.name}</div>
            <div className="pal-sections">
              {t.sections.map((s, si)=>{
                const isSel = selected && selected.trackIdx===ti && selected.section.start===s.start && selected.section.end===s.end;
                return (
                  <div key={si}
                       draggable
                       onDragStart={(e)=>onDragStart(e, { trackIdx: ti, section: s })}
                       onDrag={(e)=>onDrag(e)}
                       onDragEnd={onDragEnd}
                       onClick={() => setSelected(isSel ? null : { trackIdx: ti, section: s })}
                       className={`pal-chip ${isSel ? "active" : ""}`}
                       title={`Drag or click to select, then click a bar`}>
                    ⠿ {s.label} ({s.start.toFixed(1)}–{s.end.toFixed(1)})
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="placed">
        {items.map((it, i)=>(
          <div key={i} className="placed-item" style={{ left: `${(it.at_bar)*100/bars}%`}}>
            <span className="placed-tag">
              {it.label ?? "Section"} @ bar {it.at_bar+1}
            </span>
            <button onClick={()=>onRemoveItem(i)} className="placed-del">✕</button>
          </div>
        ))}
      </div>
    </div>
  );
}