// M0 placeholder shell. The real SPA (router, tree sidebar, BlockNote editor,
// date views) lands in M4+. This exists so the Vite build pipeline and committed
// ../dist output are wired and verified end to end before any UI work.
export function App() {
  return (
    <div style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
      <h1>nb</h1>
      <p>Web viewer SPA — under construction.</p>
    </div>
  );
}
