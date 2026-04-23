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

  window.MOCK = { NODES, ROUTES, ISSUES, ACTIVITY, COMMANDS, spark };
})();
