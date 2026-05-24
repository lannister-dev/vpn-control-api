export const UNKNOWN_FLAG = "\uD83C\uDF10";

export const REGION_TO_COUNTRY_CODE = {
  fi: "FI", hel: "FI", de: "DE", fra: "DE", nl: "NL", ams: "NL", pl: "PL", waw: "PL",
  gb: "GB", uk: "GB", lon: "GB", fr: "FR", par: "FR", es: "ES", mad: "ES", it: "IT",
  rom: "IT", mil: "IT", se: "SE", sto: "SE", no: "NO", osl: "NO", dk: "DK", cph: "DK",
  ch: "CH", zrh: "CH", at: "AT", vie: "AT", cz: "CZ", prg: "CZ", us: "US", nyc: "US",
  lax: "US", ca: "CA", tor: "CA", sg: "SG", jp: "JP", tok: "JP", kr: "KR", sel: "KR",
  hk: "HK", au: "AU", syd: "AU", in: "IN", tr: "TR", ua: "UA", ru: "RU", kz: "KZ",
  ae: "AE", dxb: "AE", br: "BR", mx: "MX", il: "IL", lv: "LV", rig: "LV",
};

export const COUNTRY_CODE_TO_NAME = {
  FI: "Finland", DE: "Germany", NL: "Netherlands", PL: "Poland", GB: "United Kingdom",
  FR: "France", ES: "Spain", IT: "Italy", SE: "Sweden", NO: "Norway", DK: "Denmark",
  CH: "Switzerland", AT: "Austria", CZ: "Czechia", US: "United States", CA: "Canada",
  SG: "Singapore", JP: "Japan", KR: "South Korea", HK: "Hong Kong", AU: "Australia",
  IN: "India", TR: "Turkey", UA: "Ukraine", RU: "Russia", KZ: "Kazakhstan",
  AE: "United Arab Emirates", BR: "Brazil", MX: "Mexico", IL: "Israel", LV: "Latvia",
};

export function extractRegionTokens(region) {
  return String(region || "").toLowerCase().split(/[^a-zA-Z]+/).filter(Boolean);
}

export function countryCodeFromRegion(region) {
  if (region == null) return null;
  const clean = String(region).trim().toLowerCase();
  if (!clean) return null;
  const tokens = extractRegionTokens(clean);
  for (const t of tokens) { const mapped = REGION_TO_COUNTRY_CODE[t]; if (mapped) return mapped; }
  for (const t of tokens) { if (t.length === 2 && /^[a-z]+$/i.test(t)) return t.toUpperCase(); }
  return null;
}

export function flagEmojiFromCountryCode(code) {
  if (!code) return UNKNOWN_FLAG;
  const cc = String(code).trim().toUpperCase();
  if (cc.length !== 2 || !/^[A-Z]+$/.test(cc)) return UNKNOWN_FLAG;
  const base = "A".charCodeAt(0);
  return String.fromCodePoint(0x1f1e6 + cc.charCodeAt(0) - base, 0x1f1e6 + cc.charCodeAt(1) - base);
}

export function nodeGeo(region) {
  const code = countryCodeFromRegion(region);
  const country = code ? (COUNTRY_CODE_TO_NAME[code] || code) : "Unknown";
  const flag = flagEmojiFromCountryCode(code);
  return { code, country, flag, regionText: String(region || "unknown") };
}

export function zoneFlag(zoneByCode, zoneCode, fallbackRegion) {
  const z = zoneByCode && zoneCode ? zoneByCode[zoneCode] : null;
  if (z && z.emoji) return z.emoji;
  return nodeGeo(fallbackRegion).flag;
}
