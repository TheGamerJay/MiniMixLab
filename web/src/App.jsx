import { useEffect, useRef, useState } from "react";
import io from "socket.io-client";
import { uploadFile, previewUrl, fetchSections, startMix, getJob, mixUrl,
         getProject, setProject, autoAlign } from "./api";
import ErrorBoundary from "./ErrorBoundary";

const API = import.meta.env.VITE_API || "";

function AppInner(){
  const audioRef = useRef(null);
  const [socket, setSocket] = useState(null);
  const [room] = useState(crypto.randomUUID());

  const [uploaded, setUploaded] = useState([]); // {file_id,name,duration,analysis?}
  const [tracks, setTracks]   = useState([]);   // render model: {file_id, offset, gain, speed}
  const [active, setActive]   = useState(null);

  const [sections, setSections] = useState([]);
  const [project, setProjectState] = useState({ bpm: 120, key: "C" });

  const [progress, setProgress] = useState({show:false, pct:0, msg:""});

  // sockets
  useEffect(() => {
    const s = io(API, { transports: ["websocket"] });
    s.on("connect", () => s.emit("join", room));
    s.on("mix_progress", (p) => setProgress(x => ({...x, pct: p.percent, msg: p.message})));
    setSocket(s);
    return () => s.close();
  }, [room]);

  // sections + project
  useEffect(() => { (async () => {
    const { sections } = await fetchSections(); setSections(sections);
    const p = await getProject(); setProjectState(p);
  })(); }, []);

  function playSlice(sec){
    if(!active) return;
    const url = previewUrl(active.file_id, sec.start, sec.end, 1.0);
    const el = audioRef.current; el.src = url; el.load(); el.play();
  }

  async function onUpload(e){
    const file = e.target.files?.[0]; if(!file) return;
    const meta = await uploadFile(file);
    const item = { ...meta, name: file.name }; // meta.analysis contains bpm/key/first_beat
    setUploaded(u => [...u, item]);
    setActive(item);
    setTracks(t => [...t, { file_id: item.file_id, offset: 0, gain: -3, speed: 1.0 }]);
  }

  async function applyAutoAlign(){
    if (uploaded.length === 0) return;
    const file_ids = uploaded.map(x => x.file_id);
    const { tracks: aligned } = await autoAlign(file_ids, project.bpm);
    // merge back into our track model
    setTracks(prev =>
      prev.map(tr => {
        const rec = aligned.find(a => a.file_id === tr.file_id);
        return rec ? { ...tr, speed: rec.suggested_speed, offset: rec.suggested_offset } : tr;
      })
    );
  }

  async function onRender(){
    if (tracks.length === 0) return;
    setProgress({show:true, pct:1, msg:"Queued"});
    const { job_id } = await startMix(tracks, room);
    const timer = setInterval(async () => {
      const j = await getJob(job_id);
      if (j.status === "done") {
        clearInterval(timer); setProgress({show:false, pct:100, msg:"Done"});
        window.open(mixUrl(j.result), "_blank");
      } else if (j.status === "error") {
        clearInterval(timer); setProgress({show:false, pct:0, msg:""}); alert("Mix failed:\n"+j.result);
      }
    }, 1000);
  }

  async function updateProjectBPM(e){
    const bpm = +e.target.value;
    const p = await setProject(bpm, project.key);
    setProjectState(p);
  }

  return (
    <div className="min-h-screen bg-[#0b0b11] text-slate-100 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">MiniMixLab</h1>
        <div className="text-sm opacity-70">Room: {room.slice(0,8)}</div>
      </div>

      <div className="mt-4 flex flex-wrap gap-3 items-center">
        <input type="file" accept="audio/*" onChange={onUpload}/>
        <label>Project BPM</label>
        <input type="number" className="text-black w-24" value={project.bpm} onChange={updateProjectBPM}/>
        <button className="px-3 py-2 rounded bg-cyan-500/20" onClick={applyAutoAlign}>Auto-Align</button>
        <button className="px-3 py-2 rounded bg-cyan-500/20" onClick={onRender}>Render Mix</button>
      </div>

      <div className="mt-6 grid md:grid-cols-2 gap-6">
        <div>
          <h3 className="font-semibold mb-2">Sections</h3>
          <div className="flex flex-wrap gap-2">
            {sections.map((s, i)=>(
              <button key={i} onClick={()=>playSlice(s)}
                className="px-3 py-2 rounded-xl bg-white/5 hover:bg-white/10">
                {s.label} ({s.start}-{s.end}s)
              </button>
            ))}
          </div>

          <div className="mt-6">
            <audio ref={audioRef} controls preload="none" className="w-full"/>
          </div>
        </div>

        <div>
          <h3 className="font-semibold mb-2">Stems (detected)</h3>
          <ul className="space-y-2">
            {uploaded.map(u => (
              <li key={u.file_id} className="bg-white/5 rounded p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-mono">{u.name}</div>
                    {u.analysis && (
                      <div className="text-xs opacity-80">
                        BPM: {u.analysis.bpm.toFixed(1)} • Key: {u.analysis.key} • First beat: {u.analysis.first_beat.toFixed(2)}s
                      </div>
                    )}
                  </div>
                  <button className="underline" onClick={()=>setActive(u)}>Preview</button>
                </div>
                {/* track controls */}
                <div className="mt-2 grid grid-cols-3 gap-2 text-sm">
                  {(() => {
                    const t = tracks.find(x => x.file_id === u.file_id);
                    if (!t) return null;
                    return (
                      <>
                        <label>Offset (s)
                          <input type="number" step="0.05" className="text-black w-full"
                                 value={t.offset}
                                 onChange={e=>setTracks(xs=>xs.map(x=>x.file_id===u.file_id?{...x,offset:+e.target.value}:x))}/>
                        </label>
                        <label>Speed
                          <input type="number" step="0.01" className="text-black w-full"
                                 value={t.speed}
                                 onChange={e=>setTracks(xs=>xs.map(x=>x.file_id===u.file_id?{...x,speed:+e.target.value}:x))}/>
                        </label>
                        <label>Gain (dB)
                          <input type="number" step="0.5" className="text-black w-full"
                                 value={t.gain}
                                 onChange={e=>setTracks(xs=>xs.map(x=>x.file_id===u.file_id?{...x,gain:+e.target.value}:x))}/>
                        </label>
                      </>
                    );
                  })()}
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {progress.show && (
        <div className="fixed inset-0 bg-black/60 grid place-items-center">
          <div className="bg-[#111] p-6 rounded-xl w-[420px]">
            <div className="mb-2">Rendering… {progress.pct}%</div>
            <div className="h-2 bg-white/10 rounded">
              <div className="h-2 bg-cyan-400 rounded" style={{ width: `${progress.pct}%` }} />
            </div>
            <div className="mt-2 text-xs opacity-70">{progress.msg}</div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function App(){ return <ErrorBoundary><AppInner/></ErrorBoundary>; }