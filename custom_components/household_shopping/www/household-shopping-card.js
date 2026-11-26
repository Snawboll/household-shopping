/*
 * Household Shopping card (§7.2 of docs/REQUIREMENTS.md).
 *
 * Plain web component, no build step and no external imports (NFR-01). It
 * subscribes to `household_shopping/subscribe` for a live snapshot and changes
 * things only through the integration's actions, so every rule lives in Python.
 *
 * Layout: #top (header, tabs) · #bar (add/search box, kept stable so typing
 * isn't interrupted) · #body (re-rendered on every update) · #foot (main
 * button) · #sheet (menus and dialogs) · #toast.
 */

const DOMAIN = "household_shopping";
const VERSION = "0.3.0";
const LONG_PRESS_MS = 450;

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const fmtDate = (iso) =>
  iso ? new Date(iso).toLocaleDateString("en-AU", { weekday: "short", day: "numeric", month: "short" }) : "";

const STYLE = `
  :host { display: block; }
  ha-card { overflow: hidden; }
  * { box-sizing: border-box; }
  button { font: inherit; color: inherit; cursor: pointer; border: none; background: none; }
  input, select, textarea {
    font: inherit; color: var(--primary-text-color); background: var(--secondary-background-color, #f5f5f5);
    border: 1px solid var(--divider-color); border-radius: 10px; padding: 10px 12px; min-height: 44px; width: 100%;
  }
  textarea { min-height: 140px; }
  .top { display: flex; align-items: center; gap: 8px; padding: 12px 16px 4px; }
  .title { font-size: 1.25em; font-weight: 600; flex: 1; min-width: 0; }
  .chip { font-size: .75em; padding: 3px 10px; border-radius: 999px; background: var(--secondary-background-color); color: var(--secondary-text-color); white-space: nowrap; }
  .chip.shopping { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .chip.planning { background: var(--warning-color, #f59e0b); color: #000; }
  .tabs { display: flex; gap: 4px; padding: 4px 16px 8px; }
  .tab { flex: 1; padding: 10px; border-radius: 10px; background: var(--secondary-background-color); font-weight: 500; min-height: 44px; }
  .tab.on { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .bar { display: flex; gap: 8px; padding: 0 16px 8px; }
  .bar:empty { display: none; }
  .bar input { flex: 1; }
  .bar select { width: auto; max-width: 40%; }
  .btn { min-height: 44px; padding: 0 16px; border-radius: 10px; background: var(--secondary-background-color); font-weight: 500; }
  .btn.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .btn.danger { color: var(--error-color, #db4437); }
  .btn { white-space: nowrap; }
  .btn.big { width: 100%; min-height: 52px; font-size: 1.05em; }
  .body { padding: 0 8px 8px; }
  .foot { padding: 8px 16px 16px; display: flex; gap: 8px; }
  .foot:empty { display: none; }
  .group { margin: 6px 0; }
  .ghead { display: flex; align-items: center; gap: 8px; padding: 10px 8px 6px; font-weight: 600; color: var(--secondary-text-color); font-size: .9em; text-transform: uppercase; letter-spacing: .03em; user-select: none; }
  .ghead .count { margin-left: auto; font-weight: 400; text-transform: none; }
  .ghead.click { cursor: pointer; }
  .row { display: flex; align-items: center; gap: 10px; padding: 6px 8px; min-height: 56px; border-radius: 12px; user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; }
  .row + .row { border-top: 1px solid var(--divider-color); border-radius: 0; }
  .row.click { cursor: pointer; }
  .pic { width: 40px; height: 40px; flex: none; border-radius: 8px; display: grid; place-items: center; font-size: 26px; overflow: hidden; background: var(--secondary-background-color); }
  .pic img { width: 100%; height: 100%; object-fit: cover; }
  .txt { flex: 1; min-width: 0; }
  .name { font-size: 1.05em; overflow-wrap: anywhere; }
  .note { font-size: .82em; color: var(--secondary-text-color); overflow-wrap: anywhere; }
  .row.got .name { text-decoration: line-through; opacity: .55; }
  .row.got .pic { opacity: .5; }
  .row.missing { background: color-mix(in srgb, var(--error-color, #db4437) 10%, transparent); }
  .row.missing .name::after { content: " · missing"; color: var(--error-color, #db4437); font-size: .8em; font-weight: 600; }
  .act { width: 48px; height: 48px; flex: none; border-radius: 50%; font-size: 22px; display: grid; place-items: center; border: 2px solid var(--divider-color); }
  .act.got.on { background: var(--success-color, #43a047); border-color: var(--success-color, #43a047); color: #fff; }
  .act.miss.on { background: var(--error-color, #db4437); border-color: var(--error-color, #db4437); color: #fff; }
  .tick { width: 30px; height: 30px; flex: none; border-radius: 8px; border: 2px solid var(--divider-color); display: grid; place-items: center; font-size: 18px; }
  .tick.on { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .progress { height: 6px; margin: 4px 16px 8px; background: var(--secondary-background-color); border-radius: 3px; overflow: hidden; display: flex; }
  .progress[hidden] { display: none; }
  .progress i { display: block; height: 100%; }
  .empty { text-align: center; color: var(--secondary-text-color); padding: 24px 16px; }
  .panel { margin: 8px; padding: 14px; border-radius: 12px; background: var(--secondary-background-color); }
  .panel h3 { margin: 0 0 8px; font-size: 1em; }
  .pills { display: flex; flex-wrap: wrap; gap: 6px; }
  .pill { padding: 6px 10px; border-radius: 999px; background: var(--card-background-color, #fff); font-size: .9em; display: inline-flex; align-items: center; gap: 6px; }
  .pill.miss { background: color-mix(in srgb, var(--error-color, #db4437) 18%, transparent); }
  .pill button { padding: 0 2px; opacity: .6; }
  .meta { color: var(--secondary-text-color); font-size: .85em; margin-top: 6px; }
  .seg { display: flex; gap: 4px; }
  .seg button { flex: 1; min-height: 40px; border-radius: 8px; background: var(--secondary-background-color); }
  .seg button.on { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .sheet { position: fixed; inset: 0; z-index: 10; background: rgba(0,0,0,.45); display: flex; align-items: flex-end; justify-content: center; }
  .sheet[hidden] { display: none; }
  .dlg { background: var(--card-background-color, #fff); color: var(--primary-text-color); width: 100%; max-width: 560px; max-height: 88vh; overflow: auto; border-radius: 18px 18px 0 0; padding: 16px 16px calc(16px + env(safe-area-inset-bottom)); }
  .dlg h2 { margin: 0 0 4px; font-size: 1.15em; }
  .dlg .sub { color: var(--secondary-text-color); margin-bottom: 12px; font-size: .9em; }
  .dlg label { display: block; font-size: .85em; color: var(--secondary-text-color); margin: 10px 0 4px; }
  .dlg .menu button { display: flex; align-items: center; gap: 12px; width: 100%; min-height: 50px; padding: 0 8px; border-radius: 10px; text-align: left; font-size: 1.02em; }
  .dlg .menu button:hover { background: var(--secondary-background-color); }
  .dlg .row2 { display: flex; gap: 8px; margin-top: 16px; }
  .dlg .row2 .btn { flex: 1; }
  .photo { display: flex; gap: 12px; align-items: center; }
  .photo .pic { width: 72px; height: 72px; font-size: 44px; }
  .attr { font-size: .75em; color: var(--secondary-text-color); margin-top: 4px; }
  .toast { position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); background: #323232; color: #fff; padding: 12px 16px; border-radius: 8px; z-index: 20; max-width: 90vw; }
  .toast[hidden] { display: none; }
  .order button { width: 40px; height: 40px; border-radius: 8px; }
`;

class HouseholdShoppingCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
    this._tab = "shop";
    this._kindFilter = "all";
    this._search = "";
    this._barKey = null;
    this._collapsed = new Set(JSON.parse(localStorage.getItem("hs-collapsed") || '["__occasional"]'));
    this._lastShopId = null;
  }

  // ------------------------------------------------------------ lifecycle

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    this._config = config || {};
  }

  getCardSize() {
    return 10;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._init();
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    if (this._hass && !this._unsub) this._subscribe();
  }

  disconnectedCallback() {
    this._unsubscribe();
  }

  _init() {
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="top" id="top"></div>
        <div class="tabs" id="tabs"></div>
        <div class="progress" id="progress" hidden></div>
        <div class="bar" id="bar"></div>
        <div class="body" id="body"><div class="empty">Loading…</div></div>
        <div class="foot" id="foot"></div>
      </ha-card>
      <div class="sheet" id="sheet" hidden><div class="dlg" id="dlg"></div></div>
      <div class="toast" id="toast" hidden></div>`;
    const root = this.shadowRoot;
    root.addEventListener("click", (e) => this._onClick(e));
    root.addEventListener("change", (e) => this._onChange(e));
    root.addEventListener("input", (e) => this._onInput(e));
    root.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && e.target.dataset.enter) {
        e.preventDefault();
        this._action(e.target.dataset.enter, e.target);
      }
    });
    root.getElementById("sheet").addEventListener("click", (e) => {
      if (e.target.id === "sheet") this._closeSheet();
    });
    this._setupLongPress();
    this._subscribe();
  }

  async _subscribe() {
    if (this._unsub || !this._hass) return;
    try {
      let entityId = this._config?.entity;
      if (!entityId) {
        const lists = await this._hass.connection.sendMessagePromise({ type: `${DOMAIN}/lists` });
        if (!lists.length) throw new Error("Add the Household Shopping integration first");
        entityId = lists[0].entity_id;
      }
      this._unsub = await this._hass.connection.subscribeMessage((data) => this._update(data), {
        type: `${DOMAIN}/subscribe`,
        entity_id: entityId,
      });
    } catch (err) {
      this.shadowRoot.getElementById("body").innerHTML = `<div class="empty">${esc(err.message || err)}</div>`;
    }
  }

  _unsubscribe() {
    if (this._unsub) {
      const unsub = this._unsub;
      this._unsub = null;
      Promise.resolve(unsub).then((fn) => fn && fn()).catch(() => {});
    }
  }

  _update(data) {
    const prev = this._data;
    this._data = data;
    // BR-SHOP-07: show the summary on the device that sees the shop close.
    if (prev?.shop && !data.shop && data.last_shop?.id === prev.shop.id) {
      this._tab = "shop";
      this._showSummary(data.last_shop);
    }
    this._render();
  }

  // ------------------------------------------------------------- helpers

  get _entity() {
    return this._data?.entity_id;
  }

  async _call(service, data = {}) {
    try {
      await this._hass.callService(DOMAIN, service, data, { entity_id: this._entity });
      return true;
    } catch (err) {
      this._toast(err?.message || String(err));
      return false;
    }
  }

  _toast(message) {
    const el = this.shadowRoot.getElementById("toast");
    el.textContent = message;
    el.hidden = false;
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => (el.hidden = true), 3500);
  }

  _pic(item, size) {
    const style = size ? ` style="width:${size}px;height:${size}px"` : "";
    return item.image?.url
      ? `<span class="pic"${style}><img src="${esc(item.image.url)}" alt="" loading="lazy"></span>`
      : `<span class="pic"${style}>${esc(item.icon || "🛒")}</span>`;
  }

  _options(groups, selected) {
    return groups
      .map((g) => `<option value="${esc(g.id)}" ${g.id === selected ? "selected" : ""}>${esc(g.icon)} ${esc(g.name)}</option>`)
      .join("");
  }

  _cat(id) {
    return this._data.catalogue.find((c) => c.id === id);
  }

  _shopItem(id) {
    return this._data.shop?.items.find((i) => i.id === id);
  }

  _toggleCollapsed(key) {
    this._collapsed.has(key) ? this._collapsed.delete(key) : this._collapsed.add(key);
    localStorage.setItem("hs-collapsed", JSON.stringify([...this._collapsed]));
    this._render();
  }

  // ------------------------------------------------------------- render

  _mode() {
    if (this._tab === "catalogue") return "catalogue";
    return this._data.shop ? this._data.shop.state : "none";
  }

  _render() {
    if (!this._data) return;
    const $ = (id) => this.shadowRoot.getElementById(id);
    const d = this._data;
    const mode = this._mode();
    const state = d.shop?.state || "none";
    const chip = { none: "No shop", planning: "Planning", shopping: "Shopping" }[state];
    const store = d.shop?.store ? ` · ${esc(d.shop.store)}` : "";
    $("top").innerHTML = `<div class="title">${esc(d.name)}</div><span class="chip ${state}">${chip}${store}</span>`;
    $("tabs").innerHTML = `
      <button class="tab ${this._tab === "shop" ? "on" : ""}" data-action="tab" data-tab="shop">🛒 ${d.shop ? "Shop" : "Shops"}</button>
      <button class="tab ${this._tab === "catalogue" ? "on" : ""}" data-action="tab" data-tab="catalogue">📋 Catalogue</button>`;
    this._renderBar(mode);
    this._renderProgress(mode);
    $("body").innerHTML =
      { none: () => this._renderNone(), planning: () => this._renderPlanning(), shopping: () => this._renderShopping(), catalogue: () => this._renderCatalogue() }[mode]();
    $("foot").innerHTML = this._renderFoot(mode);
  }

  _renderBar(mode) {
    // Rebuild only when the mode changes so typing isn't interrupted.
    const bar = this.shadowRoot.getElementById("bar");
    const names = this._data.catalogue.map((c) => `<option value="${esc(c.name)}"></option>`).join("");
    if (this._barKey !== mode) {
      this._barKey = mode;
      if (mode === "planning" || mode === "shopping") {
        bar.innerHTML = `
          <input id="add" list="names" placeholder="Add an item…" autocomplete="off" enterkeyhint="done" data-enter="add">
          <datalist id="names"></datalist>
          <button class="btn primary" data-action="add" aria-label="Add">＋</button>`;
      } else if (mode === "catalogue") {
        bar.innerHTML = `<input id="search" type="search" placeholder="Search catalogue…" value="${esc(this._search)}">`;
      } else {
        bar.innerHTML = "";
      }
    }
    const list = bar.querySelector("#names");
    if (list) list.innerHTML = names;
  }

  _renderProgress(mode) {
    const el = this.shadowRoot.getElementById("progress");
    const items = this._data.shop?.items || [];
    if (mode !== "shopping" || !items.length) {
      el.hidden = true;
      return;
    }
    const pct = (s) => (100 * items.filter((i) => i.state === s).length) / items.length;
    el.hidden = false;
    el.innerHTML = `<i style="width:${pct("got")}%;background:var(--success-color,#43a047)"></i><i style="width:${pct("missing")}%;background:var(--error-color,#db4437)"></i>`;
  }

  _renderNone() {
    const last = this._data.last_shop;
    let html = `<div class="panel" style="text-align:center">
        <div style="font-size:40px">🛒</div>
        <p>No shop open. Start one, then pick what's run out from your stock.</p>
        <button class="btn primary big" data-action="new-shop">New shop</button>
      </div>`;
    if (last) html += this._summaryPanel(last, "Last shop");
    return html;
  }

  _summaryPanel(s, title) {
    const pills = (list, cls = "") =>
      list.length ? `<div class="pills">${list.map((i) => `<span class="pill ${cls}">${esc(i.name)}</span>`).join("")}</div>` : "<div class='meta'>None</div>";
    return `<div class="panel">
      <h3>${esc(title)} · ${esc(fmtDate(s.finished))}${s.store ? ` · ${esc(s.store)}` : ""}</h3>
      <div style="font-weight:600;margin:8px 0 6px">❌ Missing (${s.missing.length})</div>${pills(s.missing, "miss")}
      ${s.not_got.length ? `<div style="font-weight:600;margin:12px 0 6px">⏭ Not got (${s.not_got.length})</div>${pills(s.not_got)}` : ""}
      <div class="meta">✓ Got ${s.got.length} item${s.got.length === 1 ? "" : "s"}</div>
    </div>`;
  }

  _renderPlanning() {
    const d = this._data;
    const onList = new Set(d.shop.items.map((i) => i.catalogue_id));
    const tick = (c) => `
      <div class="row click" data-action="toggle" data-id="${esc(c.id)}" data-on="${onList.has(c.id) ? 1 : 0}">
        <span class="tick ${onList.has(c.id) ? "on" : ""}">${onList.has(c.id) ? "✓" : ""}</span>
        ${this._pic(c)}
        <div class="txt"><div class="name">${esc(c.name)}</div>${c.note ? `<div class="note">${esc(c.note)}</div>` : ""}</div>
      </div>`;
    const group = (key, title, items) => {
      const picked = items.filter((c) => onList.has(c.id)).length;
      const closed = this._collapsed.has(key);
      return `<div class="group">
        <div class="ghead click" data-action="collapse" data-key="${esc(key)}">${closed ? "▸" : "▾"} ${title}<span class="count">${picked}/${items.length}</span></div>
        ${closed ? "" : items.map(tick).join("")}
      </div>`;
    };
    let html = "";
    // List so far, compact.
    const items = d.shop.items;
    html += `<div class="panel"><h3>On this shop (${items.length})</h3>${
      items.length
        ? `<div class="pills">${items
            .map((i) => `<span class="pill ${i.state === "missing" ? "miss" : ""}">${esc(i.name)}<button data-action="remove" data-id="${esc(i.id)}" aria-label="Remove">✕</button></span>`)
            .join("")}</div>`
        : `<div class="meta">Tick what's run out below, or add anything else above.</div>`
    }</div>`;
    if (!d.stock_check.length) {
      html += `<div class="empty">No stock yet. Add stock in the Catalogue tab, or paste a list.</div>`;
    }
    // BR-STOCK-04: stock check grouped by home location.
    for (const g of d.stock_check) html += group(`loc:${g.id}`, `${esc(g.icon)} ${esc(g.name)}`, g.items);
    // BR-OCC-03: occasional items, collapsed by default.
    const occ = d.catalogue.filter((c) => c.kind === "occasional").sort((a, b) => a.name.localeCompare(b.name));
    if (occ.length) html += group("__occasional", "✨ Occasional", occ);
    return html;
  }

  _renderShopping() {
    const groups = this._data.shop.by_aisle;
    if (!groups.length) return `<div class="empty">Nothing on the list yet. Add items above.</div>`;
    return groups
      .map(
        (g) => `<div class="group">
        <div class="ghead">${esc(g.icon)} ${esc(g.name)}<span class="count">${g.items.filter((i) => i.state === "needed").length} left</span></div>
        ${g.items
          .map(
            (i) => `<div class="row ${i.state}" data-press="${esc(i.id)}">
            ${this._pic(i)}
            <div class="txt"><div class="name">${esc(i.name)}</div>${i.note ? `<div class="note">${esc(i.note)}</div>` : ""}</div>
            <button class="act miss ${i.state === "missing" ? "on" : ""}" data-action="state" data-id="${esc(i.id)}" data-state="missing" aria-label="Missing">✗</button>
            <button class="act got ${i.state === "got" ? "on" : ""}" data-action="state" data-id="${esc(i.id)}" data-state="got" aria-label="Got">✓</button>
          </div>`
          )
          .join("")}
      </div>`
      )
      .join("");
  }

  _renderCatalogue() {
    const d = this._data;
    const q = this._search.trim().toLowerCase();
    const filter = (c) =>
      (this._kindFilter === "all" || c.kind === this._kindFilter) &&
      (!q || c.name.toLowerCase().includes(q) || (c.note || "").toLowerCase().includes(q));
    const row = (c) => `
      <div class="row click" data-action="edit" data-id="${esc(c.id)}">
        ${this._pic(c)}
        <div class="txt"><div class="name">${esc(c.name)}</div>
          <div class="note">${c.kind === "stock" ? `${esc(c.location_name)} · ` : "Occasional · "}${esc(c.aisle_name)}${c.note ? ` · ${esc(c.note)}` : ""}</div></div>
        <span>›</span>
      </div>`;
    let html = `<div class="seg" style="padding:0 8px 8px">
      ${["all", "stock", "occasional"].map((k) => `<button class="${this._kindFilter === k ? "on" : ""}" data-action="kind-filter" data-kind="${k}">${{ all: "All", stock: "Stock", occasional: "Occasional" }[k]}</button>`).join("")}
    </div>
    <div class="seg" style="padding:0 8px 8px">
      <button data-action="new-item">＋ Item</button>
      <button data-action="paste">📋 Paste list</button>
      <button data-action="groups">⚙️ Groups</button>
    </div>`;
    const items = d.catalogue.filter(filter);
    if (!items.length) return html + `<div class="empty">${d.catalogue.length ? "No matches." : "The catalogue is empty. Add items, paste a list, or ask your assistant to import a receipt."}</div>`;
    // Stock grouped by location; occasional alphabetically.
    for (const loc of d.locations) {
      const inLoc = items.filter((c) => c.kind === "stock" && c.location === loc.id);
      if (inLoc.length) html += `<div class="group"><div class="ghead">${esc(loc.icon)} ${esc(loc.name)}<span class="count">${inLoc.length}</span></div>${inLoc.map(row).join("")}</div>`;
    }
    const occ = items.filter((c) => c.kind === "occasional").sort((a, b) => a.name.localeCompare(b.name));
    if (occ.length) html += `<div class="group"><div class="ghead">✨ Occasional<span class="count">${occ.length}</span></div>${occ.map(row).join("")}</div>`;
    return html;
  }

  _renderFoot(mode) {
    if (mode === "planning")
      return `<button class="btn" data-action="cancel-shop">Cancel</button>
              <button class="btn" data-action="store">🏪 Store</button>
              <button class="btn primary" style="flex:1" data-action="start">Start shopping →</button>`;
    if (mode === "shopping")
      return `<button class="btn" data-action="back-plan" title="Add from stock">📋 Stock</button>
              <button class="btn primary" style="flex:1" data-action="finish">Finish shop</button>`;
    return "";
  }

  // ------------------------------------------------------------ events

  _onClick(e) {
    if (this._suppressRow?.contains(e.target)) {
      this._suppressRow = null;
      return;
    }
    const el = e.target.closest("[data-action]");
    if (!el) return;
    this._action(el.dataset.action, el);
  }

  _onInput(e) {
    if (e.target.id === "search") {
      this._search = e.target.value;
      this.shadowRoot.getElementById("body").innerHTML = this._renderCatalogue();
    }
  }

  _onChange(e) {
    const t = e.target;
    if (t.id === "photo" && t.files?.[0]) this._uploadPhoto(t.dataset.name, t.files[0]);
  }

  async _action(action, el) {
    const id = el.dataset.id;
    const v = (sel) => this.shadowRoot.querySelector(sel)?.value?.trim() ?? "";
    switch (action) {
      case "tab":
        this._tab = el.dataset.tab;
        return this._render();
      case "collapse":
        return this._toggleCollapsed(el.dataset.key);
      case "new-shop":
        return this._call("new_shop");
      case "add": {
        const input = this.shadowRoot.getElementById("add");
        const name = input.value.trim();
        if (!name) return;
        input.value = "";
        input.focus();
        return this._call("add_item", { name });
      }
      case "toggle":
        if (el.closest("#dlg")) el.remove(); // quick-add sheet: drop the row once added
        return this._call("toggle_stock", { name: this._cat(id)?.name ?? id, on: el.dataset.on !== "1" });
      case "remove":
        return this._call("remove_item", { item: id });
      case "state": {
        const item = this._shopItem(id);
        const next = item.state === el.dataset.state ? "needed" : el.dataset.state;
        return this._call("set_item_state", { item: id, state: next });
      }
      case "start":
        return this._call("start_shopping");
      case "cancel-shop":
        return this._confirm("Cancel this shop?", "The list will be deleted.", "Cancel shop", () => this._call("cancel_shop"));
      case "store":
        return this._storeSheet();
      case "back-plan":
        return this._stockSheet();
      case "finish": {
        const left = this._data.shop.items.filter((i) => i.state === "needed").length;
        const missing = this._data.shop.items.filter((i) => i.state === "missing").length;
        return this._confirm(
          "Finish this shop?",
          `${missing} missing${left ? ` · ${left} not got yet` : ""}. Got items are cleared and the summary is saved.`,
          "Finish",
          () => this._call("finish_shop")
        );
      }
      case "kind-filter":
        this._kindFilter = el.dataset.kind;
        return this._render();
      case "edit":
        return this._editSheet(this._cat(id));
      case "new-item":
        return this._editSheet(null);
      case "paste":
        return this._pasteSheet();
      case "groups":
        return this._groupsSheet(el.dataset.type || "locations");
      // ---- sheet actions
      case "close":
        return this._closeSheet();
      case "sheet-state":
        this._closeSheet();
        return this._call("set_item_state", { item: id, state: el.dataset.state });
      case "sheet-remove":
        this._closeSheet();
        return this._call("remove_item", { item: id });
      case "sheet-note":
        return this._noteSheet(this._shopItem(id));
      case "save-note": {
        const note = v("#f-note");
        this._closeSheet();
        return this._call("update_item", { item: id, note });
      }
      case "sheet-aisle":
        return this._aisleSheet(this._shopItem(id));
      case "pick-aisle":
        this._closeSheet();
        return this._call("update_item", { item: el.dataset.item, aisle: id });
      case "sheet-stock":
        return this._promoteSheet(this._shopItem(id));
      case "promote": {
        const location = v("#f-loc");
        this._closeSheet();
        return this._call("promote_to_stock", { name: el.dataset.name, location });
      }
      case "sheet-photo":
        this._closeSheet();
        return this._editSheet(this._cat(this._shopItem(id)?.catalogue_id));
      case "save-store-real": {
        const store = v("#f-store");
        this._closeSheet();
        return this._call("set_store", { store });
      }
      case "save-item":
        return this._saveItem(el);
      case "delete-item":
        return this._confirm(`Delete "${el.dataset.name}"?`, "It's removed from the catalogue, along with its photo.", "Delete", async () => {
          await this._call("remove_catalogue_item", { name: el.dataset.name });
        });
      case "set-kind":
        this.shadowRoot.querySelectorAll("[data-action=set-kind]").forEach((b) => b.classList.toggle("on", b === el));
        this.shadowRoot.getElementById("f-loc-wrap").hidden = el.dataset.kind !== "stock";
        return;
      case "pick-photo":
        return this.shadowRoot.getElementById("photo").click();
      case "clear-photo":
        this._closeSheet();
        return this._call("clear_item_image", { name: el.dataset.name });
      case "do-paste":
        return this._doPaste();
      case "group-type":
        return this._groupsSheet(el.dataset.type);
      case "group-move":
        return this._moveGroup(el.dataset.type, id, Number(el.dataset.dir));
      case "group-rename":
        return this._renameGroup(el.dataset.type, id);
      case "group-delete":
        return this._confirm("Delete this group?", "Its items move to Other.", "Delete", async () => {
          await this._call("remove_group", { type: el.dataset.type, group: id });
          this._groupsSheet(el.dataset.type);
        });
      case "group-add": {
        const name = v("#g-new");
        if (!name) return;
        if (await this._call("add_group", { type: el.dataset.type, name, icon: v("#g-icon") || undefined })) this._groupsSheet(el.dataset.type);
        return;
      }
      case "confirm":
        this._closeSheet();
        return this._confirmFn?.();
      default:
        return undefined;
    }
  }

  // --------------------------------------------------- long press (BR-ITEM-05)

  _setupLongPress() {
    const root = this.shadowRoot;
    let timer = null;
    let start = null;
    const cancel = () => {
      clearTimeout(timer);
      timer = null;
    };
    root.addEventListener("pointerdown", (e) => {
      const row = e.target.closest("[data-press]");
      if (!row || e.target.closest("button")) return;
      start = { x: e.clientX, y: e.clientY };
      timer = setTimeout(() => {
        timer = null;
        // Swallow the click that ends this press, but only on the pressed row,
        // so taps in the menu that opens still work.
        this._suppressRow = row;
        setTimeout(() => (this._suppressRow = null), 1000);
        navigator.vibrate?.(15);
        this._itemMenu(this._shopItem(row.dataset.press));
      }, LONG_PRESS_MS);
    });
    root.addEventListener("pointermove", (e) => {
      if (timer && start && Math.hypot(e.clientX - start.x, e.clientY - start.y) > 10) cancel();
    });
    root.addEventListener("pointerup", cancel);
    root.addEventListener("pointercancel", cancel);
    root.addEventListener("contextmenu", (e) => {
      const row = e.target.closest("[data-press]");
      if (!row) return;
      e.preventDefault();
      cancel();
      this._itemMenu(this._shopItem(row.dataset.press));
    });
  }

  // -------------------------------------------------------------- sheets

  _openSheet(html) {
    this.shadowRoot.getElementById("dlg").innerHTML = html;
    this.shadowRoot.getElementById("sheet").hidden = false;
  }

  _closeSheet() {
    this.shadowRoot.getElementById("sheet").hidden = true;
    this.shadowRoot.getElementById("dlg").innerHTML = "";
  }

  _confirm(title, sub, label, fn) {
    this._confirmFn = fn;
    this._openSheet(`<h2>${esc(title)}</h2><div class="sub">${esc(sub)}</div>
      <div class="row2"><button class="btn" data-action="close">Back</button>
      <button class="btn primary" data-action="confirm">${esc(label)}</button></div>`);
  }

  _showSummary(s) {
    this._openSheet(`<h2>Shop finished 🎉</h2>${this._summaryPanel(s, "Summary")}
      <div class="row2"><button class="btn primary" data-action="close">Done</button></div>`);
  }

  _itemMenu(item) {
    if (!item) return;
    const id = esc(item.id);
    const opt = (action, icon, label, extra = "") =>
      `<button data-action="${action}" data-id="${id}" ${extra}><span style="width:28px;text-align:center">${icon}</span>${label}</button>`;
    const isStock = item.kind === "stock";
    this._openSheet(`
      <div class="photo">${this._pic(item)}<div><h2>${esc(item.name)}</h2><div class="sub">${esc(item.aisle_name)}${item.note ? ` · ${esc(item.note)}` : ""}</div></div></div>
      <div class="menu">
        ${item.state !== "got" ? opt("sheet-state", "✓", "Got it", 'data-state="got"') : ""}
        ${item.state !== "missing" ? opt("sheet-state", "✗", "Missing at this shop", 'data-state="missing"') : ""}
        ${item.state !== "needed" ? opt("sheet-state", "↺", "Still needed", 'data-state="needed"') : ""}
        ${opt("sheet-note", "✎", "Edit note")}
        ${opt("sheet-aisle", "🧭", "Change aisle")}
        ${item.catalogue_id && !isStock ? opt("sheet-stock", "⭐", "Save to stock") : ""}
        ${item.catalogue_id ? opt("sheet-photo", "📷", "Photo & details") : ""}
        ${opt("sheet-remove", "🗑", "Remove from this shop")}
      </div>
      <div class="row2"><button class="btn" data-action="close">Close</button></div>`);
  }

  _noteSheet(item) {
    this._openSheet(`<h2>${esc(item.name)}</h2><label>Note (brand, size…)</label>
      <input id="f-note" value="${esc(item.note)}" data-enter="save-note" data-id="${esc(item.id)}">
      <div class="row2"><button class="btn" data-action="close">Cancel</button>
      <button class="btn primary" data-action="save-note" data-id="${esc(item.id)}">Save</button></div>`);
    this.shadowRoot.getElementById("f-note").focus();
  }

  _aisleSheet(item) {
    this._openSheet(`<h2>Aisle for ${esc(item.name)}</h2><div class="sub">This is remembered for next time.</div><div class="menu">
      ${this._data.aisles
        .map((a) => `<button data-action="pick-aisle" data-id="${esc(a.id)}" data-item="${esc(item.id)}"><span style="width:28px;text-align:center">${esc(a.icon)}</span>${esc(a.name)}${a.id === item.aisle ? " ✓" : ""}</button>`)
        .join("")}</div>`);
  }

  _promoteSheet(item) {
    const entry = this._cat(item.catalogue_id);
    this._openSheet(`<h2>Save ${esc(item.name)} to stock</h2><div class="sub">Where is it kept at home?</div>
      <select id="f-loc">${this._options(this._data.locations, entry?.location)}</select>
      <div class="row2"><button class="btn" data-action="close">Cancel</button>
      <button class="btn primary" data-action="promote" data-name="${esc(entry?.name ?? item.name)}">Save to stock</button></div>`);
  }

  _storeSheet() {
    this._openSheet(`<h2>Store</h2><div class="sub">Optional. It's shown in the summary.</div>
      <input id="f-store" value="${esc(this._data.shop?.store || "")}" placeholder="e.g. Woolworths Woden" data-enter="save-store-real">
      <div class="row2"><button class="btn" data-action="close">Cancel</button>
      <button class="btn primary" data-action="save-store-real">Save</button></div>`);
    this.shadowRoot.getElementById("f-store").focus();
  }

  _stockSheet() {
    // While shopping: quick access to the stock check without leaving shop mode.
    const d = this._data;
    const onList = new Set(d.shop.items.map((i) => i.catalogue_id));
    const rows = d.catalogue
      .filter((c) => !onList.has(c.id))
      .sort((a, b) => (a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === "stock" ? -1 : 1))
      .map((c) => `<button data-action="toggle" data-id="${esc(c.id)}" data-on="0">${this._pic(c, 32)}${esc(c.name)}</button>`)
      .join("");
    this._openSheet(`<h2>Add from catalogue</h2><div class="sub">Tap to add to this shop.</div>
      <div class="menu">${rows || "<div class='meta'>Everything's already on the list.</div>"}</div>
      <div class="row2"><button class="btn" data-action="close">Done</button></div>`);
  }

  _editSheet(item) {
    const d = this._data;
    const isNew = !item;
    const it = item || { name: "", kind: "stock", location: "other", aisle: "other", note: "", icon: "", image: null };
    const icon = it.icon_custom ? it.icon : "";
    this._openSheet(`
      <h2>${isNew ? "New catalogue item" : esc(it.name)}</h2>
      ${isNew ? "" : `<div class="photo">${this._pic(it)}
        <div><button class="btn" data-action="pick-photo">📷 ${it.image ? "Replace photo" : "Add photo"}</button>
        ${it.image ? `<button class="btn danger" data-action="clear-photo" data-name="${esc(it.name)}">Remove</button>` : ""}
        ${it.image?.attribution ? `<div class="attr">Photo: ${esc(it.image.attribution)}</div>` : ""}</div>
        <input type="file" id="photo" accept="image/*" hidden data-name="${esc(it.name)}"></div>`}
      <label>Name</label><input id="f-name" value="${esc(it.name)}">
      <label>Kind</label>
      <div class="seg">
        <button class="${it.kind === "stock" ? "on" : ""}" data-action="set-kind" data-kind="stock">Stock</button>
        <button class="${it.kind === "occasional" ? "on" : ""}" data-action="set-kind" data-kind="occasional">Occasional</button>
      </div>
      <div id="f-loc-wrap" ${it.kind === "stock" ? "" : "hidden"}><label>Home location</label><select id="f-loc">${this._options(d.locations, it.location)}</select></div>
      <label>Aisle</label><select id="f-aisle">${this._options(d.aisles, it.aisle)}</select>
      <label>Note (brand, size…)</label><input id="f-note" value="${esc(it.note)}">
      <label>Icon (emoji, blank = automatic${isNew ? "" : `: ${esc(it.icon)}`})</label><input id="f-icon" value="${esc(icon)}" maxlength="8">
      <div class="row2">
        ${isNew ? "" : `<button class="btn danger" data-action="delete-item" data-name="${esc(it.name)}">Delete</button>`}
        <button class="btn" data-action="close">Cancel</button>
        <button class="btn primary" data-action="save-item" data-name="${esc(it.name)}" data-new="${isNew ? 1 : 0}">Save</button>
      </div>`);
  }

  async _saveItem(el) {
    const $ = (s) => this.shadowRoot.querySelector(s);
    const kind = $("[data-action=set-kind].on")?.dataset.kind || "stock";
    const name = $("#f-name").value.trim();
    if (!name) return this._toast("A name is required");
    const fields = { aisle: $("#f-aisle").value, note: $("#f-note").value.trim(), icon: $("#f-icon").value.trim() };
    if (kind === "stock") fields.location = $("#f-loc").value;
    let ok;
    if (el.dataset.new === "1") {
      ok = await this._call(kind === "stock" ? "add_stock_item" : "add_occasional_item", { name, ...fields });
    } else {
      const original = el.dataset.name;
      ok = await this._call("update_catalogue_item", { name: original, ...(name !== original ? { new_name: name } : {}), ...fields });
      const current = this._data.catalogue.find((c) => c.name === original || c.name === name);
      if (ok && current && current.kind !== kind)
        ok = await this._call(kind === "stock" ? "promote_to_stock" : "demote_to_occasional", { name, ...(kind === "stock" ? { location: fields.location } : {}) });
    }
    if (ok) this._closeSheet();
  }

  async _uploadPhoto(name, file) {
    this._toast("Uploading photo…");
    try {
      const data = await shrink(file, 1024);
      if (await this._call("set_item_image", { name, image_data: data, source: "own", force: true })) {
        this._toast("Photo saved");
        this._closeSheet();
      }
    } catch (err) {
      this._toast(`Couldn't read that photo: ${err.message || err}`);
    }
  }

  _pasteSheet() {
    const d = this._data;
    this._openSheet(`<h2>Paste a list</h2><div class="sub">One item per line. Items already in the catalogue are updated.</div>
      <textarea id="p-text" placeholder="Milk&#10;Bread&#10;Eggs"></textarea>
      <label>Add as</label>
      <div class="seg">
        <button class="on" data-action="set-kind" data-kind="stock">Stock</button>
        <button data-action="set-kind" data-kind="occasional">Occasional</button>
      </div>
      <div id="f-loc-wrap"><label>Home location</label><select id="f-loc">${this._options(d.locations, "other")}</select></div>
      <label>Aisle</label><select id="f-aisle">${this._options(d.aisles, "other")}</select>
      <div class="row2"><button class="btn" data-action="close">Cancel</button>
      <button class="btn primary" data-action="do-paste">Import</button></div>`);
  }

  async _doPaste() {
    const $ = (s) => this.shadowRoot.querySelector(s);
    const kind = $("[data-action=set-kind].on")?.dataset.kind || "stock";
    const names = [...new Set($("#p-text").value.split("\n").map((s) => s.trim()).filter(Boolean))];
    if (!names.length) return this._toast("Nothing to import");
    const items = names.map((name) => ({ name, kind, aisle: $("#f-aisle").value, ...(kind === "stock" ? { location: $("#f-loc").value } : {}) }));
    if (await this._call("import_catalogue", { items })) {
      this._closeSheet();
      this._toast(`Imported ${names.length} item${names.length === 1 ? "" : "s"}`);
    }
  }

  _groupsSheet(type) {
    const groups = this._data[type];
    const label = type === "locations" ? "Home locations" : "Aisles";
    this._openSheet(`<h2>${label}</h2>
      <div class="seg" style="margin-bottom:8px">
        <button class="${type === "locations" ? "on" : ""}" data-action="group-type" data-type="locations">Home locations</button>
        <button class="${type === "aisles" ? "on" : ""}" data-action="group-type" data-type="aisles">Aisles</button>
      </div>
      <div class="sub">${type === "aisles" ? "Put these in the order you walk your usual shop." : "These group the stock check. Put them in the order you walk around the house."}</div>
      ${groups
        .map(
          (g, i) => `<div class="row order">
            <span class="pic">${esc(g.icon)}</span><div class="txt name">${esc(g.name)}</div>
            ${g.id === "other" ? "" : `
              <button data-action="group-move" data-type="${type}" data-id="${esc(g.id)}" data-dir="-1" ${i === 0 ? "disabled" : ""} aria-label="Up">↑</button>
              <button data-action="group-move" data-type="${type}" data-id="${esc(g.id)}" data-dir="1" ${i >= groups.length - 2 ? "disabled" : ""} aria-label="Down">↓</button>
              <button data-action="group-rename" data-type="${type}" data-id="${esc(g.id)}" aria-label="Rename">✎</button>
              <button data-action="group-delete" data-type="${type}" data-id="${esc(g.id)}" aria-label="Delete">🗑</button>`}
          </div>`
        )
        .join("")}
      <label>Add</label>
      <div style="display:flex;gap:8px"><input id="g-icon" placeholder="🙂" style="width:64px" maxlength="8"><input id="g-new" placeholder="Name" data-enter="group-add" data-type="${type}">
      <button class="btn primary" data-action="group-add" data-type="${type}">Add</button></div>
      <div class="row2"><button class="btn" data-action="close">Done</button></div>`);
  }

  async _moveGroup(type, id, dir) {
    const ids = this._data[type].map((g) => g.id).filter((g) => g !== "other");
    const i = ids.indexOf(id);
    const j = i + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    if (await this._call("order_groups", { type, groups: ids })) this._groupsSheet(type);
  }

  async _renameGroup(type, id) {
    const g = this._data[type].find((x) => x.id === id);
    const name = prompt("New name", g.name);
    if (name === null) return;
    const icon = prompt("Icon (emoji)", g.icon);
    if (await this._call("update_group", { type, group: id, name: name.trim() || g.name, ...(icon ? { icon } : {}) })) this._groupsSheet(type);
  }
}

/** Resize a photo in the browser before upload so the action payload stays small. */
async function shrink(file, max) {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise((res) => canvas.toBlob(res, "image/jpeg", 0.85));
  const buf = new Uint8Array(await blob.arrayBuffer());
  let bin = "";
  for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  return btoa(bin);
}

if (!customElements.get("household-shopping-card")) {
  customElements.define("household-shopping-card", HouseholdShoppingCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "household-shopping-card",
    name: "Household Shopping",
    description: "Plan from stock, shop by aisle, and track what was missing.",
    preview: false,
    documentationURL: "https://github.com/Snawboll/household-shopping",
  });
  console.info(`%c HOUSEHOLD-SHOPPING-CARD %c ${VERSION} `, "background:#0a7;color:#fff", "background:#333;color:#fff");
}
