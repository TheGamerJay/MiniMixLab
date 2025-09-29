export default function App() {
  console.log("MiniMixLab: Clean reset App mounted");

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
        gap: "16px"
      }}
    >
      <h1 style={{ color: "indigo", fontSize: "2rem" }}>
        🎶 MiniMixLab
      </h1>
      <p style={{ color: "pink", fontSize: "1.25rem" }}>
        UI is working — React is mounted.
      </p>
      <button
        style={{
          padding: "10px 20px",
          borderRadius: "12px",
          border: "none",
          background: "linear-gradient(to right, indigo, pink)",
          color: "#fff",
          fontWeight: "bold",
          cursor: "pointer"
        }}
        onClick={() => alert("Demo button works!")}
      >
        Test Button
      </button>
    </div>
  );
}