const API = import.meta.env.VITE_API || "";

export async function uploadFile(file){
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${API}/api/upload`, { method:"POST", body: fd });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export function previewUrl(file_id, start, end, speed = 1.0, opts = {}) {
  const q = new URLSearchParams({
    file_id,
    start,
    end,
    speed,
    pitch: opts.pitch ?? 0,
    hq: opts.hq ? "1" : "0",
    preset: opts.preset ?? "default",
  });
  return `${API}/api/preview?${q}`;
}

export async function fetchSections(){
  const r = await fetch(`${API}/api/sections`);
  return r.json();
}

export async function saveSections(sections){
  const r = await fetch(`${API}/api/sections`, {
    method:"POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ sections })
  });
  return r.json();
}

export async function startMix(tracks, socket_room){
  const r = await fetch(`${API}/api/mix`, {
    method:"POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ tracks, socket_room })
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json(); // {job_id}
}

export async function getJob(job_id){
  const r = await fetch(`${API}/api/jobs/${job_id}`);
  return r.json();
}

export function mixUrl(mix_id){
  return `${API}/api/mix/file/${mix_id}`;
}

export async function getProject(){
  const r = await fetch(`${API}/api/project`); return r.json();
}

export async function setProject(bpm, key){
  const r = await fetch(`${API}/api/project`, {
    method:"POST", headers:{ "Content-Type":"application/json" },
    body: JSON.stringify({ bpm, key })
  });
  return r.json();
}

export async function autoAlign(file_ids, target_bpm){
  const r = await fetch(`${API}/api/auto_align`, {
    method:"POST", headers:{ "Content-Type":"application/json" },
    body: JSON.stringify({ file_ids, target_bpm })
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function fetchSegments(file_id){
  const r = await fetch(`${API}/api/segment?file_id=${encodeURIComponent(file_id)}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json(); // { file_id, segments: [{start,end,label,confidence}] }
}

export async function renderArrangement(pieces, opts = {}){
  const body = { pieces, ...opts };
  const r = await fetch(`${API}/api/render_arrangement`, {
    method: "POST",
    headers: { "Content-Type":"application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function autoPitch(file_ids, project_key){
  const r = await fetch(`${API}/api/auto_pitch`, {
    method:"POST", headers:{ "Content-Type":"application/json" },
    body: JSON.stringify({ file_ids, project_key })
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json(); // {target_key, tracks:[{file_id,semitones,...}]}
}