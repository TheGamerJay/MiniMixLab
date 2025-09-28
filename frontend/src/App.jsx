import React, { useRef, useState } from "react";
import axios from "axios";
import Timeline from "./Timeline.jsx";

function TrackCard({track, idx, onMute, onSolo, onPlay, audioRef}) {
  return (
    <div className="card">
      <audio ref={audioRef} preload="metadata" />
      <div className="row">
        <strong>{track.name}</strong>
        <span>{Math.round(track.bpm)} BPM • {track.key}</span>
        <button className={track.muted ? "muted" : ""} onClick={() => onMute(idx)}>M</button>
        <button className={track.solo ? "solo" : ""} onClick={() => onSolo(idx)}>S</button>
      </div>
      <div className="chips">
        {track.sections.map((s, k) => (
          <button key={k} className="chip" onClick={() => onPlay(idx, s)}>
            ▶ {s.label} ({s.start.toFixed(1)}–{s.end.toFixed(1)})
          </button>
        ))}
      </div>
    </div>
  );
}

export default function App(){
  const [tracks, setTracks] = useState([]);   // analyzed
  const audioRefs = useRef({});
  const [projectBpm, setProjectBpm] = useState(88);
  const [bars, setBars] = useState(32);
  const [xfade, setXfade] = useState(120);
  const [items, setItems] = useState([]);     // placed items
  const [renderUrl, setRenderUrl] = useState("");

  async function handleFiles(e){
    const files = Array.from(e.target.files).slice(0,3);
    if(files.length===0) return;
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
      })
    }, 0);
  }

  function toggleMute(i){
    setTracks(ts => ts.map((t, k) => k===i ? {...t, muted: !t.muted, solo:false} : t));
  }
  function toggleSolo(i){
    setTracks(ts => {
      const isSolo = !ts[i].solo;
      return ts.map((t,k)=> k===i ? {...t, solo:isSolo, muted:false}
                                  : {...t, solo:false, muted:isSolo || t.muted});
    });
  }
  function getGain(i){
    const anySolo = tracks.some(t=>t.solo);
    if(tracks[i].muted) return 0;
    if(anySolo && !tracks[i].solo) return 0;
    return 1;
  }
  async function audition(i, sec){
    // stop all overlap
    Object.values(audioRefs.current).forEach(a => a?.pause());
    const t = tracks[i];
    const a = audioRefs.current[t.name];
    if(!a) return;
    if(getGain(i)===0) return;

    const payload = {
      file_hash: t.hash, start: sec.start, end: sec.end,
      target_bpm: t.bpm, source_bpm: t.bpm, semitones: 0
    };
    const res = await axios.post("/align/preview", payload, { responseType: "blob" });
    const blobUrl = URL.createObjectURL(new Blob([res.data], {type: "audio/wav"}));
    a.src = blobUrl; a.currentTime = 0; a.volume = 1; a.play();
  }

  function onDropSection(trackIdx, section, barIndex){
    const t = tracks[trackIdx];
    const it = {
      label: `${t.name.split('.').slice(0,-1).join('.')}:${section.label}`,
      file_hash: t.hash,
      start: section.start,
      end: section.end,
      source_bpm: t.bpm,
      semitones: 0,
      at_bar: barIndex
    };
    setItems(prev => [...prev, it]);
  }
  function onRemoveItem(i){ setItems(prev => prev.filter((_,k)=>k!==i)); }

  async function renderFull(){
    if(items.length === 0) return;
    setRenderUrl("");
    const payload = {
      project_bpm: Number(projectBpm),
      crossfade_ms: Number(xfade),
      bars: Number(bars),
      items: items.map(({label, ...keep})=>keep)
    };
    const res = await axios.post("/arrange/render", payload, { responseType: "blob" });
    const url = URL.createObjectURL(new Blob([res.data], {type: "audio/wav"}));
    setRenderUrl(url);
  }

  return (
    <div className="wrap">
      <h1>MiniMixLab 🎶</h1>

      <div className="panel">
        <div className="controls">
          <label>Upload 1–3
            <input type="file" accept=".wav,.aiff,.aif,.mp3,.flac" multiple onChange={handleFiles}/>
          </label>
          <label>Project BPM
            <input type="number" value={projectBpm} onChange={e=>setProjectBpm(e.target.value)} />
          </label>
          <label>Bars
            <input type="number" value={bars} onChange={e=>setBars(e.target.value)} />
          </label>
          <label>Crossfade (ms)
            <input type="number" value={xfade} onChange={e=>setXfade(e.target.value)} />
          </label>
          <button onClick={renderFull} disabled={items.length===0}>Render Full Mix</button>
        </div>

        {renderUrl && (
          <div className="render">
            <audio controls src={renderUrl}></audio>
            <a download="mix.wav" href={renderUrl} className="btn">Download WAV</a>
          </div>
        )}
      </div>

      <div className="grid two">
        <div>
          {tracks.map((t,i)=>(
            <TrackCard key={t.name}
                       track={t} idx={i}
                       onMute={toggleMute} onSolo={toggleSolo}
                       onPlay={audition}
                       audioRef={el => { if(el){ audioRefs.current[t.name]=el; }}} />
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
          />
          <div className="legend">
            Drag a section chip into a bar to place it. Click ✕ on a placed tag to remove.
          </div>
        </div>
      </div>
    </div>
  );
}