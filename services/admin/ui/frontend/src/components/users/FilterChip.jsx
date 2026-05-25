import { Icon } from "../Icon.jsx";

export function FilterChip({ icon, label, value, applied, dashed, onRemove, onClick }) {
  const cls = ["u-fchip", applied ? "applied" : "", dashed ? "add" : ""].filter(Boolean).join(" ");
  return (
    <span className={cls} onClick={onClick}>
      {icon && <Icon name={icon} size={12} className="u-fchip-ic" />}
      <span>{label}</span>
      {value && <span className="u-fchip-v">: {value}</span>}
      {applied && (
        <span className="u-fchip-x" onClick={(e) => { e.stopPropagation(); onRemove?.(); }}>
          <Icon name="x" size={10} />
        </span>
      )}
    </span>
  );
}

export function FilterPresets({ items, value, onPick }) {
  return (
    <div className="u-presets">
      {items.map((p) => (
        <button
          key={p.id}
          className={`u-preset ${value === p.id ? "active" : ""}`}
          onClick={() => onPick?.(p.id)}
        >
          {p.icon && <Icon name={p.icon} size={12} />}
          {p.label}
          {p.count != null && <span className="u-preset-count">{p.count}</span>}
        </button>
      ))}
    </div>
  );
}
