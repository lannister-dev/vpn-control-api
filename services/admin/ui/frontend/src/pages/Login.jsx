import { useEffect, useRef, useState } from "react";
import { api } from "../api/client.js";
import { Icon } from "../components/Icon.jsx";
import "./Login.css";

export function LoginPage({ theme, onToggleTheme, onSuccess }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [remember, setRemember] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [lastSync, setLastSync] = useState("2с");
  const userRef = useRef(null);
  const passRef = useRef(null);

  useEffect(() => { userRef.current?.focus(); }, []);

  useEffect(() => {
    const t0 = Date.now();
    const iv = setInterval(() => {
      const s = Math.floor((Date.now() - t0) / 1000) % 60;
      setLastSync(s < 5 ? `${s + 1}с` : `${s}с`);
    }, 1000);
    return () => clearInterval(iv);
  }, []);

  const canSubmit = username.trim().length > 0 && password.length > 0 && !loading;

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!canSubmit) return;
    setError(null);
    setLoading(true);
    try {
      await api.post("/auth/admin/login/password", { username: username.trim(), password });
      setSuccess(true);
      setTimeout(() => { onSuccess?.(); }, 700);
    } catch (err) {
      setLoading(false);
      if (err.status === 401) setError("Неверный логин или пароль");
      else if (err.status === 429) setError("Слишком много попыток. Попробуйте позже.");
      else setError(err.message || "Ошибка входа");
      passRef.current?.select();
    }
  };

  const telegramLogin = () => {
    window.location.href = "/api/v1/auth/admin/login/telegram/start";
  };

  return (
    <div className="login-root" data-theme={theme}>
      <div className="login-bg" aria-hidden="true">
        <div className="login-bg-grid" />
        <div className="login-bg-spotlight" />
        <div className="login-bg-vignette" />
      </div>

      <div className="login-topbar">
        <a className="login-topbar-link" href="#" onClick={(e) => e.preventDefault()}>
          <Icon name="activity" size={12} />
          <span>Status</span>
        </a>
        <a className="login-topbar-link" href="#" onClick={(e) => e.preventDefault()}>
          <Icon name="help" size={12} />
          <span>Документация</span>
        </a>
        <button
          className="btn btn-ghost btn-icon"
          onClick={onToggleTheme}
          title="Переключить тему"
          aria-label="Переключить тему"
        >
          <Icon name={theme === "dark" ? "sun" : "moon"} size={14} />
        </button>
      </div>

      <div className="login-footer">
        <div className="login-footer-mark">
          <div className="login-mark-sq" />
          <span>Control Panel</span>
        </div>
        <div className="login-footer-meta mono">v2.14.0 · © 2026</div>
      </div>

      <div className="login-footer-right">
        <a href="#" onClick={(e) => e.preventDefault()}>Terms</a>
        <span className="sep">·</span>
        <a href="#" onClick={(e) => e.preventDefault()}>Privacy</a>
        <span className="sep">·</span>
        <a href="#" onClick={(e) => e.preventDefault()}>Security</a>
      </div>

      <main className="login-stage">
        <div className="login-card">
          <div className="login-card-head">
            <div className="login-brand">
              <div className="login-brand-logo">C</div>
              <div className="login-brand-text">
                <div className="login-brand-name">Control Panel</div>
                <div className="login-brand-meta">
                  <span className="env-pill"><span className="status-dot ok pulse" /> PROD</span>
                  <span className="login-brand-host mono">admin.internal</span>
                </div>
              </div>
            </div>
          </div>

          <div className="login-title-block">
            <h1 className="login-title">Вход в панель</h1>
            <p className="login-subtitle">Используйте корпоративные учётные данные администратора.</p>
          </div>

          {success ? (
            <SuccessState />
          ) : (
            <form className="login-form" onSubmit={submit} noValidate>
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

              <label className="login-field">
                <div className="login-field-label-row">
                  <span className="login-field-label">Пароль</span>
                  <a href="#" className="login-link-subtle" tabIndex={-1} onClick={(e) => e.preventDefault()}>Забыли?</a>
                </div>
                <div className="login-input-wrap">
                  <Icon name="lock" size={14} className="login-input-icon" />
                  <input
                    ref={passRef}
                    type={show ? "text" : "password"}
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
                    onClick={() => setShow((s) => !s)}
                    tabIndex={-1}
                    aria-label={show ? "Скрыть пароль" : "Показать пароль"}
                    title={show ? "Скрыть пароль" : "Показать пароль"}
                  >
                    <Icon name="eye" size={13} style={{ opacity: show ? 1 : 0.55 }} />
                  </button>
                </div>
              </label>

              {error && (
                <div className="form-error" role="alert">
                  <Icon name="alert-circle" size={13} />
                  <span>{error}</span>
                </div>
              )}

              <div className="login-row-between">
                <label className="login-check">
                  <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
                  <span className="login-check-box" aria-hidden="true">
                    {remember && <Icon name="check" size={10} strokeWidth={3} />}
                  </span>
                  <span>Запомнить на 12 часов</span>
                </label>
              </div>

              <button type="submit" className="btn btn-primary login-submit" disabled={!canSubmit}>
                {loading ? (
                  <>
                    <span className="login-spin" />
                    <span>Проверка…</span>
                  </>
                ) : (
                  <>
                    <span>Войти</span>
                    <Icon name="arrow-right" size={14} />
                  </>
                )}
              </button>

              <div className="login-divider"><span>или</span></div>

              <button type="button" className="btn login-telegram" onClick={telegramLogin} disabled={loading}>
                <TelegramGlyph />
                <span>Войти через Telegram</span>
              </button>

              <div className="login-status">
                <span className="status-dot ok" />
                <span>Все системы в норме</span>
                <span className="login-status-sep">·</span>
                <span className="mono">sync {lastSync} назад</span>
              </div>
            </form>
          )}
        </div>

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
      <div className="login-success-sub mono">Перенаправление…</div>
      <div className="login-success-bar"><div className="login-success-bar-fill" /></div>
    </div>
  );
}

function TelegramGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M22 3L2 10.5l6.5 2.5L18 6.5l-7 8v5l3.5-3.5L20 21z" />
    </svg>
  );
}
