import { state, refs, $ } from '../state.js';
import { esc, chip, shortId, nodeNameById } from '../utils.js';
import { req, runAction } from '../api.js';
import { notify, confirmAction } from '../ui.js';

let _refreshAll = () => {};
export function setCallbacks(refreshAll) { _refreshAll = refreshAll; }

export function bindOpsEvents() {
  refs.formMigrate.addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = new FormData(refs.formMigrate);
    const payload = { source_backend_id: String(d.get("source_backend_id") || "").trim(), last_migration_reason: String(d.get("last_migration_reason") || "admin_manual").trim() || "admin_manual" };
    const t = String(d.get("target_backend_id") || "").trim(); if (t) payload.target_backend_id = t;
    const srcName = nodeNameById(payload.source_backend_id) || shortId(payload.source_backend_id);
    const ok = await confirmAction("\u041C\u0438\u0433\u0440\u0430\u0446\u0438\u044F \u043F\u043B\u0435\u0439\u0441\u043C\u0435\u043D\u0442\u043E\u0432", `\u041C\u0438\u0433\u0440\u0438\u0440\u043E\u0432\u0430\u0442\u044C \u0432\u0441\u0435 \u043F\u043B\u0435\u0439\u0441\u043C\u0435\u043D\u0442\u044B \u0441 \u043D\u043E\u0434\u044B "${srcName}"?`, "btn-warn"); if (!ok) return;
    runAction("Placement migration", () => req("/api/v1/admin/migrate-backend", { method: "POST", body: payload })).then(() => _refreshAll()).catch(() => {});
  });

  refs.formProbeAuto.addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = new FormData(refs.formProbeAuto);
    const payload = { source: String(d.get("source") || "").trim() || null, require_recent_failure: true, max_probe_age_sec: 600, min_consecutive_failures: 2, include_already_draining: false, dry_run: d.get("dry_run") === "on", max_nodes: Number(d.get("max_nodes") || 20), last_migration_reason: String(d.get("last_migration_reason") || "probe_auto_failure").trim() || "probe_auto_failure" };
    const t = String(d.get("target_backend_id") || "").trim(); if (t) payload.target_backend_id = t;
    const ok = await confirmAction("Probe auto-\u043F\u043E\u043B\u0438\u0442\u0438\u043A\u0430", `\u041F\u0440\u0438\u043C\u0435\u043D\u0438\u0442\u044C \u0430\u0432\u0442\u043E\u043C\u0430\u0442\u0438\u0447\u0435\u0441\u043A\u0443\u044E drain+migrate \u043F\u043E\u043B\u0438\u0442\u0438\u043A\u0443?${payload.dry_run ? " (dry run)" : " \u26A0 \u0411\u041E\u0415\u0412\u041E\u0419 \u0420\u0415\u0416\u0418\u041C"}`, payload.dry_run ? "btn-warn" : "btn-danger"); if (!ok) return;
    runAction("Probe auto policy", () => req("/api/v1/probe/admin/auto-drain-migrate-backends", { method: "POST", body: payload })).then((result) => {
      if (result && result.items) {
        const resEl = $("probe-auto-result");
        resEl.innerHTML = `<div class="card" style="font-size:12px">${chip("info", "processed: " + result.processed)} ${chip("ok", "migrated: " + result.migrated)} ${chip("warn", "skipped: " + result.skipped)}${result.dry_run ? " " + chip("warn", "dry run") : ""}<div class="stack" style="margin-top:6px">${result.items.map((it) => {
          const nName = nodeNameById(it.source_backend_id) || shortId(it.source_backend_id);
          const actionCls = it.action === "migrated" ? "ok" : (it.action === "would_migrate" ? "warn" : "info");
          return `<div>${esc(nName)} ${chip(actionCls, it.action)}${it.detail ? ` <span class="muted">${esc(it.detail)}</span>` : ""}${it.migrated_count ? ` (${it.migrated_count} placements)` : ""}</div>`;
        }).join("")}</div></div>`;
      }
      _refreshAll();
    }).catch(() => {});
  });

  refs.formRouteHealth.addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = new FormData(refs.formRouteHealth);
    const payload = { route_id: String(d.get("route_id") || "").trim(), action: String(d.get("action") || "set_healthy"), cooldown_hours: Number(d.get("cooldown_hours") || 6) };
    if (payload.action === "block") { const ok = await confirmAction("\u0411\u043B\u043E\u043A\u0438\u0440\u043E\u0432\u043A\u0430 \u043C\u0430\u0440\u0448\u0440\u0443\u0442\u0430", `\u0417\u0430\u0431\u043B\u043E\u043A\u0438\u0440\u043E\u0432\u0430\u0442\u044C \u043C\u0430\u0440\u0448\u0440\u0443\u0442 ${shortId(payload.route_id)}...?`); if (!ok) return; }
    runAction("Route health update", () => req("/api/v1/admin/set-route-health", { method: "POST", body: payload })).then(() => _refreshAll()).catch(() => {});
  });

  refs.formProbeManual.addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = new FormData(refs.formProbeManual);
    const payload = { source_backend_id: String(d.get("source_backend_id") || "").trim(), require_recent_failure: true, max_probe_age_sec: 600, min_consecutive_failures: 1, source: String(d.get("source") || "").trim() || null, last_migration_reason: "probe_failure" };
    const t = String(d.get("target_backend_id") || "").trim(); if (t) payload.target_backend_id = t;
    const srcName = nodeNameById(payload.source_backend_id) || shortId(payload.source_backend_id);
    const ok = await confirmAction("Drain \u0438 \u043C\u0438\u0433\u0440\u0430\u0446\u0438\u044F", `Drain \u0438 migrate \u043D\u043E\u0434\u044B "${srcName}"?`); if (!ok) return;
    runAction("Probe manual drain+migrate", () => req("/api/v1/probe/admin/drain-and-migrate-backend", { method: "POST", body: payload })).then(() => _refreshAll()).catch(() => {});
  });

  refs.btnWarmup.addEventListener("click", () => runAction("Advance warmup tick", () => req("/api/v1/routes/admin/advance-warmup", { method: "POST", body: {} })).then(() => _refreshAll()).catch(() => {}));
  refs.btnCleanupProbe.addEventListener("click", () => runAction("Cleanup probe signals", () => req("/api/v1/probe/admin/cleanup-old-signals", { method: "POST", body: {} })).then(() => _refreshAll()).catch(() => {}));
}
