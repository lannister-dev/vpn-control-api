// Mock data for VPN Control Panel prototype
(function () {
  const NODES = [
    { id: 'nd_7f2a9c', name: 'fra-entry-01', region: 'eu-central', flag: '🇩🇪', health: 'ok', state: 'active', load: 0.62, hb: '2s', routes: 12, role: 'entry', cpu: 34, traffic: '1.2TB' },
    { id: 'nd_a01b4e', name: 'fra-entry-02', region: 'eu-central', flag: '🇩🇪', health: 'ok', state: 'active', load: 0.41, hb: '1s', routes: 9, role: 'entry', cpu: 22, traffic: '820GB' },
    { id: 'nd_c9e1d2', name: 'ams-backend-01', region: 'eu-west', flag: '🇳🇱', health: 'warn', state: 'active', load: 0.88, hb: '4s', routes: 24, role: 'backend', cpu: 76, traffic: '3.4TB' },
    { id: 'nd_3b7f10', name: 'ams-backend-02', region: 'eu-west', flag: '🇳🇱', health: 'ok', state: 'active', load: 0.55, hb: '2s', routes: 18, role: 'backend', cpu: 41, traffic: '2.1TB' },
    { id: 'nd_1e5b4a', name: 'ams-backend-03', region: 'eu-west', flag: '🇳🇱', health: 'ok', state: 'active', load: 0.34, hb: '1s', routes: 10, role: 'backend', cpu: 27, traffic: '1.1TB' },
    { id: 'nd_5d8aa1', name: 'sgp-entry-01', region: 'ap-southeast', flag: '🇸🇬', health: 'ok', state: 'active', load: 0.33, hb: '3s', routes: 7, role: 'entry', cpu: 19, traffic: '640GB' },
    { id: 'nd_9e0c27', name: 'sgp-backend-01', region: 'ap-southeast', flag: '🇸🇬', health: 'bad', state: 'draining', load: 0.12, hb: '47s', routes: 3, role: 'backend', cpu: 8, traffic: '210GB' },
    { id: 'nd_6b4d93', name: 'tyo-backend-01', region: 'ap-northeast', flag: '🇯🇵', health: 'ok', state: 'active', load: 0.47, hb: '2s', routes: 8, role: 'backend', cpu: 31, traffic: '910GB' },
    { id: 'nd_2a6d5b', name: 'nyc-entry-01', region: 'us-east', flag: '🇺🇸', health: 'ok', state: 'active', load: 0.71, hb: '1s', routes: 15, role: 'entry', cpu: 52, traffic: '1.8TB' },
    { id: 'nd_4f1e88', name: 'nyc-backend-01', region: 'us-east', flag: '🇺🇸', health: 'ok', state: 'active', load: 0.58, hb: '2s', routes: 21, role: 'backend', cpu: 44, traffic: '2.7TB' },
    { id: 'nd_d2c701', name: 'nyc-backend-02', region: 'us-east', flag: '🇺🇸', health: 'ok', state: 'active', load: 0.49, hb: '1s', routes: 14, role: 'backend', cpu: 38, traffic: '1.9TB' },
    { id: 'nd_8c3021', name: 'lax-entry-01', region: 'us-west', flag: '🇺🇸', health: 'warn', state: 'active', load: 0.81, hb: '6s', routes: 11, role: 'entry', cpu: 69, traffic: '1.4TB' },
    { id: 'nd_a7f92b', name: 'lax-backend-01', region: 'us-west', flag: '🇺🇸', health: 'ok', state: 'active', load: 0.44, hb: '2s', routes: 9, role: 'backend', cpu: 29, traffic: '1.0TB' },
  ];

  const ROUTES = [
    // fra-entry-01 — 5 связей (показать fan-out)
    { id: 'rt_001', entry: 'fra-entry-01', backend: 'ams-backend-01', status: 'healthy', weight: 100, warmup: 100, latency: 8 },
    { id: 'rt_002', entry: 'fra-entry-01', backend: 'ams-backend-02', status: 'healthy', weight: 100, warmup: 100, latency: 12 },
    { id: 'rt_003', entry: 'fra-entry-01', backend: 'ams-backend-03', status: 'healthy', weight: 80, warmup: 100, latency: 14 },
    { id: 'rt_004', entry: 'fra-entry-01', backend: 'tyo-backend-01', status: 'healthy', weight: 40, warmup: 100, latency: 186 },
    { id: 'rt_005', entry: 'fra-entry-01', backend: 'nyc-backend-01', status: 'healthy', weight: 20, warmup: 100, latency: 94 },
    // fra-entry-02
    { id: 'rt_006', entry: 'fra-entry-02', backend: 'ams-backend-01', status: 'degraded', weight: 60, warmup: 100, latency: 142 },
    { id: 'rt_007', entry: 'fra-entry-02', backend: 'ams-backend-02', status: 'warming_up', weight: 20, warmup: 35, latency: 18 },
    { id: 'rt_008', entry: 'fra-entry-02', backend: 'ams-backend-03', status: 'healthy', weight: 100, warmup: 100, latency: 11 },
    // sgp-entry-01
    { id: 'rt_009', entry: 'sgp-entry-01', backend: 'sgp-backend-01', status: 'blocked', weight: 0, warmup: 100, latency: null },
    { id: 'rt_010', entry: 'sgp-entry-01', backend: 'tyo-backend-01', status: 'healthy', weight: 100, warmup: 100, latency: 48 },
    // nyc-entry-01
    { id: 'rt_011', entry: 'nyc-entry-01', backend: 'nyc-backend-01', status: 'healthy', weight: 100, warmup: 100, latency: 5 },
    { id: 'rt_012', entry: 'nyc-entry-01', backend: 'nyc-backend-02', status: 'healthy', weight: 100, warmup: 100, latency: 7 },
    { id: 'rt_013', entry: 'nyc-entry-01', backend: 'lax-backend-01', status: 'healthy', weight: 60, warmup: 100, latency: 62 },
    // lax-entry-01
    { id: 'rt_014', entry: 'lax-entry-01', backend: 'lax-backend-01', status: 'healthy', weight: 100, warmup: 100, latency: 4 },
    { id: 'rt_015', entry: 'lax-entry-01', backend: 'nyc-backend-01', status: 'suspected', weight: 40, warmup: 60, latency: 78 },
    { id: 'rt_016', entry: 'lax-entry-01', backend: 'nyc-backend-02', status: 'healthy', weight: 80, warmup: 100, latency: 66 },
  ];

  const ISSUES = [
    { severity: 'bad', title: 'sgp-backend-01 heartbeat потерян 47с', sub: '3 маршрута и 128 активных ключей затронуты', kind: 'node', target: 'nd_9e0c27', time: '3m' },
    { severity: 'bad', title: 'Маршрут rt_009 заблокирован probe-политикой', sub: 'sgp-entry-01 → sgp-backend-01 · 14 неудачных probe подряд', kind: 'route', target: 'rt_009', time: '4m' },
    { severity: 'warn', title: 'ams-backend-01 нагрузка 88%', sub: 'Предлагается drain и балансировка на ams-backend-02', kind: 'node', target: 'nd_c9e1d2', time: '12m' },
    { severity: 'warn', title: 'fra-entry-02 → ams-backend-01 latency 142мс (degraded)', sub: '2 синтетических probe провалились за последние 10м', kind: 'route', target: 'rt_006', time: '24m' },
    { severity: 'info', title: '3 команды в outbox ожидают подтверждения', sub: 'Задержка NATS 180мс, выше нормы', kind: 'transport', target: null, time: '38m' },
    { severity: 'warn', title: '47 подписок истекают в ближайшие 24ч', sub: '12 без автопродления', kind: 'subs', target: null, time: '1h' },
  ];

  const ACTIVITY = [
    { tone: 'ok', text: 'kate.shirokova мигрировала плейсмент 2d4f... на ams-backend-02', meta: 'admin · 2m назад' },
    { tone: 'warn', text: 'Warmup tick автоматически поднят до 60 для rt_006', meta: 'system · 8m назад' },
    { tone: 'ok', text: 'Создан план Pro-Yearly (1TB, 5 устройств)', meta: 'admin · 14m назад' },
    { tone: 'bad', text: 'rt_004 заблокирован: 14 неудачных probe_vpn подряд', meta: 'probe_policy · 24m назад' },
    { tone: 'ok', text: '128 ключей переданы на ams-backend-02 после drain sgp-backend-01', meta: 'system · 34m назад' },
    { tone: 'ok', text: 'Новый админ operator добавлен: d.petrov', meta: 'admin · 1h назад' },
  ];

  const COMMANDS = [
    { group: 'Перейти', items: [
      { label: 'Главная', icon: 'layout-dashboard', kbd: ['G', 'H'], tab: 'overview' },
      { label: 'Серверы', icon: 'server', kbd: ['G', 'S'], tab: 'nodes' },
      { label: 'Маршруты', icon: 'route', kbd: ['G', 'R'], tab: 'routes' },
      { label: 'Пользователи', icon: 'users', kbd: ['G', 'U'], tab: 'users' },
      { label: 'Трафик', icon: 'bar-chart', kbd: ['G', 'T'], tab: 'traffic' },
      { label: 'Probes', icon: 'radar', kbd: ['G', 'P'], tab: 'probes' },
    ]},
    { group: 'Действия', items: [
      { label: 'Создать сервер', icon: 'plus', kbd: ['N', 'S'], action: 'create-node' },
      { label: 'Создать маршрут', icon: 'plus', kbd: ['N', 'R'], action: 'create-route' },
      { label: 'Запустить миграцию плейсментов', icon: 'arrow-right', action: 'migrate' },
      { label: 'Сдвинуть warmup tick', icon: 'zap', action: 'warmup' },
      { label: 'Применить probe-политику (dry run)', icon: 'shield-check', action: 'probe-auto' },
    ]},
    { group: 'Инциденты', items: [
      { label: 'sgp-backend-01 — потерян heartbeat', icon: 'alert-circle', sub: 'critical · 3m', action: 'incident', target: 'nd_9e0c27' },
      { label: 'rt_004 — блокирован probe-политикой', icon: 'alert-triangle', sub: 'critical · 4m', action: 'incident', target: 'rt_004' },
      { label: 'ams-backend-01 — нагрузка 88%', icon: 'flame', sub: 'warn · 12m', action: 'incident', target: 'nd_c9e1d2' },
    ]},
    { group: 'Настройки', items: [
      { label: 'Переключить тему', icon: 'sun', action: 'toggle-theme' },
      { label: 'Плотность: Compact', icon: 'sliders', action: 'density-compact' },
      { label: 'Плотность: Comfortable', icon: 'sliders', action: 'density-comfortable' },
      { label: 'Плотность: Spacious', icon: 'sliders', action: 'density-spacious' },
      { label: 'Выход из сессии', icon: 'logout', action: 'logout' },
    ]},
  ];

  const PLANS = [
    {
      id: 'pl_free', name: 'Free', price: 0, currency: 'RUB', duration_days: 30,
      limit: 5 * 1024**3, devices: 1,
      state: 'active', visibility: 'public',
      features: { smart_routing: false, whitelist: false, p2p: false, all_regions: false, multi_protocol: false, priority_support: false },
      promo_codes: 0,
      created_h_ago: 8760,
    },
    {
      id: 'pl_basic', name: 'Basic', price: 199, currency: 'RUB', duration_days: 30,
      limit: 100 * 1024**3, devices: 3,
      state: 'active', visibility: 'public',
      features: { smart_routing: true, whitelist: false, p2p: false, all_regions: false, multi_protocol: false, priority_support: false },
      promo_codes: 2,
      created_h_ago: 6480,
    },
    {
      id: 'pl_pro', name: 'Pro', price: 449, currency: 'RUB', duration_days: 30,
      limit: 1024 * 1024**3, devices: 5,
      state: 'active', visibility: 'public',
      features: { smart_routing: true, whitelist: true, p2p: true, all_regions: true, multi_protocol: true, priority_support: false },
      promo_codes: 5,
      created_h_ago: 6480,
    },
    {
      id: 'pl_proy', name: 'Pro Yearly', price: 4490, currency: 'RUB', duration_days: 365,
      limit: 1024 * 1024**3, devices: 5,
      state: 'active', visibility: 'public',
      features: { smart_routing: true, whitelist: true, p2p: true, all_regions: true, multi_protocol: true, priority_support: false },
      promo_codes: 3,
      created_h_ago: 4320,
    },
    {
      id: 'pl_team', name: 'Team', price: 2490, currency: 'RUB', duration_days: 30,
      limit: 5 * 1024 * 1024**3, devices: 25,
      state: 'active', visibility: 'public',
      features: { smart_routing: true, whitelist: true, p2p: true, all_regions: true, multi_protocol: true, priority_support: true },
      promo_codes: 1,
      created_h_ago: 2160,
    },
    {
      id: 'pl_promo7', name: 'Promo 7d', price: 49, currency: 'RUB', duration_days: 7,
      limit: 50 * 1024**3, devices: 2,
      state: 'promo', visibility: 'hidden',
      features: { smart_routing: true, whitelist: false, p2p: false, all_regions: false, multi_protocol: false, priority_support: false },
      promo_codes: 1,
      created_h_ago: 168,
      promo_until_h: 240,
    },
    {
      id: 'pl_legacy_pro', name: 'Pro 2023', price: 299, currency: 'RUB', duration_days: 30,
      limit: 500 * 1024**3, devices: 4,
      state: 'active', visibility: 'hidden',
      features: { smart_routing: false, whitelist: true, p2p: true, all_regions: false, multi_protocol: false, priority_support: false },
      promo_codes: 0,
      created_h_ago: 17520,
      legacy_note: 'Старая линейка, продаётся только текущим клиентам',
    },
  ];

  const SUBS = [
    { id: 'sub_a4f928c1', user: '@kate_shirokova', tg: 184729301, plan: 'pl_pro', used: 920 * 1024**3, devices: 5, expires_h: 6, active: true, hwid: true },
    { id: 'sub_b71d33ef', user: '@d_petrov', tg: 240118822, plan: 'pl_team', used: 4.2 * 1024 * 1024**3, devices: 22, expires_h: 18, active: true, hwid: true },
    { id: 'sub_c8e0a512', user: '@maria_l', tg: 519302014, plan: 'pl_basic', used: 102 * 1024**3, devices: 3, expires_h: 22, active: true, hwid: false },
    { id: 'sub_d11f4b09', user: '@oleg_k', tg: 622019883, plan: 'pl_proy', used: 480 * 1024**3, devices: 4, expires_h: 72, active: true, hwid: true },
    { id: 'sub_e3a9c0d4', user: '@anna_s', tg: 718203991, plan: 'pl_pro', used: 640 * 1024**3, devices: 3, expires_h: 96, active: true, hwid: true },
    { id: 'sub_f7b21e88', user: '@igor_t', tg: 802419772, plan: 'pl_basic', used: 38 * 1024**3, devices: 2, expires_h: 120, active: true, hwid: false },
    { id: 'sub_087dc41a', user: '@lena_m', tg: 901827314, plan: 'pl_pro', used: 320 * 1024**3, devices: 2, expires_h: 144, active: true, hwid: true },
    { id: 'sub_19c4e708', user: '@sergey_v', tg: 1027183921, plan: 'pl_team', used: 1.8 * 1024 * 1024**3, devices: 14, expires_h: 240, active: true, hwid: true },
    { id: 'sub_2af6b201', user: '@pavel_r', tg: 1142039128, plan: 'pl_pro', used: 220 * 1024**3, devices: 3, expires_h: 360, active: true, hwid: true },
    { id: 'sub_3c8f9d52', user: '@ekaterina_b', tg: 1208377412, plan: 'pl_proy', used: 510 * 1024**3, devices: 5, expires_h: 540, active: true, hwid: true },
    { id: 'sub_4d09e6b7', user: '@andrey_p', tg: 1349812003, plan: 'pl_basic', used: 56 * 1024**3, devices: 1, expires_h: 720, active: true, hwid: false },
    { id: 'sub_5e1a73c8', user: '@natasha_k', tg: 1487192013, plan: 'pl_free', used: 4.7 * 1024**3, devices: 1, expires_h: null, active: true, hwid: false },
    { id: 'sub_61f3a9e0', user: '@dmitry_s', tg: 1529018822, plan: 'pl_pro', used: 30 * 1024**3, devices: 0, expires_h: 96, active: true, hwid: true },
    { id: 'sub_72b8c4d3', user: '@old_user', tg: 1600281932, plan: 'pl_basic', used: 22 * 1024**3, devices: 0, expires_h: -120, active: false, hwid: false },
    { id: 'sub_8390e21f', user: '@former_client', tg: 1718823902, plan: 'pl_pro', used: 880 * 1024**3, devices: 0, expires_h: -480, active: false, hwid: true },
  ];

  // helper — generate sparkline points
  function spark(seed, len = 24, base = 50, vol = 25) {
    let x = seed;
    const out = [];
    for (let i = 0; i < len; i++) {
      x = (x * 9301 + 49297) % 233280;
      out.push(base + ((x / 233280) - 0.5) * vol * 2);
    }
    return out;
  }

  // ── Users: derived from SUBS (one user can have N subs) ──
  // Group all SUBS by tg, then add a few users with no subs and a few blocked.
  const _subsByTg = SUBS.reduce((acc, s) => { (acc[s.tg] = acc[s.tg] || []).push(s.id); return acc; }, {});
  const USERS = [
    // Each user inherits username + tg from SUBS
    ...Object.entries(_subsByTg).map(([tg, subIds], i) => {
      const firstSub = SUBS.find(s => String(s.tg) === tg);
      const blocked = !firstSub.active && Math.random() < 0;  // keep determinism
      return {
        id: `usr_${tg}`,
        username: firstSub.user.replace('@', ''),
        tg: Number(tg),
        balance: [0, 50, 230, 1240, 0, 750, 95, 4200, 320, 1800, 60, 0, 0, 12, 80][i] ?? 100,
        created_h_ago: [720, 1440, 360, 4320, 2160, 168, 8760, 1080, 540, 2880, 720, 360, 96, 24*120, 24*200][i] ?? 720,
        last_seen_h_ago: [2, 1, 6, 12, 4, 24, 8, 1, 36, 4, 48, 168, 720, 24*30, 24*90][i] ?? 24,
        terms_accepted: true,
        sub_ids: subIds,
        blocked: !firstSub.active,  // 2 blocked from sub data
        ref_code: i < 5 ? `REF${(parseInt(tg) % 10000).toString(36).toUpperCase()}` : null,
      };
    }),
    // Lead users with no subscriptions
    { id: 'usr_lead_001', username: 'tanya_new', tg: 1820391847, balance: 0, created_h_ago: 4, last_seen_h_ago: 1, terms_accepted: true, sub_ids: [], blocked: false, ref_code: null },
    { id: 'usr_lead_002', username: 'curious_max', tg: 1928374651, balance: 100, created_h_ago: 18, last_seen_h_ago: 6, terms_accepted: true, sub_ids: [], blocked: false, ref_code: null },
    { id: 'usr_lead_003', username: 'silent_one', tg: 2018473628, balance: 0, created_h_ago: 168, last_seen_h_ago: 168, terms_accepted: false, sub_ids: [], blocked: false, ref_code: null },
  ];

  // ─── Probe data — shaped to match real API ───
  // Probe sources are external probe-agents that ping nodes/routes
  const PROBE_SOURCES = [
    { id: 'rt-1',       region: 'eu-central',  flag: '🇩🇪', last_seen_s: 4,    rate_pm: 124, success_24h: 0.991, p95_ms: 64,  status: 'ok'  },
    { id: 'ru-probe-1', region: 'eu-east',     flag: '🇷🇺', last_seen_s: 8,    rate_pm: 96,  success_24h: 0.984, p95_ms: 78,  status: 'ok'  },
    { id: 'ams-probe',  region: 'eu-west',     flag: '🇳🇱', last_seen_s: 11,   rate_pm: 142, success_24h: 0.978, p95_ms: 52,  status: 'ok'  },
    { id: 'sgp-probe',  region: 'ap-southeast',flag: '🇸🇬', last_seen_s: 6,    rate_pm: 68,  success_24h: 0.812, p95_ms: 168, status: 'warn'},
    { id: 'tyo-probe',  region: 'ap-northeast',flag: '🇯🇵', last_seen_s: 3,    rate_pm: 81,  success_24h: 0.989, p95_ms: 71,  status: 'ok'  },
    { id: 'nyc-probe',  region: 'us-east',     flag: '🇺🇸', last_seen_s: 9,    rate_pm: 117, success_24h: 0.992, p95_ms: 38,  status: 'ok'  },
    { id: 'lax-probe',  region: 'us-west',     flag: '🇺🇸', last_seen_s: 754,  rate_pm: 12,  success_24h: 0.604, p95_ms: 0,   status: 'bad' }, // orphaned
  ];

  // Probe targets — what should be pinged
  const TARGETS = [
    { route_id: 'rt_001', node_id: 'nd_c9e1d2', transport_kind: 'wireguard',  target_host: '10.42.7.11',  target_port: 51820, last_seen_s: 4,   last_status: 'ok'   },
    { route_id: 'rt_002', node_id: 'nd_3b7f10', transport_kind: 'wireguard',  target_host: '10.42.7.12',  target_port: 51820, last_seen_s: 6,   last_status: 'ok'   },
    { route_id: 'rt_003', node_id: 'nd_1e5b4a', transport_kind: 'wireguard',  target_host: '10.42.7.13',  target_port: 51820, last_seen_s: 8,   last_status: 'ok'   },
    { route_id: 'rt_004', node_id: 'nd_6b4d93', transport_kind: 'shadowsocks',target_host: '10.51.2.21',  target_port: 8388,  last_seen_s: 12,  last_status: 'ok'   },
    { route_id: 'rt_005', node_id: 'nd_4f1e88', transport_kind: 'shadowsocks',target_host: '10.62.1.31',  target_port: 8388,  last_seen_s: 7,   last_status: 'ok'   },
    { route_id: 'rt_006', node_id: 'nd_c9e1d2', transport_kind: 'wireguard',  target_host: '10.42.7.11',  target_port: 51820, last_seen_s: 9,   last_status: 'warn' },
    { route_id: 'rt_007', node_id: 'nd_3b7f10', transport_kind: 'wireguard',  target_host: '10.42.7.12',  target_port: 51820, last_seen_s: 5,   last_status: 'ok'   },
    { route_id: 'rt_008', node_id: 'nd_1e5b4a', transport_kind: 'wireguard',  target_host: '10.42.7.13',  target_port: 51820, last_seen_s: 10,  last_status: 'ok'   },
    { route_id: 'rt_009', node_id: 'nd_9e0c27', transport_kind: 'wireguard',  target_host: '10.71.4.41',  target_port: 51820, last_seen_s: 832, last_status: 'bad'  }, // orphan
    { route_id: 'rt_010', node_id: 'nd_6b4d93', transport_kind: 'shadowsocks',target_host: '10.51.2.21',  target_port: 8388,  last_seen_s: 4,   last_status: 'ok'   },
    { route_id: 'rt_011', node_id: 'nd_4f1e88', transport_kind: 'wireguard',  target_host: '10.62.1.31',  target_port: 51820, last_seen_s: 3,   last_status: 'ok'   },
    { route_id: 'rt_012', node_id: 'nd_d2c701', transport_kind: 'wireguard',  target_host: '10.62.1.32',  target_port: 51820, last_seen_s: 6,   last_status: 'ok'   },
    { route_id: 'rt_013', node_id: 'nd_a7f92b', transport_kind: 'shadowsocks',target_host: '10.81.3.51',  target_port: 8388,  last_seen_s: 11,  last_status: 'ok'   },
    { route_id: 'rt_014', node_id: 'nd_a7f92b', transport_kind: 'shadowsocks',target_host: '10.81.3.51',  target_port: 8388,  last_seen_s: 5,   last_status: 'ok'   },
    { route_id: 'rt_015', node_id: 'nd_4f1e88', transport_kind: 'wireguard',  target_host: '10.62.1.31',  target_port: 51820, last_seen_s: 14,  last_status: 'warn' },
    { route_id: 'rt_016', node_id: 'nd_d2c701', transport_kind: 'wireguard',  target_host: '10.62.1.32',  target_port: 51820, last_seen_s: 8,   last_status: 'ok'   },
  ];

  // Reports — recent probe signals
  // Generate ~140 events spanning the last 60min, biased so problem routes have failures
  const PROBE_REPORTS = (function () {
    const rng = (s) => { let x = s; return () => { x = (x * 1103515245 + 12345) & 0x7fffffff; return x / 0x7fffffff; }; };
    const r = rng(424242);
    const PROBLEM_ROUTES = { 'rt_009': 0.95, 'rt_006': 0.45, 'rt_015': 0.30, 'rt_004': 0.18 };
    const ERROR_PHASES = ['handshake', 'tcp_connect', 'tls', 'auth', 'tunnel_setup', 'icmp', 'dns'];
    const ERRORS = {
      handshake:    'wireguard handshake timeout after 5s',
      tcp_connect:  'connection refused',
      tls:          'tls: handshake failure: protocol version mismatch',
      auth:         'auth: invalid pre-shared key',
      tunnel_setup: 'tunnel setup failed: peer did not respond',
      icmp:         'icmp echo timed out',
      dns:          'dns lookup failed: NXDOMAIN',
    };
    const out = [];
    let id = 1000;
    for (let i = 0; i < 220; i++) {
      const ageS = Math.floor(r() * 3600);
      const t = TARGETS[Math.floor(r() * TARGETS.length)];
      const src = PROBE_SOURCES[Math.floor(r() * (PROBE_SOURCES.length - 1))]; // skip orphan source
      const failChance = (PROBLEM_ROUTES[t.route_id] || 0.02) + (src.id === 'sgp-probe' ? 0.20 : 0);
      const failed = r() < failChance;
      const kind = r() < 0.7 ? 'synthetic_vpn' : 'tcp_connect';
      const phase = failed ? ERROR_PHASES[Math.floor(r() * ERROR_PHASES.length)] : null;
      const lat = failed ? null : Math.round(20 + r() * (t.transport_kind === 'shadowsocks' ? 200 : 80));
      out.push({
        id: 'pr_' + (id++).toString(16),
        source: src.id,
        node_id: t.node_id,
        route_id: t.route_id,
        probe_kind: kind,
        is_reachable: !failed,
        latency_ms: lat,
        error: phase ? ERRORS[phase] : null,
        error_phase: phase,
        checked_at_s_ago: ageS,
      });
    }
    return out.sort((a, b) => a.checked_at_s_ago - b.checked_at_s_ago);
  })();

  // Auto-drain history (24h)
  const PROBE_DRAINS = [
    { id: 'dr_001', node_id: 'nd_9e0c27', node_name: 'sgp-backend-01', reason: 'route rt_009 blocked, 14 consecutive probe failures', triggered_by: 'auto-policy', s_ago: 1620 },
    { id: 'dr_002', node_id: 'nd_8c3021', node_name: 'lax-entry-01',   reason: 'p95 > 200ms for 8 minutes',                            triggered_by: 'auto-policy', s_ago: 5400 },
    { id: 'dr_003', node_id: 'nd_c9e1d2', node_name: 'ams-backend-01', reason: 'manual drain after operator review',                   triggered_by: 'operator k.shirokova', s_ago: 17280 },
  ];

  window.MOCK = { NODES, ROUTES, ISSUES, ACTIVITY, COMMANDS, PLANS, SUBS, USERS, PROBE_SOURCES, PROBE_TARGETS: TARGETS, PROBE_REPORTS, PROBE_DRAINS, spark };
})();
