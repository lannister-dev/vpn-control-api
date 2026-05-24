export function Field({ label, hint, children }) {
  return (
    <div className="form-field">
      <label className="form-label">
        {label}
        {hint && <span className="form-hint"> · {hint}</span>}
      </label>
      {children}
    </div>
  );
}

export function Row({ children }) {
  return <div className="form-row">{children}</div>;
}
