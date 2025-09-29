import React, { useState } from "react";

export default function App() {
  console.log("MiniMixLab: Clean reset App mounted");
  const [tracks, setTracks] = useState([]);

  function injectDemo() {
    const mkSecs = (len) => [
      { label: "Intro", start: 0, end: 10 },
      { label: "Verse 1", start: 10, end: 30 },
      { label: "Chorus", start: 30, end: 50 },
      { label: "Verse 2", start: 50, end: 70 },
      { label: "Bridge", start: 70, end: 85 },
      { label: "Chorus", start: 85, end: len },
    ];
    const t1 = { name: "Demo A.wav", bpm: 120, key: "C#m", sections: mkSecs(100) };
    const t2 = { name: "Demo B.wav", bpm: 120, key: "Am",  sections: mkSecs(95) };
    setTracks([t1, t2]);
  }

  return (
    <div
      style={{
        background: "#0b0f1a",
        color: "#fff",
        fontFamily: "system-ui, sans-serif",
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        gap: "16px",
        padding: "24px",
      }}
    >
      <h1 style={{ color: "indigo", fontSize: "2rem" }}> MiniMixLab</h1>
      <p style={{ color: "pink", fontSize: "1.1rem" }}>UI is working  React is mounted.</p>

      <div style={{ display: "flex", gap: "12px" }}>
        <button
          style={{
            padding: "10px 20px",
            borderRadius: "12px",
            border: "none",
            background: "linear-gradient(to right, indigo, pink)",
            color: "#fff",
            fontWeight: "bold",
            cursor: "pointer",
          }}
          onClick={() => alert("Demo button works!")}
        >
          Test Button
        </button>

        <button
          style={{
            padding: "10px 20px",
            borderRadius: "12px",
            border: "1px solid #444",
            background: "#141a24",
            color: "#fff",
            cursor: "pointer",
          }}
          onClick={injectDemo}
        >
          Load Demo Tracks
        </button>
      </div>

      {tracks.length > 0 && (
        <div
          style={{
            marginTop: "20px",
            width: "min(900px, 90vw)",
            border: "1px solid #333",
            borderRadius: "12px",
            padding: "16px",
            textAlign: "left",
            background: "#0f1420",
          }}
        >
          {tracks.map((t, i) => (
            <div key={i} style={{ borderBottom: "1px solid #222", padding: "10px 0" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <strong>{t.name}</strong>
                <span style={{ opacity: 0.8 }}>{Math.round(t.bpm)} BPM  {t.key}</span>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginTop: "8px" }}>
                {t.sections.map((s, k) => (
                  <span
                    key={k}
                    style={{
                      border: "1px solid #555",
                      padding: "6px 10px",
                      borderRadius: "999px",
                      background: "#151a22",
                      fontSize: "0.9rem",
                    }}
                    title={`${s.start.toFixed(1)}${s.end.toFixed(1)}s`}
                  >
                    {s.label} ({s.start.toFixed(1)}{s.end.toFixed(1)})
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
