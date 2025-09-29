const API = import.meta.env.VITE_API || ""; // same origin if proxied

export async function uploadFile(file) {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${API}/api/upload`, { method: "POST", body: fd });
  if (!r.ok) throw new Error("upload failed");
  return r.json();
}

export function previewUrl(file_id, start, end, speed = 1.0) {
  const q = new URLSearchParams({ file_id, start, end, speed });
  return `${API}/api/preview?${q}`;
}

export async function renderMix(tracks) {
  const r = await fetch(`${API}/api/mix`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tracks }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}