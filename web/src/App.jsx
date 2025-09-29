import { useRef, useState } from "react";
import { uploadFile, previewUrl, renderMix } from "./api";
import useAudioSlice from "./useAudioSlice";

export default function App() {
  const [uploaded, setUploaded] = useState([]);
  const [active, setActive] = useState(null);
  const [range, setRange] = useState([0, 30]);
  const [speed, setSpeed] = useState(1.0);
  const audioRef = useRef(null);

  const currentUrl = active ? previewUrl(active.file_id, range[0], range[1], speed) : "";
  useAudioSlice(audioRef, currentUrl);

  async function onUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const meta = await uploadFile(file);
    setUploaded(u => [...u, { ...meta, name: file.name }]);
    setActive({ ...meta, name: file.name });
    setRange([0, Math.min(30, meta.duration || 30)]);
  }

  async function onRender() {
    if (!uploaded.length) return;
    // simple demo mix: first two tracks, play from 0 with speed
    const tracks = uploaded.slice(0, 4).map((t, i) => ({
      file_id: t.file_id,
      offset: i * 0.0,   // could be positions from your UI
      gain: -3.0,
      speed: 1.0
    }));
    const { url } = await renderMix(tracks);
    window.open(url, "_blank");
  }

  return (
    <div className="min-h-screen bg-[#0b0b11] text-slate-100 p-6">
      <h1 className="text-3xl font-bold mb-4">MiniMixLab (Real)</h1>

      <div className="space-x-3 mb-4">
        <input type="file" accept="audio/*" onChange={onUpload} />
        <button className="px-3 py-2 bg-cyan-500/20 rounded" onClick={onRender}>
          Render Mix (server)
        </button>
      </div>

      {active && (
        <div className="mb-3">
          <div className="mb-2">Preview: {active.name}</div>
          <label>Start (s): </label>
          <input type="number" value={range[0]} onChange={e=>setRange([+e.target.value, range[1]])} />
          <label className="ml-3">End (s): </label>
          <input type="number" value={range[1]} onChange={e=>setRange([range[0], +e.target.value])} />
          <label className="ml-3">Speed: </label>
          <input type="number" step="0.05" value={speed} onChange={e=>setSpeed(+e.target.value)} />
        </div>
      )}

      <audio ref={audioRef} controls preload="none" className="w-full" />

      <div className="mt-6">
        <h3 className="font-semibold mb-2">Uploaded</h3>
        <ul className="space-y-1">
          {uploaded.map(f => (
            <li key={f.file_id}>
              <button className="underline" onClick={()=>setActive(f)}>{f.name}</button>
              <span className="opacity-60"> — {Math.round(f.duration||0)}s</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}