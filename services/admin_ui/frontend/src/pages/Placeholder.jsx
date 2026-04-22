export function Placeholder({ title, hint }) {
  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">{title}</h1>
      </div>
      <div className="card">
        <div className="muted">{hint || "Страница будет реализована в следующей итерации."}</div>
      </div>
    </div>
  );
}
