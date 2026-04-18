import { state, refs, $ } from './state.js';
import { esc } from './utils.js';
import { copyToClipboard } from './api.js';

// Focus trap
let focusTrapStack = [];

export function trapFocus(modalEl) {
  if (!modalEl) return;
  const focusableSelector = 'a, button, input, select, textarea, [tabindex]:not([tabindex="-1"])';
  const focusableElements = Array.from(modalEl.querySelectorAll(focusableSelector)).filter(el => !el.hasAttribute('disabled'));
  if (focusableElements.length === 0) return;
  const firstElement = focusableElements[0];
  const lastElement = focusableElements[focusableElements.length - 1];
  focusTrapStack.push({ modal: modalEl, firstElement, lastElement, previousFocus: document.activeElement });
  firstElement.focus();
  const handleKeydown = (e) => {
    if (e.key === 'Tab') {
      if (e.shiftKey) {
        if (document.activeElement === firstElement) { e.preventDefault(); lastElement.focus(); }
      } else {
        if (document.activeElement === lastElement) { e.preventDefault(); firstElement.focus(); }
      }
    }
  };
  modalEl.addEventListener('keydown', handleKeydown);
  modalEl._trapKeydownHandler = handleKeydown;
}

export function releaseFocus() {
  const trap = focusTrapStack.pop();
  if (trap && trap.modal) {
    trap.modal.removeEventListener('keydown', trap.modal._trapKeydownHandler);
    delete trap.modal._trapKeydownHandler;
    if (trap.previousFocus && typeof trap.previousFocus.focus === 'function') {
      trap.previousFocus.focus();
    }
  }
}

// Enhanced notify
const toastQueue = [];
const MAX_TOASTS = 5;
export function notify(message, isError, duration) {
  const el = document.createElement("div");
  el.className = "toast" + (isError ? " error" : "");
  const dur = duration || (isError ? 6000 : 4500);
  el.innerHTML = `<span>${esc(message)}</span><div class="toast-progress"></div><button class="toast-close" aria-label="Закрыть уведомление">&times;</button>`;
  refs.toastContainer.appendChild(el);
  let timeoutId;
  let startTime = Date.now();
  let isPaused = false;
  let pauseTime = 0;
  const dismiss = () => { el.classList.remove("show"); setTimeout(() => { el.remove(); toastQueue.splice(toastQueue.indexOf(el), 1); }, 200); };
  const resume = () => { if (!isPaused) return; isPaused = false; startTime = Date.now() - pauseTime; const remaining = dur - pauseTime; timeoutId = setTimeout(dismiss, remaining); };
  const pause = () => { if (isPaused) return; isPaused = true; pauseTime = Date.now() - startTime; clearTimeout(timeoutId); };
  el.addEventListener("mouseenter", pause);
  el.addEventListener("mouseleave", resume);
  el.querySelector(".toast-close").addEventListener("click", dismiss);
  requestAnimationFrame(() => el.classList.add("show"));
  toastQueue.push(el);
  while (refs.toastContainer.children.length > MAX_TOASTS) refs.toastContainer.firstChild.remove();
  timeoutId = setTimeout(dismiss, dur);
}

export function confirmAction(title, body, btnClass) {
  return new Promise((resolve) => {
    refs.confirmModal.innerHTML = `<div class="modal-overlay"><div class="modal-box"><div class="modal-title">${esc(title)}</div><div class="modal-body">${body}</div><div class="modal-actions"><button class="btn btn-ghost" data-confirm="cancel">Отмена</button><button class="btn ${btnClass || "btn-danger"}" data-confirm="ok">Подтвердить</button></div></div></div>`;
    const modalBox = refs.confirmModal.querySelector(".modal-box");
    const cleanup = (result) => { releaseFocus(); refs.confirmModal.innerHTML = ""; resolve(result); };
    const handleEsc = (e) => { if (e.key === "Escape") { e.preventDefault(); cleanup(false); } };
    refs.confirmModal.querySelector('[data-confirm="cancel"]').addEventListener("click", () => cleanup(false));
    refs.confirmModal.querySelector('[data-confirm="ok"]').addEventListener("click", () => cleanup(true));
    refs.confirmModal.querySelector(".modal-overlay").addEventListener("click", (ev) => { if (ev.target === ev.currentTarget) cleanup(false); });
    refs.confirmModal.addEventListener("keydown", handleEsc);
    trapFocus(modalBox);
  });
}

