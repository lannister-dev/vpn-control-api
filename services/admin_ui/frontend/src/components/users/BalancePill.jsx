export function BalancePill({ amount, currency = "₽" }) {
  const n = Number(amount || 0);
  const tone = n > 0 ? "ok" : n < 0 ? "bad" : "zero";
  const sign = n > 0 ? "+" : n < 0 ? "−" : "";
  const fmt = Math.abs(n).toLocaleString("ru-RU");
  return (
    <span className={`u-balance ${tone}`}>
      {sign}{fmt} {currency}
    </span>
  );
}
