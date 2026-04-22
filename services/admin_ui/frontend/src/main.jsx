import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./styles.css";

const saved = (() => {
  try { return JSON.parse(localStorage.getItem("vpn-ctrl-state") || "null") || {}; } catch { return {}; }
})();
const theme = saved.theme || "dark";
document.documentElement.setAttribute("data-theme", theme);
document.documentElement.setAttribute("data-density", saved.density || "comfortable");

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
