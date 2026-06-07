import React, { useState, useEffect } from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

function AutoScale({ children }: { children: React.ReactNode }) {
  const [scale, setScale] = useState(1);

  useEffect(() => {
    const handleResize = () => {
      // The absolute minimum dimensions required to fit the UI without scrolling
      const MIN_W = 1440;
      const MIN_H = 960; 
      
      // If the screen is larger than the minimum, don't scale (let it be fully dynamic and responsive)
      const scaleW = window.innerWidth < MIN_W ? window.innerWidth / MIN_W : 1;
      const scaleH = window.innerHeight < MIN_H ? window.innerHeight / MIN_H : 1;
      
      setScale(Math.min(scaleW, scaleH));
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
