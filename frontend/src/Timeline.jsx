import React, { useMemo } from "react";

/**
 * Minimal timeline (4/4 bars)
 * Props:
 *  - projectBpm, bars, tracks, items
 *  - onDropSection(trackIdx, section, barIndex)
 *  - onRemoveItem(index)
 */
export default function Timeline({
  projectBpm, bars = 32, tracks, items,
  onDropSection, onRemoveItem
}){
  const barSeconds = useMemo(()=> (60/projectBpm)*4, [projectBpm]);

  function onDragStart(e, payload){
    e.dataTransfer.setData("application/json", JSON.stringify(payload));
    e.dataTransfer.effectAllowed = "copy";
  }
  function onDragOver(e){ e.preventDefault(); }
  function onDrop(e, barIndex){
    e.preventDefault();
    const data = e.dataTransfer.getData("application/json");
    if(!data) return;
    const { trackIdx, section } = JSON.parse(data);
    onDropSection(trackIdx, section, barIndex);
  }

  return (
    <div className="timeline">
      <div className="bars" style={{gridTemplateColumns:`repeat(${bars},1fr)`}}>
        {Array.from({length: bars}).map((_,i)=>(
          <div key={i} className="bar" onDragOver={onDragOver} onDrop={(e)=>onDrop(e,i)}>
            <span className="bar-num">{i+1}</span>
          </div>
        ))}
      </div>

      <div className="palette">
        {tracks.map((t, ti)=>(
          <div key={t.name} className="pal-track">
            <div className="pal-title">{t.name}</div>
            <div className="pal-sections">
              {t.sections.map((s, si)=>(
                <div key={si} draggable
                  onDragStart={(e)=>onDragStart(e, { trackIdx: ti, section: s })}
                  className="pal-chip" title={`Drag ${s.label} to a bar`}>
                  ⠿ {s.label} ({s.start.toFixed(1)}–{s.end.toFixed(1)})
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="placed">
        {items.map((it, i)=>(
          <div key={i} className="placed-item" style={{ left: `${(it.at_bar)*100/bars}%`}}>
            <span className="placed-tag">{it.label ?? "Section"} @ {it.at_bar+1}</span>
            <button onClick={()=>onRemoveItem(i)} className="placed-del">✕</button>
          </div>
        ))}
      </div>
    </div>
  );
}