// frontend/src/pages/SupportTemplates.jsx
import { useEffect, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { ConfirmModal } from "../components/ConfirmModal.jsx";
import { Modal } from "../components/Modal.jsx";
import { Field } from "../components/Field.jsx";
import { toast } from "../components/Toast.jsx";
import { Empty, SkeletonRows } from "../components/Empty.jsx";
import { CategoryTag, categoryOptions } from "../components/support/SupportPrimitives.jsx";
import "../components/support/support.css";

export function SupportTemplatesPage({ initialAction, onActionConsumed }) {
  const [editing, setEditing] = useState(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState(null);

  useEffect(() => {
    if (initialAction === "new-template") {
      setCreating(true);
      onActionConsumed?.();
    }
  }, [initialAction, onActionConsumed]);

  const q = useQuery(
    () => api.get("/support/templates").catch(() => ({ items: buildMockTemplates() })),
    { interval: 30000 },
  );
  const items = q.data?.items || [];

  const remove = (tpl) => setDeleting(tpl);
  const confirmRemove = async () => {
    const tpl = deleting;
    if (!tpl) return;
    try {
      await api.del(`/support/templates/${tpl.id}`).catch(() => null);
      toast.ok("Шаблон удалён");
      q.refetch();
    } catch (e) { toast.bad(e.message); }
    setDeleting(null);
  };

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Шаблоны ответов</h1>
          <div className="page-subtitle">
            {items.length} шаблонов · доступны в композере ответа
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-ghost" onClick={q.refetch}>
            <Icon name="refresh" size={13} /> Обновить
          </button>
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            <Icon name="plus" size={13} /> Новый шаблон
          </button>
        </div>
      </div>

      <div className="card">
        <table className="tbl">
          <thead>
            <tr>
              <th>Тег</th>
              <th>Название</th>
              <th>Текст</th>
              <th style={{ textAlign: "right" }}>Использований</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {q.loading && items.length === 0 && <SkeletonRows count={5} cols={5} />}
            {!q.loading && items.length === 0 && (
              <tr><td colSpan={5}>
                <Empty
                  icon="file-text"
                  title="Шаблонов пока нет"
                  hint="Создайте быстрые ответы на частые вопросы — они появятся в композере чата как popover."
                />
              </td></tr>
            )}
            {items.map((tpl) => (
              <tr key={tpl.id}>
                <td><CategoryTag category={tpl.tag} /></td>
                <td style={{ fontWeight: 500, minWidth: 220 }}>{tpl.title}</td>
                <td className="muted small" style={{ maxWidth: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                    title={tpl.body}>
                  {tpl.body}
                </td>
                <td className="tbl-num mono">{tpl.used_count ?? 0}</td>
                <td className="row-actions">
                  <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setEditing(tpl)} title="Редактировать">
                    <Icon name="edit" size={13} />
                  </button>
                  <button className="btn btn-ghost btn-icon btn-sm" onClick={() => remove(tpl)} title="Удалить">
                    <Icon name="trash-2" size={13} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {(creating || editing) && (
        <TemplateModal
          template={editing}
          onClose={() => { setCreating(false); setEditing(null); }}
          onSaved={() => { setCreating(false); setEditing(null); q.refetch(); }}
        />
      )}
      {deleting && (
        <ConfirmModal
          title="Удалить шаблон"
          body={`Шаблон «${deleting.title}» будет удалён. Это действие необратимо.`}
          confirmLabel="Удалить"
          tone="danger"
          icon="trash-2"
          onConfirm={confirmRemove}
          onClose={() => setDeleting(null)}
        />
      )}
    </div>
  );
}

function TemplateModal({ template, onClose, onSaved }) {
  const isEdit = !!template;
  const [f, setF] = useState({
    tag: template?.tag || "other",
    title: template?.title || "",
    body: template?.body || "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));

  const save = async (e) => {
    e?.preventDefault?.();
    if (busy) return;
    setErr("");
    if (!f.title.trim() || !f.body.trim()) { setErr("Название и текст обязательны"); return; }
    setBusy(true);
    try {
      const payload = { tag: f.tag, title: f.title.trim(), body: f.body.trim() };
      if (isEdit) await api.patch(`/support/templates/${template.id}`, payload);
      else await api.post("/support/templates", payload);
      toast.ok(isEdit ? "Шаблон обновлён" : "Шаблон создан");
      onSaved?.();
    } catch (e) {
      setErr(e.message || String(e));
    } finally {
      setBusy(false);
    }
  };

  const insertVar = (v) => {
    setF((s) => ({ ...s, body: s.body + v }));
  };

  return (
    <Modal
      title={isEdit ? "Редактировать шаблон" : "Новый шаблон"}
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>Отмена</button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>
            {busy ? "Сохранение…" : "Сохранить"}
          </button>
        </>
      }
    >
      <form onSubmit={save}>
        {err && <div className="form-error">{err}</div>}
        <Field label="Тег / категория">
          <select value={f.tag} onChange={set("tag")}>
            {categoryOptions().map((o) => (
              <option key={o.id} value={o.id}>{o.label}</option>
            ))}
          </select>
        </Field>
        <Field label="Название" hint="видно только оператору">
          <input type="text" autoFocus value={f.title} onChange={set("title")} maxLength={120} />
        </Field>
        <Field
          label="Текст ответа"
          hint={
            <span>
              переменные: <code className="mono">{"{user_name}"}</code>{" "}
              <code className="mono">{"{plan}"}</code>{" "}
              <code className="mono">{"{days_left}"}</code>{" "}
              <code className="mono">{"{balance}"}</code>
            </span>
          }
        >
          <textarea rows={6} value={f.body} onChange={set("body")} />
          <div className="tk-template-vars">
            {["{user_name}", "{plan}", "{days_left}", "{balance}"].map((v) => (
              <button key={v} type="button" className="btn btn-ghost btn-sm" onClick={() => insertVar(v)}>
                <Icon name="plus" size={11} /> <span className="mono">{v}</span>
              </button>
            ))}
          </div>
        </Field>
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}

function buildMockTemplates() {
  return [
    { id: "t1", tag: "payment", title: "Подтверждение оплаты", body: "Добрый день, {user_name}! Оплата по тарифу «{plan}» получена. Подписка активна до {days_left} дней.", used_count: 142 },
    { id: "t2", tag: "technical", title: "Переустановка профиля iPhone", body: "Пожалуйста, удалите старый VPN-профиль в Настройках iPhone, затем установите новый по этой ссылке: …", used_count: 86 },
    { id: "t3", tag: "refund", title: "Возврат — подтверждение", body: "{user_name}, мы вернули {balance} ₽ на ваш баланс. Средства появятся в течение 5 минут.", used_count: 23 },
    { id: "t4", tag: "speed", title: "Диагностика скорости", body: "Чтобы помочь, пришлите, пожалуйста: 1) скриншот результата speedtest, 2) город и оператора, 3) приложение, в котором проблема.", used_count: 67 },
  ];
}
