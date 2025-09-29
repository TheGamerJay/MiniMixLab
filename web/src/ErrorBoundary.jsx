import React from "react";

export default class ErrorBoundary extends React.Component {
  state = { hasError: false };

  static getDerivedStateFromError(){
    return { hasError: true };
  }

  componentDidCatch(e, info){
    console.error(e, info);
  }

  clearAndReload = async () => {
    if ('caches' in window) {
      for (const k of await caches.keys()) {
        await caches.delete(k);
      }
    }
    const regs = await navigator.serviceWorker?.getRegistrations?.();
    regs?.forEach(r=>r.unregister());
    location.reload();
  };

  render(){
    if (!this.state.hasError) return this.props.children;

    return (
      <div style={{padding:20,background:"#0b0b11",color:"#fff"}}>
        <h2>MiniMixLab had an error</h2>
        <button
          onClick={this.clearAndReload}
          style={{padding:10,marginTop:10,background:"#333",color:"#fff",border:"none",borderRadius:4,cursor:"pointer"}}
        >
          Clear cache & reload
        </button>
      </div>
    );
  }
}