import React from "react";

export default function ItemsPanel({
  items, setItems, tracks,
  onRemoveItem
}){
  function update(i, patch){
    setItems(prev => prev.map((it, k) => k===i ? ({...it, ...patch}) : it));
  }

  function replaceWith(i, trackIdx, sectionIdx){
    const t = tracks[trackIdx];
    const s = t.sections[sectionIdx];
    update(i, {
      label: `${t.name.split('.').slice(0,-1).join('.')}:${s.label}`,
      file_hash: t.hash,
      start: s.start,
      end: s.end,
      source_bpm: t.bpm,
      semitones: 0
    });
  }

  return (
    <div className="panel">
      <h3 style={{marginTop:0}}>Section Editor</h3>
      {items.length===0 && <div className="legend">Drop sections into the timeline to edit them.</div>}
      {items.map((it, i)=>(
        <div key={i} className="card" style={{marginBottom:10}}>
          <div className="row" style={{gap:10}}>
            <strong>{it.label ?? "Section"} @ bar {it.at_bar+1}</strong>
            <button className="placed-del" onClick={()=>onRemoveItem(i)}>Remove</button>
          </div>

          {/* Replace Section */}
          <div className="row" style={{gap:8}}>
            <span>Replace with:</span>
            <select onChange={e=>update(i, { __repTrack: Number(e.target.value), __repSection: 0 })}>
              <option value="">Select track</option>
              {tracks.map((t, ti)=>(<option key={t.name} value={ti}>{t.name}</option>))}
            </select>
            <select
              onChange={e=>{
                const ti = it.__repTrack ?? 0;
                const si = Number(e.target.value);
                if (!tracks[ti]) return;
                replaceWith(i, ti, si);
              }}>
              <option value="">Select section</option>
              {(tracks[it.__repTrack ?? 0]?.sections || []).map((s, si)=>(
                <option key={si} value={si}>{s.label} ({s.start.toFixed(1)}–{s.end.toFixed(1)})</option>
              ))}
            </select>
          </div>

          {/* Crop (start/end) */}
          <div className="row" style={{gap:8}}>
            <label>Start (s)
              <input type="number" value={Number(it.start).toFixed(2)}
                     onChange={e=>update(i, {start: Number(e.target.value)})} style={{width:80}}/>
            </label>
            <label>End (s)
              <input type="number" value={Number(it.end).toFixed(2)}
                     onChange={e=>update(i, {end: Number(e.target.value)})} style={{width:80}}/>
            </label>
            <span className="legend">Adjust to crop this placed section.</span>
          </div>

          {/* Extend (loop) + Transpose */}
          <div className="row" style={{gap:8}}>
            <label>Loop ×
              <input type="number" min="1" value={it.loop_times ?? 1}
                     onChange={e=>update(i, {loop_times: Math.max(1, Number(e.target.value))})}
                     style={{width:70}}/>
            </label>
            <label>Semitones
              <input type="number" value={it.semitones ?? 0}
                     onChange={e=>update(i, {semitones: Number(e.target.value)})}
                     style={{width:70}}/>
            </label>
          </div>
        </div>
      ))}
    </div>
  );
}