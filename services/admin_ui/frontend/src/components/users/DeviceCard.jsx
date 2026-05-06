import { Icon } from "../Icon.jsx";

function fmtSeen(iso) {
  if (!iso) return "—";
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (m < 1) return "сейчас";
  if (m < 60) return `${m} мин назад`;
  if (m < 60 * 24) return `${Math.round(m / 60)} ч назад`;
  return `${Math.round(m / 60 / 24)} д назад`;
}

function shortenUA(ua) {
  if (!ua) return "—";
  return ua.length > 64 ? ua.slice(0, 64) + "…" : ua;
}

export function DeviceCard({ device, onCopy, onRevoke }) {
  return (
    <div className="u-devcard">
      <div className="u-devcard-icon">
        <Icon name="monitor" size={18} />
      </div>
      <div className="u-devcard-meta">
        <div className="u-devcard-top">
          <span className="mono small">{String(device.hwid_hash || device.id).slice(0, 16)}…</span>
          {!device.is_active && <span className="u-devcard-revoked">отозвано</span>}
        </div>
        <div className="u-devcard-sub" title={device.user_agent || ""}>
          <span className="muted">{shortenUA(device.user_agent)}</span>
          <span className="u-devcard-sep">·</span>
          <span className="muted">{fmtSeen(device.last_seen_at)}</span>
        </div>
      </div>
      <div className="u-devcard-actions">
        {onCopy && (
          <button className="btn btn-ghost btn-icon btn-sm" onClick={() => onCopy(device)} title="Копировать HWID">
            <Icon name="copy" size={12} />
          </button>
        )}
        {device.is_active && onRevoke && (
          <button className="btn btn-ghost btn-icon btn-sm" onClick={() => onRevoke(device)} title="Отозвать">
            <Icon name="shield-off" size={12} />
          </button>
        )}
      </div>
    </div>
  );
}
