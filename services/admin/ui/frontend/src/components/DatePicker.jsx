import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./Icon.jsx";

const POP_W = 296;
const POP_H = 360;

const MONTHS = [
  "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
];
const MONTHS_SHORT = [
  "янв", "фев", "мар", "апр", "мая", "июн",
  "июл", "авг", "сен", "окт", "ноя", "дек",
];
const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

const pad = (n) => String(n).padStart(2, "0");

function parseValue(v, mode) {
  if (!v) return null;
  const d = new Date(v.length === 10 ? `${v}T00:00:00` : v);
  if (isNaN(d.getTime())) return null;
  return d;
}

function formatOut(d, mode) {
  if (!d) return "";
  const ymd = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  if (mode === "date") return ymd;
  return `${ymd}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatDisplay(d, mode) {
  if (!d) return "";
  const datePart = `${d.getDate()} ${MONTHS_SHORT[d.getMonth()]} ${d.getFullYear()}`;
  if (mode === "date") return datePart;
  return `${datePart}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function startOfMonth(d) { return new Date(d.getFullYear(), d.getMonth(), 1); }
function addMonths(d, n) { return new Date(d.getFullYear(), d.getMonth() + n, 1); }
function sameDay(a, b) {
  return a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function buildGrid(viewMonth) {
  const first = startOfMonth(viewMonth);
  const offset = (first.getDay() + 6) % 7;
  const start = new Date(first); start.setDate(first.getDate() - offset);
  const cells = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(start); d.setDate(start.getDate() + i);
    cells.push(d);
  }
  return cells;
}

export function DatePicker({
  value,
  onChange,
  mode = "datetime",
  placeholder,
  disabled = false,
  min,
  max,
}) {
  const wrapRef = useRef(null);
  const popRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [popPos, setPopPos] = useState({ top: 0, left: 0, above: false });

  const parsed = useMemo(() => parseValue(value, mode), [value, mode]);
  const minD = useMemo(() => parseValue(min, mode), [min, mode]);
  const maxD = useMemo(() => parseValue(max, mode), [max, mode]);

  const [view, setView] = useState(() => startOfMonth(parsed || new Date()));
  useEffect(() => {
    if (parsed) setView(startOfMonth(parsed));
  }, [value]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target) &&
          popRef.current && !popRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    const onEsc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  const computePos = () => {
    const el = wrapRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const margin = 8;
    const popH = (popRef.current && popRef.current.offsetHeight) || POP_H;
    const popW = (popRef.current && popRef.current.offsetWidth) || POP_W;
    const roomBelow = window.innerHeight - rect.bottom - margin;
    const roomAbove = rect.top - margin;
    // Prefer below; flip up when below cannot fit AND above has more space.
    const wantBelow = roomBelow >= popH || roomBelow >= roomAbove;
    let top = wantBelow ? rect.bottom + 6 : rect.top - popH - 6;
    // Clamp vertically into the viewport.
    if (top + popH + margin > window.innerHeight) {
      top = Math.max(margin, window.innerHeight - popH - margin);
    }
    if (top < margin) top = margin;
    let left = rect.left;
    const maxLeft = window.innerWidth - popW - margin;
    if (left > maxLeft) left = Math.max(margin, maxLeft);
    if (left < margin) left = margin;
    setPopPos({ top, left, above: !wantBelow });
  };

  useLayoutEffect(() => {
    if (!open) return;
    computePos();
    const onScroll = () => computePos();
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [open]);

  const grid = useMemo(() => buildGrid(view), [view]);

  const isDisabled = (d) => {
    if (minD && d < new Date(minD.getFullYear(), minD.getMonth(), minD.getDate())) return true;
    if (maxD && d > new Date(maxD.getFullYear(), maxD.getMonth(), maxD.getDate())) return true;
    return false;
  };

  const pickDay = (d) => {
    if (isDisabled(d)) return;
    const next = new Date(d);
    if (mode === "datetime") {
      if (parsed) { next.setHours(parsed.getHours(), parsed.getMinutes(), 0, 0); }
      else {
        const now = new Date();
        next.setHours(now.getHours(), now.getMinutes(), 0, 0);
      }
    }
    onChange(formatOut(next, mode));
    if (mode === "date") setOpen(false);
  };

  const setHour = (h) => {
    const base = parsed || new Date();
    const next = new Date(base);
    next.setHours(Number(h), next.getMinutes(), 0, 0);
    onChange(formatOut(next, mode));
  };
  const setMinute = (m) => {
    const base = parsed || new Date();
    const next = new Date(base);
    next.setMinutes(Number(m), 0, 0);
    onChange(formatOut(next, mode));
  };

  const applyPreset = (preset) => {
    const now = new Date();
    let d;
    if (preset === "now") d = now;
    else if (preset === "in1h") d = new Date(now.getTime() + 3600_000);
    else if (preset === "tomorrow") {
      d = new Date(now); d.setDate(d.getDate() + 1);
      if (mode === "datetime") d.setHours(12, 0, 0, 0);
    } else if (preset === "in7d") {
      d = new Date(now); d.setDate(d.getDate() + 7);
      if (mode === "datetime") d.setHours(now.getHours(), now.getMinutes(), 0, 0);
    } else if (preset === "in30d") {
      d = new Date(now); d.setDate(d.getDate() + 30);
      if (mode === "datetime") d.setHours(now.getHours(), now.getMinutes(), 0, 0);
    } else return;
    onChange(formatOut(d, mode));
    setView(startOfMonth(d));
  };

  const clear = () => onChange("");

  const today = new Date();
  const monthLabel = `${MONTHS[view.getMonth()]} ${view.getFullYear()}`;

  return (
    <div className={`dp-wrap ${disabled ? "is-disabled" : ""}`} ref={wrapRef}>
      <button
        type="button"
        className="dp-trigger"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        data-open={open || undefined}
      >
        <Icon name={mode === "datetime" ? "clock" : "calendar"} size={13} />
        <span className={parsed ? "dp-trigger-val" : "dp-trigger-placeholder"}>
          {parsed ? formatDisplay(parsed, mode) : (placeholder || (mode === "datetime" ? "Дата и время" : "Дата"))}
        </span>
        {parsed && !disabled && (
          <span
            role="button"
            tabIndex={0}
            className="dp-trigger-clear"
            title="Очистить"
            onClick={(e) => { e.stopPropagation(); clear(); }}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); clear(); } }}
          >
            <Icon name="x" size={11} />
          </span>
        )}
      </button>

      {open && createPortal(
        <div
          className="dp-pop"
          ref={popRef}
          style={{ position: "fixed", top: popPos.top, left: popPos.left, width: POP_W }}
        >
          <div className="dp-pop-head">
            <button type="button" className="dp-nav" onClick={() => setView(addMonths(view, -1))} title="Предыдущий">
              <Icon name="chevron-left" size={14} />
            </button>
            <div className="dp-pop-title">{monthLabel}</div>
            <button type="button" className="dp-nav" onClick={() => setView(addMonths(view, 1))} title="Следующий">
              <Icon name="chevron-right" size={14} />
            </button>
          </div>

          <div className="dp-weekdays">
            {WEEKDAYS.map((w) => <div key={w} className="dp-wd">{w}</div>)}
          </div>

          <div className="dp-grid">
            {grid.map((d, i) => {
              const otherMonth = d.getMonth() !== view.getMonth();
              const isToday = sameDay(d, today);
              const isSel = sameDay(d, parsed);
              const dis = isDisabled(d);
              return (
                <button
                  key={i}
                  type="button"
                  className="dp-day"
                  data-other={otherMonth || undefined}
                  data-today={isToday || undefined}
                  data-selected={isSel || undefined}
                  disabled={dis}
                  onClick={() => pickDay(d)}
                >
                  {d.getDate()}
                </button>
              );
            })}
          </div>

          {mode === "datetime" && (
            <div className="dp-time">
              <Icon name="clock" size={12} />
              <select
                className="dp-time-sel"
                value={parsed ? parsed.getHours() : new Date().getHours()}
                onChange={(e) => setHour(e.target.value)}
              >
                {Array.from({ length: 24 }, (_, i) => (
                  <option key={i} value={i}>{pad(i)}</option>
                ))}
              </select>
              <span className="dp-time-sep">:</span>
              <select
                className="dp-time-sel"
                value={parsed ? parsed.getMinutes() : 0}
                onChange={(e) => setMinute(e.target.value)}
              >
                {Array.from({ length: 60 }, (_, i) => i).map((m) => (
                  <option key={m} value={m}>{pad(m)}</option>
                ))}
              </select>
            </div>
          )}

          <div className="dp-presets">
            {mode === "datetime" ? (
              <>
                <button type="button" className="dp-preset" onClick={() => applyPreset("now")}>Сейчас</button>
                <button type="button" className="dp-preset" onClick={() => applyPreset("in1h")}>+1 час</button>
                <button type="button" className="dp-preset" onClick={() => applyPreset("tomorrow")}>Завтра 12:00</button>
                <button type="button" className="dp-preset" onClick={() => applyPreset("in7d")}>+7 дней</button>
              </>
            ) : (
              <>
                <button type="button" className="dp-preset" onClick={() => applyPreset("now")}>Сегодня</button>
                <button type="button" className="dp-preset" onClick={() => applyPreset("tomorrow")}>Завтра</button>
                <button type="button" className="dp-preset" onClick={() => applyPreset("in7d")}>+7 дней</button>
                <button type="button" className="dp-preset" onClick={() => applyPreset("in30d")}>+30 дней</button>
              </>
            )}
            <div style={{ flex: 1 }} />
            <button type="button" className="dp-apply" onClick={() => setOpen(false)}>Готово</button>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
