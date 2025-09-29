import { useEffect, useRef, useState } from "react";
import io from "socket.io-client";
import { uploadFile, previewUrl, fetchSections, startMix, getJob, mixUrl } from "./api";
import ErrorBoundary from "./ErrorBoundary";
import logoImage from "./assets/MiniMixLabLogo.png";

const API = import.meta.env.VITE_API || "";

function AppInner(){
  const audioRef = useRef(null);
  const [socket, setSocket] = useState(null);
  const [room, setRoom] = useState(crypto.randomUUID());
  const [uploaded, setUploaded] = useState([]);
  const [active, setActive] = useState(null);
  const [sections, setSections] = useState([]);
  const [speed, setSpeed] = useState(1.0);
  const [progress, setProgress] = useState({show:false, pct:0, msg:""});

  useEffect(() => {
    // socket
    const s = io(API, { transports: ["websocket"] });
    s.on("connect", () => { s.emit("join", room); });
    s.on("mix_progress", (p) => setProgress(x => ({...x, pct: p.percent, msg: p.message})));
    setSocket(s);
    return () => { s.close(); };
  }, [room]);

  useEffect(() => { (async () => {
    const { sections } = await fetchSections();
    setSections(sections);
  })(); }, []);

  function playSlice(sec){
    if(!active) return;
    const url = previewUrl(active.file_id, sec.start, sec.end, speed);
    const el = audioRef.current;
    el.src = url; el.load(); el.play();
  }

  async function onUpload(e){
    const file = e.target.files?.[0]; if(!file) return;
    const meta = await uploadFile(file);
    const item = { ...meta, name: file.name };
    setUploaded(u => [...u, item]);
    setActive(item);
  }

  async function onRender(){
    if (uploaded.length === 0) return;
    setProgress({show:true, pct:1, msg:"Queued"});
    // simple: mix all uploaded tracks aligned at 0
    const tracks = uploaded.map((t) => ({
      file_id: t.file_id, offset: 0, gain: -3, speed: 1.0
    }));
    const { job_id } = await startMix(tracks, room);

    // poll for completion (backend also streams progress over socket)
    const timer = setInterval(async () => {
      const j = await getJob(job_id);
      if (j.status === "done") {
        clearInterval(timer);
        setProgress({show:false, pct:100, msg:"Done"});
        window.open(mixUrl(j.result), "_blank");
      } else if (j.status === "error") {
        clearInterval(timer);
        alert("Mix failed:\n" + j.result);
        setProgress({show:false, pct:0, msg:""});
      }
    }, 1000);
  }

  return (
    <div className="min-h-screen bg-[#0b0b11] text-slate-100 p-6">
      <div className="flex flex-col items-center gap-2 mb-6">
        <h1 className="text-3xl font-bold">MiniMixLab</h1>
        <img
          src={logoImage}
          alt="MiniMixLab Logo"
          className="h-32 w-auto"
          onError={(e) => {
            // Hide logo if it fails to load
            console.log('Logo failed to load:', e.target.src);
            e.target.style.display = 'none';
          }}
        />
        <div className="text-sm opacity-70">Room: {room.slice(0,8)}</div>
      </div>

      <div className="mt-4 flex gap-3 items-center flex-wrap">
        <input type="file" accept="audio/*" onChange={onUpload}/>
        <label className="ml-2">Speed</label>
        <input type="number" step="0.05" value={speed} onChange={e=>setSpeed(+e.target.value)} className="text-black w-24 p-1 rounded"/>
        <button className="px-3 py-2 rounded bg-cyan-500/20 hover:bg-cyan-500/30" onClick={onRender}>Render Mix</button>
      </div>

      <div className="mt-6">
        <h3 className="font-semibold mb-2">Sections</h3>
        <div className="flex flex-wrap gap-2">
          {sections.map((s, i)=>(
            <button key={i} onClick={()=>playSlice(s)}
              className="px-3 py-2 rounded-xl bg-white/5 hover:bg-white/10 transition-colors">
              {s.label} ({s.start}-{s.end}s)
            </button>
          ))}
        </div>
      </div>

      <div className="mt-6">
        <audio ref={audioRef} controls preload="none" className="w-full"/>
      </div>

      <div className="mt-6">
        <h3 className="font-semibold mb-2">Uploaded</h3>
        <ul className="space-y-1">
          {uploaded.map(f => (
            <li key={f.file_id} className="flex items-center gap-2">
              <button className="underline hover:text-cyan-400" onClick={()=>setActive(f)}>{f.name}</button>
              <span className="opacity-60">— {Math.round(f.duration||0)}s</span>
              {active?.file_id === f.file_id && <span className="text-cyan-400 text-xs">● active</span>}
            </li>
          ))}
        </ul>
      </div>

      {progress.show && (
        <div className="fixed inset-0 bg-black/60 grid place-items-center z-50">
          <div className="bg-[#111] p-6 rounded-xl w-[420px] border border-white/10">
            <div className="mb-2 font-semibold">Rendering… {progress.pct}%</div>
            <div className="h-3 bg-white/10 rounded-full overflow-hidden">
              <div
                className="h-3 bg-gradient-to-r from-cyan-400 to-blue-500 rounded-full transition-all duration-300"
                style={{ width: `${progress.pct}%` }}
              />
            </div>
            <div className="mt-2 text-sm opacity-70">{progress.msg}</div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function App(){
  return (
    <ErrorBoundary>
      <AppInner/>
    </ErrorBoundary>
  );
}