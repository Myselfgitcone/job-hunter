import React, { useState, useEffect } from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

function AutoScale({ children }: { children: React.ReactNode }) {
  const [scale, setScale] = useState(1);

  useEffect(() => {
    const handleResize = () => {
      // The absolute minimum dimensions the dense layout requires before it would need to scroll
      const BASE_W = 1440;
      const BASE_H = 960; 
      const scaleW = window.innerWidth / BASE_W;
      const scaleH = window.innerHeight / BASE_H;
      // Scale down to fit, but never scale up past 1
      setScale(Math.min(scaleW, scaleH, 1));
    };

    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return (
    <div style={{
      width: `${100 / scale}vw`,
      height: `${100 / scale}vh`,
      transform: `scale(${scale})`,
      transformOrigin: "top left",
      overflow: "hidden"
    }}>
      {children}
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
