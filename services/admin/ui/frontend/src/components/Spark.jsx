export function Spark({ data, color = "currentColor", w = 120, h = 32, filled = true }) {
  if (!data || data.length < 2) {
    return <svg className="spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`} />;
  }
  const min = Math.min(...data); const max = Math.max(...data);
  const pad = 2;
  const stepX = (w - pad * 2) / (data.length - 1);
  const norm = (v) => h - pad - ((v - min) / (max - min || 1)) * (h - pad * 2);
  const line = data.map((v, i) => `${i === 0 ? "M" : "L"} ${pad + i * stepX} ${norm(v)}`).join(" ");
  const fill = `${line} L ${w - pad} ${h} L ${pad} ${h} Z`;
  return (
    <svg className="spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      {filled && <path d={fill} fill={color} opacity="0.15" />}
      <path d={line} stroke={color} fill="none" strokeWidth="1.5" />
    </svg>
  );
}
