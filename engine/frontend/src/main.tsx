import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

type ErrorBoundaryState = { error: Error | null };

class DashboardErrorBoundary extends React.Component<React.PropsWithChildren, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, details: React.ErrorInfo) {
    console.error("Dashboard render failed", error, details.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24, background: "#080d14", color: "#f4f7fb", fontFamily: "Inter, system-ui, sans-serif" }}>
        <section style={{ width: "min(560px, 100%)", padding: 28, border: "1px solid #283442", borderRadius: 18, background: "#111923" }}>
          <p style={{ margin: "0 0 8px", color: "#ff7185", fontWeight: 700, letterSpacing: ".08em" }}>DASHBOARD RECOVERY</p>
          <h1 style={{ margin: "0 0 12px", fontSize: 28 }}>The dashboard could not finish rendering.</h1>
          <p style={{ margin: "0 0 22px", color: "#aeb9c7", lineHeight: 1.6 }}>The bot keeps running. Reload this page to fetch the current dashboard bundle.</p>
          <button onClick={() => window.location.reload()} style={{ border: 0, borderRadius: 10, padding: "12px 18px", background: "#7ba7ff", color: "#07101d", fontWeight: 800, cursor: "pointer" }}>Reload dashboard</button>
          <details style={{ marginTop: 20, color: "#8390a1" }}><summary>Technical details</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{this.state.error.message}</pre></details>
        </section>
      </main>
    );
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <DashboardErrorBoundary><App /></DashboardErrorBoundary>
  </React.StrictMode>,
);
