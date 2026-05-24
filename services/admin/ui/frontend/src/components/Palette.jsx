// REPLACE frontend/src/components/Palette.jsx with this file.
// Adds support quick-action commands that emit non-navigation events.
import { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "./Icon.jsx";

const COMMANDS = [
  { group: "Навигация", items: [
    { id: "overview", label: "Главная", icon: "layout-dashboard" },
    { id: "probes", label: "Probes", icon: "radar" },
    { id: "traffic", label: "Трафик", icon: "bar-chart" },
    { id: "nodes", label: "Серверы", icon: "server" },
    { id: "routes", label: "Маршруты", icon: "route" },
    { id: "placements", label: "Плейсменты", icon: "map-pin" },
    { id: "transport", label: "Очередь", icon: "activity" },
    { id: "users", label: "Пользователи", icon: "users" },
    { id: "plans", label: "Тарифы", icon: "wallet" },
    { id: "subscriptions", label: "Подписки", icon: "key" },
    { id: "tickets", label: "Тикеты", icon: "message-square" },
    { id: "support-templates", label: "Шаблоны ответов", icon: "file-text" },
    { id: "broadcasts", label: "Рассылки", icon: "send" },
    { id: "zones", label: "Зоны", icon: "globe" },
    { id: "admin-users", label: "Админы", icon: "settings" },
    { id: "ops", label: "Операции", icon: "shield-check" },
  ]},
  { group: "Поддержка — действия", items: [
    { id: "tickets", action: "new-ticket", label: "Открыть новый тикет", icon: "plus", hint: "T N" },
    { id: "broadcasts", action: "new-broadcast", label: "Создать рассылку", icon: "megaphone", hint: "B N" },
    { id: "support-templates", action: "new-template", label: "Создать шаблон ответа", icon: "file-text", hint: "S N" },
  ]},
];

export function Palette({ open, onClose, onSelect }) {
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);

  useEffect(() => {
    if (open) { setQ(""); setActive(0); setTimeout(() => inputRef.current?.focus(), 40); }
  }, [open]);

  const filtered = useMemo(() => {
    if (!q.trim()) return COMMANDS;
    const needle = q.toLowerCase();
    return COMMANDS.map((g) => ({ ...g, items: g.items.filter((i) => i.label.toLowerCase().includes(needle)) }))
      .filter((g) => g.items.length);
  }, [q]);
  const flat = filtered.flatMap((g) => g.items);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === "Escape") { e.preventDefault(); onClose(); }
      else if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, flat.length - 1)); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
      else if (e.key === "Enter") { e.preventDefault(); if (flat[active]) onSelect(flat[active]); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, flat, active, onSelect, onClose]);

  if (!open) return null;
  let idx = -1;
  return (
    <div className="palette-backdrop" onClick={onClose}>
      <div className="palette" onClick={(e) => e.stopPropagation()}>
        <div className="palette-input-wrap">
          <Icon name="search" size={16} />
          <input
            ref={inputRef}
            className="palette-input"
            placeholder="Перейти или найти…"
            value={q}
            onChange={(e) => { setQ(e.target.value); setActive(0); }}
          />
          <span className="palette-hint"><span className="kbd">esc</span></span>
        </div>
        <div className="palette-list">
          {filtered.length === 0 && <div className="empty">Ничего не найдено</div>}
          {filtered.map((g) => (
            <div key={g.group}>
              <div className="palette-group-title">{g.group}</div>
              {g.items.map((it) => {
                idx++; const thisIdx = idx;
                return (
                  <div
                    key={`${it.id}-${it.action || "nav"}`}
                    className="palette-item"
                    data-active={thisIdx === active}
                    onMouseEnter={() => setActive(thisIdx)}
                    onClick={() => onSelect(it)}
                  >
                    <div className="palette-item-icon"><Icon name={it.icon} size={13} /></div>
                    <div className="palette-item-main">
                      <div className="palette-item-label">{it.label}</div>
                    </div>
                    {it.hint && (
                      <div className="palette-item-kbd">
                        {it.hint.split(" ").map((k, i) => <span key={i} className="kbd">{k}</span>)}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
        <div className="palette-footer">
          <div className="palette-footer-item"><span className="kbd">↑</span><span className="kbd">↓</span> навигация</div>
          <div className="palette-footer-item"><span className="kbd">↵</span> выбрать</div>
        </div>
      </div>
    </div>
  );
}
