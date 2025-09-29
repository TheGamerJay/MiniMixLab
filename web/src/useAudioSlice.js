import { useEffect, useRef } from "react";

// Lightweight: just set the <audio>.src to the streaming endpoint.
export default function useAudioSlice(audioRef, url) {
  useEffect(() => {
    const el = audioRef.current;
    if (!el || !url) return;
    el.src = url; // browser streams it; no big JS buffers
    el.load();
  }, [url, audioRef]);
}