export function pushLog(title, payload, isError) {
  state.logs.unshift({ at: new Date().toLocaleString(), title, payload, isError: !!isError });
  if (state.logs.length > 40) state.logs.length = 40;
  refs.actionLog.innerHTML = state.logs.length
    ? state.logs.map((i) => `<div class="log-item${i.isError ? " error" : ""}"><div><strong>${esc(i.title)}</strong></div><div class="muted">${esc(i.at)}</div><div class="mono">${esc(typeof i.payload === "string" ? i.payload : JSON.stringify(i.payload))}</div></div>`).join("")
    : `<div class="empty">Операций пока не было.</div>`;
}

export function announce(text) {
  const announcer = $("aria-announce");
  if (announcer) { announcer.textContent = text; setTimeout(() => { announcer.textContent = ""; }, 3000); }
}

export function showSkeleton(containerId, rowCount = 5) {
  const container = $(containerId);
  if (!container || container.children.length > 0) return;
  const skeletons = Array.from({ length: rowCount }, () => {
    const cols = Math.floor(Math.random() * 3) + 3;
    return `<tr><td colspan="${cols}"><div class="skeleton-row">${Array.from({ length: cols }).map(() => `<div></div>`).join("")}</div></td></tr>`;
  }).join("");
  container.innerHTML = skeletons;
}

export function hideSkeleton(containerId) { const container = $(containerId); if (container) container.innerHTML = ""; }

export function smoothUpdate(containerId, html) {
  const el = $(containerId);
  if (!el) return;
  el.classList.remove("refreshing");
  el.innerHTML = html;
  void el.offsetWidth;
  el.style.opacity = "0";
  requestAnimationFrame(() => { el.style.opacity = ""; });
}

export function markRefreshing(containerId) {
  const el = $(containerId);
  if (el && el.children.length > 0) el.classList.add("refreshing");
}

export function renderEmptyState(container, { icon = "\uD83D\uDCED", title = "\u041F\u0443\u0441\u0442\u043E", hint = "", actionLabel = null, onAction = null } = {}) {
  const actionBtn = actionLabel && onAction ? `<div class="empty-state-action"><button class="btn btn-primary">${esc(actionLabel)}</button></div>` : "";
  container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">${icon}</div><div class="empty-state-title">${esc(title)}</div>${hint ? `<div class="empty-state-hint">${esc(hint)}</div>` : ""}${actionBtn}</div>`;
  if (actionLabel && onAction) { container.querySelector(".btn").addEventListener("click", onAction); }
}

export function initTooltips(rootEl = document) {
  const tooltipElements = rootEl.querySelectorAll("[data-tooltip]");
  tooltipElements.forEach(el => {
    const text = el.getAttribute("data-tooltip");
    const pos = el.getAttribute("data-tooltip-pos") || "top";
    let tooltip = null;
    let timeoutId = null;
    const show = () => {
      clearTimeout(timeoutId);
      const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      timeoutId = setTimeout(() => {
        tooltip = document.createElement("div");
        tooltip.className = `tooltip ${pos}`;
        tooltip.textContent = text;
        document.body.appendChild(tooltip);
        const rect = el.getBoundingClientRect();
        const ttRect = tooltip.getBoundingClientRect();
        let top, left;
        const offset = 10;
        switch (pos) {
          case "top": top = rect.top - ttRect.height - offset; left = rect.left + (rect.width - ttRect.width) / 2; break;
          case "bottom": top = rect.bottom + offset; left = rect.left + (rect.width - ttRect.width) / 2; break;
          case "left": top = rect.top + (rect.height - ttRect.height) / 2; left = rect.left - ttRect.width - offset; break;
          case "right": top = rect.top + (rect.height - ttRect.height) / 2; left = rect.right + offset; break;
        }
        tooltip.style.top = top + "px";
        tooltip.style.left = left + "px";
        requestAnimationFrame(() => tooltip.classList.add("visible"));
      }, prefersReduced ? 0 : 300);
    };
    const hide = () => {
      clearTimeout(timeoutId);
      if (tooltip) { tooltip.classList.remove("visible"); setTimeout(() => tooltip && tooltip.remove(), 150); tooltip = null; }
    };
    el.addEventListener("mouseenter", show);
    el.addEventListener("mouseleave", hide);
    el.addEventListener("focus", show);
    el.addEventListener("blur", hide);
  });
}

