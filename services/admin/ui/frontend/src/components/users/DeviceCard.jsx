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

function deviceIcon(platform) {
  const p = (platform || "").toLowerCase();
  if (p.includes("ios") || p.includes("iphone") || p.includes("ipad")) return "smartphone";
  if (p.includes("android")) return "smartphone";
  if (p.includes("mac")) return "monitor";
  if (p.includes("windows") || p.includes("linux")) return "monitor";
  return "monitor";
}

function deviceTitle(device) {
  if (device.device_model && device.device_model.trim()) return device.device_model.trim();
  if (device.platform && device.platform.trim()) {
    const p = device.platform.trim();
    return p.charAt(0).toUpperCase() + p.slice(1);
  }
  return "Устройство";
}

export function DeviceCard({ device, onCopy, onRevoke, onRestore }) {
  const title = deviceTitle(device);
  const osLine = [device.platform, device.os_version].filter((v) => v && v.trim()).join(" ");

  return (
    <div className="u-devcard">
      <div className="u-devcard-icon">
        <Icon name={deviceIcon(device.platform)} size={18} />
      </div>
      <div className="u-devcard-meta">
        <div className="u-devcard-top">
          <span style={{ fontWeight: 500 }}>{title}</span>
          {osLine && <span className="muted small" style={{ marginLeft: 6 }}>{osLine}</span>}
          {!device.is_active && <span className="u-devcard-revoked" style={{ marginLeft: 6 }}>отозвано</span>}
        </div>
        <div className="u-devcard-sub" title={device.user_agent || ""}>
          <span className="mono muted">{String(device.hwid_hash || device.id).slice(0, 12)}…</span>
          <span className="u-devcard-sep">·</span>
          <span className="muted">{fmtSeen(device.last_seen_at)}</span>
          {device.user_agent && <>
            <span className="u-devcard-sep">·</span>
            <span className="u-devcard-ua muted">{shortenUA(device.user_agent)}</span>
          </>}
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
        {!device.is_active && onRestore && (
          <button className="btn btn-ghost btn-icon btn-sm" onClick={() => onRestore(device)} title="Вернуть устройство">
            <Icon name="rotate-cw" size={12} />
          </button>
        )}
      </div>
    </div>
  );
}
