import React, { useState } from "react";

export default function App() {
  const [tab, setTab] = useState("overview");
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-head">VPN Control</div>
        <nav className="sidebar-nav">
          {[
            ["overview", "Главная"],
            ["nodes", "Серверы"],
            ["routes", "Маршруты"],
            ["subscriptions", "Подписки"],
          ].map(([id, label]) => (
            <button
              key={id}
              className={tab === id ? "sidebar-item active" : "sidebar-item"}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </nav>
      </aside>
      <main className="content">
        <h1 style={{ margin: 0 }}>{tab}</h1>
        <p className="muted" style={{ marginTop: 12 }}>
          Новая админ-панель. Пока только каркас — следующим шагом подключу API и перенесу страницы из шаблона.
        </p>
      </main>
    </div>
  );
}
