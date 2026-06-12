export const PROVIDER_LABELS = {
  platega: "Platega",
  stars: "Telegram Stars",
  crypto: "Crypto",
  freekassa: "FreeKassa",
  balance: "С баланса",
  free: "Free / trial",
};
export const PROVIDER_COLORS = {
  platega: "var(--accent)",
  stars: "var(--info)",
  crypto: "var(--warn)",
  freekassa: "oklch(0.62 0.13 320)",
  balance: "var(--text-muted)",
  free: "var(--text-faint)",
};

export const ORDER_TYPE_LABELS = {
  plan_purchase: "Покупка тарифа",
  subscription_renewal: "Продление",
  device_slots: "Слоты устройств",
  top_up: "Пополнение",
};
export const ORDER_TYPE_COLORS = {
  subscription_renewal: "var(--accent)",
  plan_purchase: "var(--ok)",
  device_slots: "var(--info)",
  top_up: "var(--text-muted)",
};

export const PERIOD_LABELS = {
  1: "1 месяц",
  3: "3 месяца",
  6: "6 месяцев",
  12: "12 месяцев",
};
export const PERIOD_COLORS = {
  1: "var(--accent)",
  3: "var(--info)",
  6: "var(--ok)",
  12: "var(--warn)",
};

export const KIND_LABELS = {
  infrastructure: "Инфраструктура",
  gateway_fee: "Эквайринг",
  domain_cdn: "Домены / CDN",
  marketing: "Маркетинг",
  salary: "Зарплаты",
  referral: "Реферальные",
  tax: "Налоги",
  other: "Прочее",
};
export const KIND_COLORS = {
  infrastructure: "var(--spend)",
  salary: "oklch(0.60 0.09 235)",
  marketing: "oklch(0.62 0.11 200)",
  referral: "oklch(0.64 0.10 165)",
  domain_cdn: "oklch(0.56 0.09 285)",
  tax: "var(--bad)",
  gateway_fee: "var(--text-muted)",
  other: "var(--text-faint)",
};
export const KIND_CHIP = {
  infrastructure: "info",
  salary: "info",
  marketing: "info",
  referral: "ok",
  domain_cdn: "muted",
  tax: "bad",
  gateway_fee: "muted",
  other: "muted",
};

export const FUNDING = {
  cash: { label: "Живые деньги", color: "var(--ok)" },
  balance: { label: "С баланса", color: "var(--info)" },
  free: { label: "Пробные", color: "var(--text-muted)" },
};
const PROVIDER_FUNDING = {
  platega: "cash", crypto: "cash", freekassa: "cash", stars: "cash",
  balance: "balance", free: "free",
};
export function fundingOf(provider) {
  return PROVIDER_FUNDING[provider] || "cash";
}

export const STATUS_META = {
  completed: { label: "completed", cls: "ok" },
  paid: { label: "paid", cls: "info" },
  pending: { label: "pending", cls: "warn" },
  expired: { label: "expired", cls: "muted" },
  refunded: { label: "refunded", cls: "bad" },
  failed: { label: "failed", cls: "bad" },
};

export function waterfallLabel(key) {
  if (key === "gross") return "Gross revenue";
  if (key === "commissions") return "− Комиссии";
  if (key === "profit") return "Чистая прибыль";
  return `− ${KIND_LABELS[key] || key}`;
}
