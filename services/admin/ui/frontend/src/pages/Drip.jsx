import { useState } from "react";

import { api } from "../api/client.js";
import { Empty } from "../components/Empty.jsx";
import { Icon } from "../components/Icon.jsx";
import { useQuery } from "../hooks/useQuery.js";

const TRIGGERS = [
  { v: "trial_started", l: "Активировал триал" },
  { v: "purchase", l: "Оплатил" },
  { v: "user_registered", l: "Зарегистрировался" },
];

const CONDITIONS = [
  { v: "always", l: "Всегда" },
  { v: "not_connected", l: "Ещё не подключился" },
  { v: "not_purchased", l: "Ещё не купил" },
];

const UNITS = [
  { v: 60, l: "мин" },
  { v: 3600, l: "часов" },
  { v: 86400, l: "дней" },
];

const BUTTON_STYLES = [
  { v: "", l: "По умолчанию" },
  { v: "primary", l: "Синяя" },
  { v: "success", l: "Зелёная" },
  { v: "danger", l: "Красная" },
];

function splitDelay(sec) {
  const s = sec || 0;
  if (s && s % 86400 === 0) return [s / 86400, 86400];
  if (s && s % 3600 === 0) return [s / 3600, 3600];
  return [Math.round(s / 60), 60];
}

function emptyStep() {
  return { val: 1, unit: 3600, condition: "always", text_body: "", buttons: [] };
}

function fromApi(c) {
  return {
    id: c.id,
    key: c.key,
    name: c.name,
    trigger_event: c.trigger_event || "trial_started",
    is_active: !!c.is_active,
    steps: (c.steps || [])
      .slice()
      .sort((a, b) => a.step_order - b.step_order)
      .map((s) => {
        const [val, unit] = splitDelay(s.delay_seconds);
        return {
          val,
          unit,
          condition: s.condition,
          text_body: s.text_body || "",
          buttons: (s.inline_buttons || []).map((b) => ({
            text: b.text || "",
            url: b.url || "",
            style: b.style || "",
          })),
        };
      }),
  };
}

function toPayload(form) {
  return {
    key: form.key.trim(),
    name: form.name.trim(),
    trigger_event: form.trigger_event,
    is_active: form.is_active,
    steps: form.steps.map((s, i) => {
      const buttons = s.buttons
        .filter((b) => b.text.trim() && b.url.trim())
        .map((b) => ({ text: b.text.trim(), url: b.url.trim(), style: b.style || null }));
      return {
        step_order: i,
        delay_seconds: Math.max(0, Math.round(s.val * s.unit)),
        condition: s.condition,
        text_body: s.text_body,
        inline_buttons: buttons.length ? buttons : null,
      };
    }),
  };
}

