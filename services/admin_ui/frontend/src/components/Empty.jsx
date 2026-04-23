import { Icon } from "./Icon.jsx";

export function Empty({ icon = "activity", title = "Пусто", hint }) {
  return (
    <div className="empty-state">
      <div className="empty-icon"><Icon name={icon} size={18} /></div>
      <div className="empty-title">{title}</div>
      {hint && <div className="empty-hint">{hint}</div>}
    </div>
  );
}

export function SkeletonRows({ count = 4, cols = 5 }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <tr key={i}>
          {Array.from({ length: cols }).map((_, j) => (
            <td key={j}><span className="skel skel-cell" style={{ width: j === 0 ? 140 : 60 + (j * 11) % 40 }} /></td>
          ))}
        </tr>
      ))}
    </>
  );
}