export function initCopyButtons(rootEl = document) {
  const copyBtns = rootEl.querySelectorAll(".copy-value, .uuid");
  copyBtns.forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const val = btn.getAttribute("data-copy") || btn.textContent;
      await copyToClipboard(val);
    });
  });
}

export function trackFormDirty(formEl) { if (!formEl) return; formEl.setAttribute("data-dirty", "false"); formEl.addEventListener("input", () => formEl.setAttribute("data-dirty", "true")); formEl.addEventListener("change", () => formEl.setAttribute("data-dirty", "true")); }
export function isFormDirty(formEl) { return formEl && formEl.getAttribute("data-dirty") === "true"; }
export function resetFormDirty(formEl) { if (formEl) formEl.setAttribute("data-dirty", "false"); }

export function renderPagination(container, total, limit, offset, onPage) {
  const pages = Math.ceil(total / limit); const current = Math.floor(offset / limit);
  if (pages <= 1) { container.innerHTML = ""; return; }
  let html = "";
  if (current > 0) html += `<button class="btn-mini" data-page="${current - 1}">&laquo;</button>`;
  const start = Math.max(0, current - 3); const end = Math.min(pages, current + 4);
  for (let i = start; i < end; i++) html += `<button class="btn-mini${i === current ? " ok" : ""}" data-page="${i}">${i + 1}</button>`;
  if (current < pages - 1) html += `<button class="btn-mini" data-page="${current + 1}">&raquo;</button>`;
  html += `<span class="muted" style="font-size:11px;margin-left:8px">${total} записей</span>`;
  container.innerHTML = html;
  container.querySelectorAll("[data-page]").forEach((btn) => { btn.addEventListener("click", () => onPage(Number(btn.dataset.page))); });
}

export function showModal(el) {
  if (!el) return;
  el.style.display = "flex";
  const modalBox = el.querySelector(".modal-box");
  if (modalBox) trapFocus(modalBox);
  const handleEsc = (e) => { if (e.key === "Escape") { e.preventDefault(); hideModal(el); } };
  el.addEventListener("keydown", handleEsc);
  el._escHandler = handleEsc;
}

export function hideModal(el) {
  if (!el) return;
  el.style.display = "none";
  if (el._escHandler) { el.removeEventListener("keydown", el._escHandler); delete el._escHandler; }
  releaseFocus();
}

export function openShortcutsModal() {
  const shortcuts = [
    { keys: "Esc", desc: "Закрыть модаль" },
    { keys: "Cmd/Ctrl+K", desc: "Открыть палетру команд" },
    { keys: "?", desc: "Показать горячие клавиши" },
    { keys: "Tab", desc: "Переход по полям" },
    { keys: "Shift+Tab", desc: "Переход назад" },
  ];
  confirmAction("Горячие клавиши", `<div class="shortcuts-modal-content"><div class="shortcuts-group"><div class="shortcuts-group-title">Общее</div>${shortcuts.map(s => `<div class="shortcuts-item"><span class="shortcuts-desc">${esc(s.desc)}</span><span class="shortcuts-key">${esc(s.keys)}</span></div>`).join("")}</div></div>`, "btn-ghost");
}

