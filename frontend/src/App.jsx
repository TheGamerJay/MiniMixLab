import React, { useRef, useState } from "react";
import axios from "axios";
import Timeline from "./Timeline.jsx";
//  use the new compact editor instead of ItemsPanel
import SectionEditor from "./SectionEditor.jsx";
import "./SectionEditor.css";

function TrackCard({ track, idx, onMute, onSolo, onPlay, audioRef }) {
  return (
    <div className="card">
      <audio ref={audioRef} preload="metadata" />
      <div className="row">
        <strong>{track.name}</strong>
        <span>{Math.round(track.bpm)} BPM  {track.key}</span>
        <button className={track.muted ? "muted" : ""} onClick={() => onMute(idx)}>M</button>
        <button className={track.solo ? "solo" : ""} onClick={() => onSolo(idx)}>S</button>
      </div>
      <div className="chips">
        {track.sections.map((s, k) => (
          <button key={k} className="chip" onClick={() => onPlay(idx, s)}>
             {s.label} ({s.start.toFixed(1)}{s.end.toFixed(1)})
          </button>
        ))}
      </div>
    </div>
  );
}

export default function App(){
  const [tracks, setTracks] = useState([]);     // analyzed tracks
  const audioRefs = useRef({});
  const [projectBpm, setProjectBpm] = useState(88);
  const [bars, setBars] = useState(32);
  const [xfade, setXfade] = useState(120);
  const [masterFadeOut, setMasterFadeOut] = useState(0); // ms
  const [items, setItems] = useState([]);       // placed items on timeline
  const [renderUrl, setRenderUrl] = useState("");
  const [selected, setSelected] = useState(null); // for click-to-place
  const [autoImportMix, setAutoImportMix] = useState(true); // auto-import rendered mix as new track

  async function handleFiles(e){
    const files = Array.from(e.target.files).slice(0,3);
    if(files.length === 0) return;
    const fd = new FormData();
    files.forEach(f => fd.append("files", f));
    const { data } = await axios.post("/analyze/batch", fd);
    const enhanced = data.tracks.map((t, i) => ({
      ...t, muted:false, solo:false,
      file: files[i], url: URL.createObjectURL(files[i])
    }));
    setTracks(enhanced);
    setProjectBpm(Math.round(enhanced[0]?.bpm ?? projectBpm));
    setTimeout(() => {
      enhanced.forEach(t => {
        const a = audioRefs.current[t.name];
        if(a){ a.src = t.url; }
      });
    }, 0);
  }

  function toggleMute(i){
    setTracks(ts => ts.map((t, k) => k===i ? {...t, muted: !t.muted, solo:false} : t));
  }

  //  safe, simple version (no ternary), fixes build error
  function toggleSolo(i){
    setTracks(ts => {
      const isSolo = !ts[i].solo;
      return ts.map((t, k) => {
        if (k === i) return { ...t, solo: isSolo, muted: false };
        return { ...t, solo: false, muted: (isSolo || t.muted) };
      });
    });
  }

  function getGain(i){
    const anySolo = tracks.some(t=>t.solo);
    if(tracks[i].muted) return 0;
    if(anySolo && !tracks[i].solo) return 0;
    return 1;
  }

  async function audition(i, sec){
    try {
      Object.values(audioRefs.current).forEach(a => a?.pause());
      const t = tracks[i];
      if(!t) return;
      const a = audioRefs.current[t.name];
      if(!a){ console.warn("No <audio> ref"); return; }

      const payload = {
        file_hash: t.hash,
        start: sec.start,
        end: sec.end,
        target_bpm: t.bpm,
        source_bpm: t.bpm,
        semitones: 0
      };
      const res = await axios.post("/align/preview", payload, { responseType: "blob" });
      if (res.status !== 200) {
        console.error("Preview failed", res.status, res.data);
        alert("Preview failed. Check console/network tab.");
        return;
      }
      const url = URL.createObjectURL(new Blob([res.data], { type: "audio/wav" }));
      a.src = url;
      a.currentTime = 0;
      a.volume = 1;
      const playPromise = a.play();
      if (playPromise?.catch) {
        playPromise.catch(() => {
          alert("Browser blocked playback. Click anywhere in the page, then try again.");
        });
      }
    } catch (e) {
      console.error("audition() error", e);
      alert("Preview error  see console for details.");
    }
  }

  function onDropSection(trackIdx, section, barIndex){
    const t = tracks[trackIdx];
    if(!t) return;
    const it = {
      label: `${t.name.split('.').slice(0,-1).join('.')}:${section.label}`,
      file_hash: t.hash,
      start: section.start,
      end: section.end,
      source_bpm: t.bpm,
      semitones: 0,
      at_bar: barIndex,
      loop_times: 1
    };
    setItems(prev => [...prev, it]);
  }
  function onRemoveItem(i){ setItems(prev => prev.filter((_,k)=>k!==i)); }

  // render + optional auto-import of the rendered WAV as a new track
  async function renderFull(){
    if(items.length === 0) return;
    setRenderUrl("");

    const payload = {
      project_bpm: Number(projectBpm),
      crossfade_ms: Number(xfade),
      bars: Number(bars),
      master_fade_out_ms: Number(masterFadeOut),
      items: items.map(({label, ...keep})=>keep)
    };

    // 1) Render full mix
    const res = await axios.post("/arrange/render", payload, { responseType: "blob" });
    if (res.status !== 200) {
      alert("Render failed  see devtools Network tab");
      return;
    }
    const blob = res.data;
    const url = URL.createObjectURL(new Blob([blob], {type: "audio/wav"}));
    setRenderUrl(url);

    // 2) Auto-import rendered mix as a new track (4th song)
    if (autoImportMix) {
      try {
        const file = new File([blob], "MiniMixLab_mix.wav", { type: "audio/wav" });
        const fd = new FormData();
        fd.append("files", file);
        const { data } = await axios.post("/analyze/batch", fd);
        const newTracks = data.tracks.map(t => ({
          ...t, muted:false, solo:false, file, url
        }));
        setTracks(prev => [...prev, ...newTracks]);
      } catch (e) {
        console.error("Auto-import of rendered mix failed:", e);
      }
    }
  }

  return (
    <div className="wrap">
      <h1>MiniMixLab </h1>

      <div className="panel">
        <div className="controls">
          <label>Upload 13
            <input type="file" accept=".wav,.aiff,.aif,.mp3,.flac" multiple onChange={handleFiles}/>
          </label>

          <button onClick={()=>{
            const t = tracks[0];
            if(!t) return;
            const a = audioRefs.current[t.name];
            if(!a) return;
            a.src = t.url;  // play the local file directly
            a.play().catch(() => alert("Click anywhere on the page, then press again."));
          }}>Play Original</button>

          <label>Project BPM
            <input type="number" value={projectBpm} onChange={e=>setProjectBpm(e.target.value)} />
          </label>
          <label>Bars
            <input type="number" value={bars} onChange={e=>setBars(e.target.value)} />
          </label>
          <label>Crossfade (ms)
            <input type="number" value={xfade} onChange={e=>setXfade(e.target.value)} />
          </label>
          <label>Fade Out (ms)
            <input type="number" value={masterFadeOut} onChange={e=>setMasterFadeOut(e.target.value)} />
          </label>

          <label className="chip">
            <input
              type="checkbox"
              checked={autoImportMix}
              onChange={e=>setAutoImportMix(e.target.checked)}
            />
            Auto-import rendered mix as new track
          </label>

          <button onClick={renderFull} disabled={items.length===0}>Render Full Mix</button>
          <button onClick={()=> setItems(prev => prev.slice(0,-1))} disabled={!items.length}>Undo</button>
          <button onClick={()=> setItems([])} disabled={!items.length}>Clear</button>
        </div>

        {renderUrl && (
          <div className="render">
            <audio controls src={renderUrl}></audio>
            <a download="MiniMixLab_mix.wav" href={renderUrl} className="btn">Download WAV</a>
          </div>
        )}
      </div>

      <div className="grid two">
        <div>
          {tracks.map((t,i)=>(
            <TrackCard
              key={`${t.name}-${i}`}
              track={t} idx={i}
              onMute={toggleMute} onSolo={toggleSolo}
              onPlay={audition}
              audioRef={el => { if(el){ audioRefs.current[t.name]=el; }}}
            />
          ))}
        </div>

        <div>
          <Timeline
            projectBpm={Number(projectBpm)}
            bars={Number(bars)}
            tracks={tracks}
            items={items}
            onDropSection={onDropSection}
            onRemoveItem={onRemoveItem}
            selected={selected}
            setSelected={setSelected}
          />

          {/*  NEW: compact per-item editor */}
          <SectionEditor
            items={items}
            onUpdate={(i, updates) => {
              setItems(prev => prev.map((it, k) => (k === i ? { ...it, ...updates } : it)));
            }}
            onRemove={(i) => {
              setItems(prev => prev.filter((_, k) => k !== i));
            }}
          />

          <div className="legend">
            Replace: choose a different track+section  Extend: set Loop  Crop: edit Start/End  Remove: delete item  Fade Out: set ms in controls.
          </div>
        </div>
      </div>
    </div>
  );
}