export function DripPage() {
  const q = useQuery(
    () => api.get("/support/drip/campaigns").catch(() => ({ items: [] })),
    { interval: 0 },
  );
  const [form, setForm] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const campaigns = q.data?.items || [];

  const patch = (p) => setForm((f) => ({ ...f, ...p }));
  const patchStep = (i, p) =>
    setForm((f) => ({
      ...f,
      steps: f.steps.map((s, idx) => (idx === i ? { ...s, ...p } : s)),
    }));

  const save = async () => {
    const payload = toPayload(form);
    if (!payload.key || !payload.name) {
      setErr("Заполни ключ и название");
      return;
    }
    if (!payload.steps.length) {
      setErr("Добавь хотя бы один шаг");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      if (form.id) await api.put(`/support/drip/campaigns/${form.id}`, payload);
      else await api.post("/support/drip/campaigns", payload);
      setForm(null);
      q.refetch();
    } catch (e) {
      setErr(e.message || "Ошибка сохранения");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!form.id) {
      setForm(null);
      return;
    }
    if (!window.confirm("Удалить кампанию?")) return;
    setBusy(true);
    try {
      await api.del(`/support/drip/campaigns/${form.id}`);
      setForm(null);
      q.refetch();
    } catch (e) {
      setErr(e.message || "Ошибка удаления");
    } finally {
      setBusy(false);
    }
  };

  if (form) {
    return (
      <div className="page">
        <div className="page-head">
          <div className="page-head-main">
            <h1 className="page-title">{form.id ? "Кампания" : "Новая цепочка"}</h1>
            <div className="page-subtitle">
              Автоматическая цепочка сообщений по событию пользователя
            </div>
          </div>
          <div className="page-head-actions">
            <button className="btn" onClick={() => setForm(null)} disabled={busy}>
              Назад
            </button>
            <button className="btn btn-primary" onClick={save} disabled={busy}>
              Сохранить
            </button>
          </div>
        </div>

        {err && <div className="card card-bad">{err}</div>}

        <div className="card" style={{ display: "grid", gap: 12, padding: 16 }}>
          <label className="form-field">
            <span className="form-label">Название</span>
            <input
              className="input"
              value={form.name}
              onChange={(e) => patch({ name: e.target.value })}
              placeholder="Триал → подключение"
            />
          </label>
          <label className="form-field">
            <span className="form-label">Ключ (латиницей, уникальный)</span>
            <input
              className="input mono"
              value={form.key}
              onChange={(e) => patch({ key: e.target.value })}
              placeholder="trial_connect"
              disabled={!!form.id}
            />
          </label>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "end" }}>
            <label className="form-field" style={{ flex: 1, minWidth: 200 }}>
              <span className="form-label">Запускать по событию</span>
              <select
                className="select"
                value={form.trigger_event}
                onChange={(e) => patch({ trigger_event: e.target.value })}
              >
                {TRIGGERS.map((t) => (
                  <option key={t.v} value={t.v}>{t.l}</option>
                ))}
              </select>
            </label>
            <label className="form-field" style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => patch({ is_active: e.target.checked })}
              />
              <span className="form-label" style={{ margin: 0 }}>Активна</span>
            </label>
          </div>
        </div>

        <div style={{ display: "grid", gap: 12, marginTop: 12 }}>
          {form.steps.map((s, i) => (
            <div key={i} className="card" style={{ display: "grid", gap: 10, padding: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <strong>Шаг {i + 1}</strong>
                <button
                  className="btn btn-ghost btn-icon"
                  onClick={() =>
                    setForm((f) => ({ ...f, steps: f.steps.filter((_, idx) => idx !== i) }))
                  }
                  title="Удалить шаг"
                >
                  <Icon name="x" size={16} />
                </button>
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "end" }}>
                <label className="form-field" style={{ width: 110 }}>
                  <span className="form-label">Через</span>
                  <input
                    className="input"
                    type="number"
                    min={0}
                    value={s.val}
                    onChange={(e) => patchStep(i, { val: Number(e.target.value) })}
                  />
                </label>
                <label className="form-field" style={{ width: 120 }}>
                  <span className="form-label">&nbsp;</span>
                  <select
                    className="select"
                    value={s.unit}
                    onChange={(e) => patchStep(i, { unit: Number(e.target.value) })}
                  >
                    {UNITS.map((u) => (
                      <option key={u.v} value={u.v}>{u.l}</option>
                    ))}
                  </select>
                </label>
                <label className="form-field" style={{ flex: 1, minWidth: 200 }}>
                  <span className="form-label">Условие (иначе цепочка завершается)</span>
                  <select
                    className="select"
                    value={s.condition}
                    onChange={(e) => patchStep(i, { condition: e.target.value })}
                  >
                    {CONDITIONS.map((c) => (
                      <option key={c.v} value={c.v}>{c.l}</option>
                    ))}
                  </select>
                </label>
              </div>
              <label className="form-field">
                <span className="form-label">Текст сообщения</span>
                <textarea
                  className="input"
                  rows={4}
                  value={s.text_body}
                  onChange={(e) => patchStep(i, { text_body: e.target.value })}
                  placeholder="Заметили, ты ещё не подключился — давай помогу 👇"
                />
              </label>
              <div style={{ display: "grid", gap: 6 }}>
                <span className="form-label">Кнопки</span>
                {s.buttons.map((b, bi) => (
                  <div key={bi} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <input
                      className="input"
                      style={{ flex: 1 }}
                      value={b.text}
                      placeholder="Текст"
                      onChange={(e) =>
                        patchStep(i, {
                          buttons: s.buttons.map((x, xi) =>
                            xi === bi ? { ...x, text: e.target.value } : x,
                          ),
                        })
                      }
                    />
                    <input
                      className="input"
                      style={{ flex: 2 }}
                      value={b.url}
                      placeholder="https://… или https://t.me/…"
                      onChange={(e) =>
                        patchStep(i, {
                          buttons: s.buttons.map((x, xi) =>
                            xi === bi ? { ...x, url: e.target.value } : x,
                          ),
                        })
                      }
                    />
                    <select
                      className="select"
                      style={{ width: 130 }}
                      value={b.style}
                      onChange={(e) =>
                        patchStep(i, {
                          buttons: s.buttons.map((x, xi) =>
                            xi === bi ? { ...x, style: e.target.value } : x,
                          ),
                        })
                      }
                    >
                      {BUTTON_STYLES.map((st) => (
                        <option key={st.v} value={st.v}>{st.l}</option>
                      ))}
                    </select>
                    <button
                      className="btn btn-ghost btn-icon"
                      onClick={() =>
                        patchStep(i, { buttons: s.buttons.filter((_, xi) => xi !== bi) })
                      }
                      title="Удалить кнопку"
                    >
                      <Icon name="x" size={14} />
                    </button>
                  </div>
                ))}
                <button
                  className="btn btn-sm"
                  onClick={() =>
                    patchStep(i, { buttons: [...s.buttons, { text: "", url: "", style: "" }] })
                  }
                >
                  <Icon name="plus" size={14} /> Кнопка
                </button>
              </div>
            </div>
          ))}
          <button
            className="btn"
            onClick={() => setForm((f) => ({ ...f, steps: [...f.steps, emptyStep()] }))}
          >
            <Icon name="plus" size={16} /> Добавить шаг
          </button>
        </div>

        {form.id && (
          <div style={{ marginTop: 16 }}>
            <button className="btn btn-danger" onClick={remove} disabled={busy}>
              Удалить кампанию
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Цепочки</h1>
          <div className="page-subtitle">
            Автоматические сообщения по событиям: триал → подключение, конверсия, winback
          </div>
        </div>
        <div className="page-head-actions">
          <button
            className="btn btn-primary"
            onClick={() =>
              setForm({
                key: "",
                name: "",
                trigger_event: "trial_started",
                is_active: false,
                steps: [emptyStep()],
              })
            }
          >
            <Icon name="plus" size={16} /> Кампания
          </button>
        </div>
      </div>

      {!campaigns.length ? (
        <Empty
          icon="git-branch"
          title="Цепочек нет"
          hint="Создай кампанию: выбери событие-триггер и шаги с задержкой, условием и текстом. Движок сам разошлёт их по юзерам."
        />
      ) : (
        <div className="card">
          <table className="tbl">
            <thead>
              <tr>
                <th>Название</th>
                <th>Триггер</th>
                <th>Шагов</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.map((c) => (
                <tr key={c.id} style={{ cursor: "pointer" }} onClick={() => setForm(fromApi(c))}>
                  <td style={{ fontWeight: 500 }}>
                    {c.name}
                    <div className="mono muted" style={{ fontSize: 11 }}>{c.key}</div>
                  </td>
                  <td>{TRIGGERS.find((t) => t.v === c.trigger_event)?.l || c.trigger_event || "—"}</td>
                  <td className="tbl-num">{(c.steps || []).length}</td>
                  <td>
                    {c.is_active ? (
                      <span className="pill ok">активна</span>
                    ) : (
                      <span className="pill muted">выкл</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