// Command palette - items will be registered by app.js via setCommandItems
let commandItems = [];
let commandPaletteOpen = false;

export function setCommandItems(items) { commandItems = items; }

export function fuzzyMatch(query, text) {
  const q = query.toLowerCase(); const t = text.toLowerCase();
  let qi = 0, ti = 0, score = 0;
  while (qi < q.length && ti < t.length) { if (q[qi] === t[ti]) { score += 1; qi++; } ti++; }
  return qi === q.length ? score : 0;
}

export function initCommandPalette() {
  const commandPalette = $("command-palette");
  const commandInput = $("command-input");
  const commandList = $("command-list");

  function renderCommandList(query) {
    const filtered = query ? commandItems.filter(item => fuzzyMatch(query, item.label) > 0).sort((a, b) => fuzzyMatch(query, b.label) - fuzzyMatch(query, a.label)) : commandItems;
    const grouped = {};
    filtered.forEach(item => { if (!grouped[item.section]) grouped[item.section] = []; grouped[item.section].push(item); });
    commandList.innerHTML = Object.entries(grouped).map(([section, items]) =>
      `<div class="command-palette-group"><div class="command-palette-group-title">${esc(section)}</div>${items.map((item, idx) => `<div class="command-palette-item" data-idx="${idx}" data-section="${esc(section)}"><div class="command-palette-item-icon">${item.icon}</div><div class="command-palette-item-label">${esc(item.label)}</div></div>`).join("")}</div>`
    ).join("");
  }

  function openCP() { commandPaletteOpen = true; commandInput.value = ""; commandPalette.classList.add("active"); commandInput.focus(); renderCommandList(""); }
  function closeCP() { commandPaletteOpen = false; commandPalette.classList.remove("active"); commandInput.value = ""; }

  commandInput.addEventListener("input", (e) => renderCommandList(e.target.value));
  commandInput.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { closeCP(); }
    if (e.key === "Enter") {
      const selected = commandList.querySelector(".command-palette-item.selected");
      if (selected) {
        const idx = Array.from(commandList.querySelectorAll(".command-palette-item")).indexOf(selected);
        const item = commandItems.find((_, i) => i === idx);
        if (item && item.action) { item.action(); closeCP(); }
      }
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      const items = Array.from(commandList.querySelectorAll(".command-palette-item"));
      const selected = commandList.querySelector(".command-palette-item.selected");
      const idx = selected ? items.indexOf(selected) : -1;
      if (items[idx + 1]) { items[idx + 1].classList.add("selected"); selected?.classList.remove("selected"); }
      else if (items[0]) { items[0].classList.add("selected"); selected?.classList.remove("selected"); }
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      const items = Array.from(commandList.querySelectorAll(".command-palette-item"));
      const selected = commandList.querySelector(".command-palette-item.selected");
      const idx = selected ? items.indexOf(selected) : 0;
      if (items[idx - 1]) { items[idx - 1].classList.add("selected"); selected?.classList.remove("selected"); }
      else if (items[items.length - 1]) { items[items.length - 1].classList.add("selected"); selected?.classList.remove("selected"); }
    }
  });
  commandList.addEventListener("click", (e) => {
    const item = e.target.closest(".command-palette-item");
    if (item) {
      const idx = Array.from(commandList.querySelectorAll(".command-palette-item")).indexOf(item);
      const cmdItem = commandItems.find((_, i) => i === idx);
      if (cmdItem && cmdItem.action) { cmdItem.action(); closeCP(); }
    }
  });
  commandPalette.addEventListener("click", (e) => { if (e.target === commandPalette) closeCP(); });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "k") { e.preventDefault(); commandPaletteOpen ? closeCP() : openCP(); }
    if (e.key === "?" && !e.ctrlKey && !e.metaKey) {
      const active = document.activeElement;
      if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA" || active.tagName === "SELECT")) return;
      e.preventDefault(); openShortcutsModal();
    }
  });
}
