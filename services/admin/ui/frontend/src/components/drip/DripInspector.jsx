// Drip / Цепочки — step inspector (right pane). Edits the selected node and
// shows a live Telegram preview for message nodes. Uses the repo's TextEditor.
import { api } from "../../api/client.js";
import { Icon } from "../Icon.jsx";
import { TextEditor } from "../TextEditor.jsx";
import { TelegramPreview } from "./TelegramPreview.jsx";
import { TRIGGERS, CONDITIONS, UNITS, BUTTON_STYLES, BUTTON_ACTIONS, splitDelay } from "./dripModel.js";

async function uploadDripMedia(file, onPatch) {
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await api.raw("/support/drip/upload", { method: "POST", headers: {}, body: fd });
    onPatch({ media: { kind: r.media_kind, url: r.media_url, name: file.name, size: "" } });
  } catch {
    /* ignore — upload failed */
  }
}

function ButtonsEditor({ buttons, onChange }) {
  const upd = (i, p) => onChange(buttons.map((b, x) => (x === i ? { ...b, ...p } : b)));
  const del = (i) => onChange(buttons.filter((_, x) => x !== i));
  const add = () => onChange([...buttons, { text: "", action: "", url: "", style: "" }]);
  return (
    <div className="di-btn-list">
      {buttons.map((b, i) => (
        <div className="di-btn-row" key={i}>
          <button className="di-btn-x" title="Удалить кнопку" onClick={() => del(i)}><Icon name="x" size={13} /></button>
          <div className="di-field span2">
            <span className="di-mini-label">Текст кнопки</span>
            <input className="di-input-sm" value={b.text} placeholder="Подключить за 1 клик" onChange={(e) => upd(i, { text: e.target.value })} />
          </div>
          <div className="di-field">
            <span className="di-mini-label">Действие</span>
            <select className="di-select-sm" value={b.action || ""} onChange={(e) => upd(i, { action: e.target.value })}>
              {Object.entries(BUTTON_ACTIONS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div className="di-field">
            <span className="di-mini-label">Стиль</span>
            <select className="di-select-sm" value={b.style || ""} onChange={(e) => upd(i, { style: e.target.value })}>
              {Object.entries(BUTTON_STYLES).map(([v, s]) => <option key={v} value={v}>{s.l}</option>)}
            </select>
          </div>
          {!b.action && (
            <div className="di-field span2">
              <span className="di-mini-label">URL</span>
              <input className="di-input-sm mono" value={b.url || ""} placeholder="https://t.me/…" onChange={(e) => upd(i, { url: e.target.value })} />
            </div>
          )}
        </div>
      ))}
      <button className="btn btn-sm" style={{ alignSelf: "flex-start" }} onClick={add}><Icon name="plus" size={13} /> Кнопка</button>
    </div>
  );
}

export function DripInspector({ node, chainStats, onPatch, onClose, onDelete, onAddBranch }) {
  if (!node) {
    return (
      <aside className="di">
        <div className="di-scroll" style={{ alignItems: "center", justifyContent: "center", textAlign: "center", color: "var(--text-muted)" }}>
          <Icon name="git-branch" size={26} style={{ opacity: 0.4, marginBottom: 10 }} />
          <div style={{ fontSize: 13 }}>Выберите шаг на схеме слева,<br />чтобы открыть редактор и превью</div>
        </div>
      </aside>
    );
  }

  const [val, unit] = splitDelay(node.delay_seconds);
  const setDelay = (v, u) => onPatch({ delay_seconds: Math.max(0, Math.round((v ?? val) * (u ?? unit))) });
  const [rptVal, rptUnit] = splitDelay(node.repeatInterval || node.delay_seconds || 86400);
  const setRpt = (v, u) => onPatch({ repeatInterval: Math.max(0, Math.round((v ?? rptVal) * (u ?? rptUnit))) });

  const TYPE_META = {
    trigger:   { ic: "zap", tone: "var(--accent)", title: "Триггер", sub: "Точка входа в цепочку" },
    message:   { ic: "message-square", tone: "var(--info)", title: "Сообщение", sub: "Шаг с текстом и кнопками" },
    condition: { ic: "git-branch", tone: "var(--warn)", title: "Условие", sub: "Ветвление по состоянию юзера" },
    end:       { ic: node.conversion ? "check-circle" : "flag", tone: node.conversion ? "var(--ok)" : "var(--text-muted)", title: node.conversion ? "Конверсия" : "Финал", sub: "Завершение ветки" },
  };
  const tm = TYPE_META[node.type];

  return (
    <aside className="di">
      <div className="di-head">
        <span className="di-head-ic" style={{ background: `color-mix(in oklch, ${tm.tone} 18%, var(--surface))`, color: tm.tone }}>
          <Icon name={tm.ic} size={15} />
        </span>
        <div className="di-head-tt">
          <div className="di-head-title">{tm.title}</div>
          <div className="di-head-sub">{tm.sub}</div>
        </div>
        <button className="btn btn-ghost btn-icon" style={{ marginLeft: "auto" }} onClick={onClose} title="Закрыть"><Icon name="x" size={15} /></button>
      </div>

      <div className="di-scroll">
        {node.type === "message" && (
          <>
            <div className="di-sec">
              <div className="di-sec-h"><Icon name="eye" size={13} /> Превью в Telegram</div>
              <TelegramPreview node={node} />
            </div>

            <div className="di-sec">
              <div className="di-sec-h"><Icon name="clock" size={13} /> Расписание</div>
              <div className="di-row">
                <div className="di-field">
                  <span className="di-label">Отправить через</span>
                  <input className="di-input-sm" type="number" min={0} style={{ width: 88 }} value={val} onChange={(e) => setDelay(Number(e.target.value), unit)} />
                </div>
                <div className="di-field">
                  <span className="di-label">&nbsp;</span>
                  <select className="di-select-sm" style={{ width: 110 }} value={unit} onChange={(e) => setDelay(val, Number(e.target.value))}>
                    {UNITS.map((u) => <option key={u.v} value={u.v}>{u.long}</option>)}
                  </select>
                </div>
              </div>
              <div className="di-hint">Отсчёт начинается после предыдущего шага цепочки.</div>
            </div>

            <div className="di-sec">
              <div className="di-sec-h"><Icon name="refresh" size={13} /> Повторы (напоминания)</div>
              <div className="di-row">
                <div className="di-field">
                  <span className="di-label">Сколько раз</span>
                  <input className="di-input-sm" type="number" min={1} style={{ width: 84 }}
                    value={node.repeat ?? 1}
                    onChange={(e) => onPatch({ repeat: Math.max(1, Number(e.target.value) || 1) })} />
                </div>
                <div className="di-field">
                  <span className="di-label">Каждые</span>
                  <input className="di-input-sm" type="number" min={1} style={{ width: 70 }}
                    value={rptVal} onChange={(e) => setRpt(Number(e.target.value), rptUnit)} />
                </div>
                <div className="di-field">
                  <span className="di-label">&nbsp;</span>
                  <select className="di-select-sm" style={{ width: 100 }} value={rptUnit} onChange={(e) => setRpt(rptVal, Number(e.target.value))}>
                    {UNITS.map((u) => <option key={u.v} value={u.v}>{u.long}</option>)}
                  </select>
                </div>
              </div>
              <div className="di-hint">
                {(node.repeat ?? 1) > 1
                  ? "Напоминание прекратится само, как только «условие отправки» выше перестанет выполняться (юзер сделал действие)."
                  : "1 = один раз. Поставь больше, чтобы напоминать, пока держится «условие отправки» выше."}
              </div>
            </div>

            <div className="di-sec">
              <div className="di-sec-h"><Icon name="git-branch" size={13} /> Условие отправки</div>
              <select className="di-select-sm" value={node.condition} onChange={(e) => onPatch({ condition: e.target.value })}>
                {Object.entries(CONDITIONS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <div className="di-hint">Если условие не выполнено — пользователь выходит из цепочки и шаг не отправляется.</div>
            </div>

            <div className="di-sec">
              <div className="di-sec-h"><Icon name="message-square" size={13} /> Текст сообщения</div>
              <TextEditor value={node.text} onChange={(v) => onPatch({ text: v })} placeholder="Заметили, ты ещё не подключился — давай помогу 👇" minHeight={120} />
              <div className="di-hint">Переменные: <span className="mono">{"{name}"}</span>, <span className="mono">{"{referral}"}</span>, <span className="mono">{"{plan}"}</span>, <span className="mono">{"{days_left}"}</span>.</div>
            </div>

            <div className="di-sec">
              <div className="di-sec-h"><Icon name="image" size={13} /> Медиа</div>
              {node.media ? (
                <div className="di-media">
                  <span className="di-media-ph"><Icon name="image" size={18} /></span>
                  <div className="di-media-txt">
                    <div className="di-media-name">{node.media.name}</div>
                    <div className="di-media-meta">{node.media.kind}{node.media.size ? ` · ${node.media.size}` : ""}</div>
                  </div>
                  <button className="btn btn-ghost btn-icon" title="Убрать" onClick={() => onPatch({ media: null })}><Icon name="trash" size={14} /></button>
                </div>
              ) : (
                <label className="di-media" style={{ cursor: "pointer" }}>
                  <span className="di-media-ph"><Icon name="upload" size={18} /></span>
                  <div className="di-media-txt">
                    <div className="di-media-name">Загрузить фото или видео</div>
                    <div className="di-media-meta muted">нажмите, чтобы выбрать</div>
                  </div>
                  <input
                    type="file"
                    accept="image/*,video/*"
                    style={{ display: "none" }}
                    onChange={(e) => uploadDripMedia(e.target.files?.[0], onPatch)}
                  />
                </label>
              )}
            </div>

            <div className="di-sec">
              <div className="di-sec-h"><Icon name="link" size={13} /> Inline-кнопки</div>
              <ButtonsEditor buttons={node.buttons || []} onChange={(b) => onPatch({ buttons: b })} />
            </div>

            {onAddBranch && (
              <div className="di-sec">
                <div className="di-sec-h"><Icon name="git-branch" size={13} /> Ветвление</div>
                <button className="btn btn-sm" style={{ alignSelf: "flex-start" }} onClick={() => onAddBranch(node.id)}>
                  <Icon name="git-branch" size={13} /> Добавить развилку после
                </button>
                <div className="di-hint">Создаёт условие с двумя ветками («да» / «нет») и шагом в каждой.</div>
              </div>
            )}
          </>
        )}

        {node.type === "condition" && (
          <>
            <div className="di-sec">
              <div className="di-sec-h"><Icon name="git-branch" size={13} /> Проверка</div>
              <select className="di-select-sm" value={node.check} onChange={(e) => onPatch({ check: e.target.value })}>
                {Object.entries(CONDITIONS).filter(([v]) => v !== "always").map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <div className="di-hint">Движок проверяет состояние юзера в момент шага и направляет его по одной из веток.</div>
            </div>
            <div className="di-sec">
              <div className="di-sec-h"><Icon name="git-branch" size={13} /> Метки веток</div>
              <div className="di-row">
                <div className="di-field" style={{ flex: 1 }}>
                  <span className="di-mini-label" style={{ color: "var(--ok)" }}>Ветка «да»</span>
                  <input className="di-input-sm" value={node.yes} onChange={(e) => onPatch({ yes: e.target.value })} />
                </div>
                <div className="di-field" style={{ flex: 1 }}>
                  <span className="di-mini-label" style={{ color: "var(--bad)" }}>Ветка «нет»</span>
                  <input className="di-input-sm" value={node.no} onChange={(e) => onPatch({ no: e.target.value })} />
                </div>
              </div>
            </div>
            <div className="di-note"><Icon name="info" size={15} /> Условие не отправляет сообщение — оно лишь разделяет поток. Каждая ветка может вести к своим шагам и снова сливаться.</div>
          </>
        )}

        {node.type === "trigger" && (
          <>
            <div className="di-sec">
              <div className="di-sec-h"><Icon name="zap" size={13} /> Событие-триггер</div>
              <select className="di-select-sm" value={node.trigger_event} onChange={(e) => onPatch({ trigger_event: e.target.value })}>
                {Object.entries(TRIGGERS).map(([v, t]) => <option key={v} value={v}>{t.label}</option>)}
              </select>
              <div className="di-hint">Цепочка запускается автоматически, как только пользователь совершает это событие.</div>
            </div>
            {chainStats && (
              <div className="di-note"><Icon name="user" size={15} /> Сейчас в цепочке <b style={{ color: "var(--text)" }}>{chainStats.active?.toLocaleString("ru-RU")}</b> пользователей. Изменение триггера не затронет уже запущенных.</div>
            )}
          </>
        )}

        {node.type === "end" && (
          <>
            <div className="di-sec">
              <div className="di-sec-h"><Icon name="flag" size={13} /> Завершение</div>
              <div className="di-field">
                <span className="di-label">Подпись точки</span>
                <input className="di-input-sm" value={node.label} onChange={(e) => onPatch({ label: e.target.value })} />
              </div>
            </div>
            <div className="di-sec">
              <div className="db-toggle" style={{ justifyContent: "space-between", width: "100%" }}>
                <span>Отметить как конверсию</span>
                <button className="db-switch" data-on={node.conversion ? "true" : "false"} onClick={() => onPatch({ conversion: !node.conversion })} />
              </div>
              <div className="di-hint">Конверсионные финалы подсвечиваются и учитываются в статистике эффективности цепочки.</div>
            </div>
          </>
        )}
      </div>

      {node.type !== "trigger" && (
        <div className="di-foot">
          <button className="btn btn-sm"><Icon name="copy" size={13} /> Дублировать</button>
          <button className="btn btn-sm btn-danger" style={{ marginLeft: "auto" }} onClick={() => onDelete(node.id)}><Icon name="trash" size={13} /> Удалить шаг</button>
        </div>
      )}
    </aside>
  );
}
