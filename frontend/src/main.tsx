import React, { useState, useEffect } from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

function AutoScale({ children }: { children: React.ReactNode }) {
  const [scale, setScale] = useState(1);

  useEffect(() => {
    const handleResize = () => {
      // The minimum desktop bounds the app was designed for
      const BASE_W = 1440;
      const BASE_H = 850;
      const scaleW = window.innerWidth / BASE_W;
      const scaleH = window.innerHeight / BASE_H;
      // Scale down to fit, but never scale up past 1
      setScale(Math.min(scaleW, scaleH, 1));
    };

    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  if (scale === 1) return <>{children}</>;

  return (
    <div style={{ width: "100vw", height: "100vh", overflow: "hidden", display: "flex", justifyContent: "center", alignItems: "center", background: "var(--bg-base)" }}>
      <div style={{
        width: 1440, height: 850,
        transform: `scale(${scale})`, transformOrigin: "center center"
      }}>
        {children}
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AutoScale>
      <App />
    </AutoScale>
  </React.StrictMode>
);
