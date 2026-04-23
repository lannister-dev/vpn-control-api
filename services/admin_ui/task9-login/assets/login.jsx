// Task 9 — Login page
// Single-variant, production-ready. Monochrome dark grid background.
// Matches existing design system: OKLCH tokens, Inter/JetBrains Mono, .btn .input .pill,
// Topbar-style env-pill, workspace-logo crest.

const { useState, useEffect, useRef } = React;

function LoginPage({ theme, onToggleTheme }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [remember, setRemember] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [lastSync, setLastSync] = useState('2с');
  const userRef = useRef(null);
  const passRef = useRef(null);

  useEffect(() => { userRef.current?.focus(); }, []);

  // Simulated "все системы в норме" ticker — reinforces live-admin feeling
  useEffect(() => {
    const t0 = Date.now();
    const iv = setInterval(() => {
      const s = Math.floor((Date.now() - t0) / 1000) % 60;
      setLastSync(s < 5 ? `${s + 1}с` : `${s}с`);
    }, 1000);
    return () => clearInterval(iv);
  }, []);

  const canSubmit = username.trim().length > 0 && password.length > 0 && !loading;

  const submit = (e) => {
    e?.preventDefault?.();
    if (!canSubmit) return;
    setError(null);
    setLoading(true);
    // Demo behaviour: specific pair fails, anything else succeeds
    setTimeout(() => {
      if (username.trim() === 'admin' && password === 'wrong') {
        setLoading(false);
        setError('Неверный логин или пароль');
        // refocus password for quick retry
        passRef.current?.select();
      } else {
        setLoading(false);
        setSuccess(true);
      }
    }, 900);
  };

  return (
    <div className="login-root" data-theme={theme}>
      {/* Background: subtle monochrome grid + vignette + accent spotlight */}
      <div className="login-bg" aria-hidden="true">
        <div className="login-bg-grid"></div>
        <div className="login-bg-spotlight"></div>
        <div className="login-bg-vignette"></div>
      </div>

      {/* Top-right controls */}
      <div className="login-topbar">
        <a className="login-topbar-link" href="#">
          <Icon name="activity" size={12} />
          <span>Status</span>
        </a>
        <a className="login-topbar-link" href="#">
          <Icon name="help" size={12} />
          <span>Документация</span>
        </a>
        <button
          className="btn btn-ghost btn-icon"
          onClick={onToggleTheme}
          title="Переключить тему"
          aria-label="Переключить тему"
        >
          <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={14} />
        </button>
      </div>

      {/* Bottom-left brand footer */}
      <div className="login-footer">
        <div className="login-footer-mark">
          <div className="login-mark-sq"></div>
          <span>Control Panel</span>
        </div>
        <div className="login-footer-meta mono">
          v2.14.0 · © 2026
        </div>
      </div>

      {/* Bottom-right legalish links */}
      <div className="login-footer-right">
        <a href="#">Terms</a>
        <span className="sep">·</span>
        <a href="#">Privacy</a>
        <span className="sep">·</span>
        <a href="#">Security</a>
      </div>

      {/* Central card */}
      <main className="login-stage">
        <div className="login-card">
          {/* Header — workspace crest + env-pill */}
          <div className="login-card-head">
            <div className="login-brand">
              <div className="login-brand-logo">C</div>
              <div className="login-brand-text">
                <div className="login-brand-name">Control Panel</div>
                <div className="login-brand-meta">
                  <span className="env-pill"><span className="status-dot ok pulse"></span> PROD</span>
                  <span className="login-brand-host mono">admin.internal</span>
                </div>
              </div>
            </div>
          </div>

          {/* Title */}
          <div className="login-title-block">
            <h1 className="login-title">Вход в панель</h1>
            <p className="login-subtitle">
              Используйте корпоративные учётные данные администратора.
            </p>
          </div>

          {success ? (
            <SuccessState />
          ) : (
            <form className="login-form" onSubmit={submit} noValidate>
              {/* Username */}
              <label className="login-field">
                <span className="login-field-label">Логин</span>
                <div className="login-input-wrap">
                  <Icon name="users" size={14} className="login-input-icon" />
                  <input
                    ref={userRef}
                    type="text"
                    className="input login-input"
                    placeholder="k.shirokova"
                    autoComplete="username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    disabled={loading}
                  />
                </div>
              </label>

              {/* Password */}
              <label className="login-field">
                <div className="login-field-label-row">
                  <span className="login-field-label">Пароль</span>
                  <a href="#" className="login-link-subtle" tabIndex={-1}>Забыли?</a>
                </div>
                <div className="login-input-wrap">
                  <Icon name="lock" size={14} className="login-input-icon" />
                  <input
                    ref={passRef}
                    type={show ? 'text' : 'password'}
                    className="input login-input"
                    placeholder="••••••••••••"
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    disabled={loading}
                  />
                  <button
                    type="button"
                    className="login-input-eye"
                    onClick={() => setShow(s => !s)}
                    tabIndex={-1}
                    aria-label={show ? 'Скрыть пароль' : 'Показать пароль'}
                    title={show ? 'Скрыть пароль' : 'Показать пароль'}
                  >
                    <Icon name={show ? 'eye' : 'eye'} size={13} style={{opacity: show ? 1 : 0.55}} />
                  </button>
                </div>
              </label>

              {/* Inline error */}
              {error && (
                <div className="form-error" role="alert">
                  <Icon name="alert-circle" size={13} />
                  <span>{error}</span>
                </div>
              )}

              {/* Remember + trust hint */}
              <div className="login-row-between">
                <label className="login-check">
                  <input
                    type="checkbox"
                    checked={remember}
                    onChange={(e) => setRemember(e.target.checked)}
                  />
                  <span className="login-check-box" aria-hidden="true">
                    {remember && <Icon name="check" size={10} strokeWidth={3} />}
                  </span>
                  <span>Запомнить на 12 часов</span>
                </label>
              </div>

              {/* Submit */}
              <button
                type="submit"
                className="btn btn-primary login-submit"
                disabled={!canSubmit}
              >
                {loading ? (
                  <>
                    <span className="login-spin"></span>
                    <span>Проверка…</span>
                  </>
                ) : (
                  <>
                    <span>Войти</span>
                    <Icon name="arrow-right" size={14} />
                  </>
                )}
              </button>

              {/* Divider */}
              <div className="login-divider"><span>или</span></div>

              {/* Telegram login */}
              <button
                type="button"
                className="btn login-telegram"
                onClick={() => {
                  setLoading(true);
                  setError(null);
                  setTimeout(() => { setLoading(false); setSuccess(true); }, 900);
                }}
                disabled={loading}
              >
                <TelegramGlyph />
                <span>Войти через Telegram</span>
              </button>

              {/* System status ticker */}
              <div className="login-status">
                <span className="status-dot ok"></span>
                <span>Все системы в норме</span>
                <span className="login-status-sep">·</span>
                <span className="mono">sync {lastSync} назад</span>
              </div>
            </form>
          )}
        </div>

        {/* Below-card help */}
        <div className="login-card-below">
          <Icon name="shield-check" size={12} />
          <span>Доступ по SSO, логину или Telegram. Сессии логируются.</span>
        </div>
      </main>
    </div>
  );
}

function SuccessState() {
  return (
    <div className="login-success">
      <div className="login-success-icon">
        <Icon name="check" size={22} strokeWidth={2.5} />
      </div>
      <div className="login-success-title">Успешный вход</div>
      <div className="login-success-sub mono">Перенаправление в /overview…</div>
      <div className="login-success-bar"><div className="login-success-bar-fill"></div></div>
    </div>
  );
}

// Telegram paper-plane glyph — simple original SVG
function TelegramGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M22 3L2 10.5l6.5 2.5L18 6.5l-7 8v5l3.5-3.5L20 21z" />
    </svg>
  );
}

Object.assign(window, { LoginPage });
