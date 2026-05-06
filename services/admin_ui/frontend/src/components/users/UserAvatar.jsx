export function UserAvatar({ name, size = "md", muted }) {
  const initials = (name || "?").trim().split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase() || "?";
  const cls = ["u-avatar", size === "lg" ? "lg" : size === "huge" ? "huge" : "", muted ? "muted" : ""].filter(Boolean).join(" ");
  return (
    <div className={cls}>
      <span>{initials}</span>
    </div>
  );
}
