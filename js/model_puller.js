import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const PREFIX = "/mhnodes/model_puller";
const S = (id) => `MHNodes.ModelPuller.${id}`;

const fmtSize = (bytes) => {
  if (!bytes) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes, i = 0;
  while (value >= 1024 && i < units.length - 1) { value /= 1024; i++; }
  return `${value.toFixed(value < 10 && i > 1 ? 1 : 0)} ${units[i]}`;
};

const call = async (path, options) => {
  const response = await api.fetchApi(PREFIX + path, options);
  if (!response.ok) {
    let reason = response.statusText;
    try { reason = (await response.json()).error || reason; } catch { /* keep statusText */ }
    throw new Error(reason);
  }
  return response.json();
};

const toast = (severity, summary, detail, life = 4000) =>
  app.extensionManager.toast.add({ severity, summary, detail, life });

// ---------------------------------------------------------------------------- styles

const CSS = `
.mhmp-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,.6); z-index: 10000;
  display: flex; align-items: center; justify-content: center; }
.mhmp { background: var(--comfy-menu-bg, #202020); color: var(--fg-color, #ddd);
  border: 1px solid var(--border-color, #444); border-radius: 8px; width: min(820px, 92vw);
  height: min(640px, 86vh); display: flex; flex-direction: column;
  font-family: system-ui, sans-serif; font-size: 13px; box-shadow: 0 12px 48px rgba(0,0,0,.5); }
.mhmp header { padding: 12px 16px; border-bottom: 1px solid var(--border-color, #444);
  display: flex; align-items: center; gap: 12px; }
.mhmp header h3 { margin: 0; font-size: 15px; font-weight: 600; flex: 1; }
.mhmp .mhmp-close { background: none; border: none; color: inherit; cursor: pointer;
  font-size: 20px; line-height: 1; padding: 0 4px; opacity: .7; }
.mhmp .mhmp-close:hover { opacity: 1; }
.mhmp .mhmp-crumbs { padding: 8px 16px; border-bottom: 1px solid var(--border-color, #444);
  opacity: .8; font-size: 12px; word-break: break-all; }
.mhmp .mhmp-crumbs a { color: var(--p-primary-color, #5af); cursor: pointer; text-decoration: none; }
.mhmp .mhmp-crumbs a:hover { text-decoration: underline; }
.mhmp .mhmp-list { flex: 1; overflow-y: auto; padding: 4px 0; }
.mhmp .mhmp-row { display: flex; align-items: center; gap: 10px; padding: 6px 16px; }
.mhmp .mhmp-row:hover { background: rgba(255,255,255,.05); }
.mhmp .mhmp-row.mhmp-dir { cursor: pointer; }
.mhmp .mhmp-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mhmp .mhmp-size { opacity: .55; font-variant-numeric: tabular-nums; font-size: 12px; }
.mhmp .mhmp-tag { font-size: 11px; padding: 1px 7px; border-radius: 10px; white-space: nowrap; }
.mhmp .mhmp-have { background: #1d4d2b; color: #8ae6a4; }
.mhmp .mhmp-soon { background: #5a4410; color: #ffd98a; }
.mhmp .mhmp-perm { background: #26406b; color: #9cc5ff; }
.mhmp .mhmp-keep { background: none; border: 1px solid var(--border-color, #555);
  color: inherit; border-radius: 4px; padding: 2px 9px; cursor: pointer; font-size: 11px; }
.mhmp .mhmp-keep:hover { border-color: #8ae6a4; color: #8ae6a4; }
.mhmp .mhmp-bar { height: 3px; background: #3b82f6; border-radius: 2px; transition: width .2s; }
.mhmp .mhmp-track { flex: 1; height: 3px; background: rgba(255,255,255,.12); border-radius: 2px; }
.mhmp footer { padding: 10px 16px; border-top: 1px solid var(--border-color, #444);
  display: flex; align-items: center; gap: 12px; }
.mhmp footer .mhmp-info { flex: 1; opacity: .7; font-size: 12px; }
.mhmp button.mhmp-primary { background: var(--p-primary-color, #3b82f6); border: none;
  color: #fff; padding: 6px 16px; border-radius: 5px; cursor: pointer; font-size: 13px; }
.mhmp button.mhmp-primary:disabled { opacity: .4; cursor: default; }
.mhmp .mhmp-empty { padding: 32px 16px; text-align: center; opacity: .55; }
.mhmp-xfers { position: fixed; right: 16px; bottom: 16px; z-index: 10001; width: 330px;
  background: var(--comfy-menu-bg, #202020); color: var(--fg-color, #ddd);
  border: 1px solid var(--border-color, #444); border-radius: 8px;
  font-family: system-ui, sans-serif; font-size: 12px; box-shadow: 0 8px 28px rgba(0,0,0,.45); }
.mhmp-xfers h4 { margin: 0; padding: 9px 12px; font-size: 12px; font-weight: 600;
  border-bottom: 1px solid var(--border-color, #444); display: flex; gap: 8px; }
.mhmp-xfers h4 span { flex: 1; }
.mhmp-xfers .mhmp-all { background: none; border: none; color: #ff9a9a; cursor: pointer;
  font-size: 11px; padding: 0; }
.mhmp-xfer { padding: 8px 12px; border-bottom: 1px solid rgba(255,255,255,.06); }
.mhmp-xfer:last-child { border-bottom: none; }
.mhmp-xfer .mhmp-xname { display: flex; gap: 8px; align-items: center; }
.mhmp-xfer .mhmp-xname span { flex: 1; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; }
.mhmp-xfer button { background: none; border: 1px solid var(--border-color, #555);
  color: inherit; border-radius: 4px; padding: 1px 7px; cursor: pointer; font-size: 11px; }
.mhmp-xfer button:hover { border-color: #ff9a9a; color: #ff9a9a; }
.mhmp-xfer .mhmp-xbar { height: 3px; background: rgba(255,255,255,.12); border-radius: 2px;
  margin-top: 6px; overflow: hidden; }
.mhmp-xfer .mhmp-xfill { height: 3px; background: #3b82f6; width: 0%; transition: width .2s; }
.mhmp-xfer .mhmp-xpct { opacity: .6; font-variant-numeric: tabular-nums; margin-top: 4px; }
`;

const injectStyles = () => {
  if (document.getElementById("mhmp-styles")) return;
  const style = document.createElement("style");
  style.id = "mhmp-styles";
  style.textContent = CSS;
  document.head.appendChild(style);
};

// ---------------------------------------------------------------------------- browser

class ModelBrowser {
  constructor() {
    this.path = "";
    this.selected = new Set();
    this.progress = new Map();   // key -> { copied, total }
    this.rows = new Map();       // key -> row element
  }

  async open() {
    injectStyles();
    const config = await call("/config");
    if (!config.server_ok) {
      toast("warn", "Server path not set",
        "Set it in Settings → MHNodes, under Model Puller.", 6000);
      return;
    }
    this.render();
    await this.load("");
  }

  render() {
    this.backdrop = document.createElement("div");
    this.backdrop.className = "mhmp-backdrop";
    this.backdrop.innerHTML = `
      <div class="mhmp" role="dialog" aria-label="Pull models from server">
        <header>
          <h3>Pull models from server</h3>
          <button class="mhmp-close" aria-label="Close">&times;</button>
        </header>
        <div class="mhmp-crumbs"></div>
        <div class="mhmp-list"></div>
        <footer>
          <span class="mhmp-info"></span>
          <button class="mhmp-primary" disabled>Pull selected</button>
        </footer>
      </div>`;

    this.crumbs = this.backdrop.querySelector(".mhmp-crumbs");
    this.list = this.backdrop.querySelector(".mhmp-list");
    this.info = this.backdrop.querySelector(".mhmp-info");
    this.pullButton = this.backdrop.querySelector(".mhmp-primary");

    this.backdrop.querySelector(".mhmp-close").onclick = () => this.close();
    this.backdrop.onclick = (e) => { if (e.target === this.backdrop) this.close(); };
    this.onKey = (e) => { if (e.key === "Escape") this.close(); };
    document.addEventListener("keydown", this.onKey);
    this.pullButton.onclick = () => this.pull();

    document.body.appendChild(this.backdrop);
  }

  close() {
    document.removeEventListener("keydown", this.onKey);
    this.backdrop?.remove();
    activeBrowser = null;
  }

  async load(path) {
    this.path = path;
    this.list.innerHTML = `<div class="mhmp-empty">Loading…</div>`;
    let data;
    try {
      data = await call(`/browse?path=${encodeURIComponent(path)}`);
    } catch (err) {
      this.list.innerHTML = `<div class="mhmp-empty">${err.message}</div>`;
      return;
    }
    this.renderCrumbs(path);
    this.renderList(data);
  }

  renderCrumbs(path) {
    const parts = path ? path.split("/").filter(Boolean) : [];
    this.crumbs.replaceChildren();
    const root = document.createElement("a");
    root.textContent = "server";
    root.onclick = () => this.load("");
    this.crumbs.appendChild(root);
    parts.forEach((part, i) => {
      this.crumbs.append(" / ");
      if (i === parts.length - 1) {
        this.crumbs.append(part);
      } else {
        const link = document.createElement("a");
        link.textContent = part;
        link.onclick = () => this.load(parts.slice(0, i + 1).join("/"));
        this.crumbs.appendChild(link);
      }
    });
  }

  renderList(data) {
    this.list.replaceChildren();
    this.rows.clear();

    if (this.path) {
      const up = this.makeRow({ name: "..", isUp: true });
      up.onclick = () => this.load(this.path.split("/").slice(0, -1).join("/"));
      this.list.appendChild(up);
    }
    for (const dir of data.directories) {
      const row = this.makeRow({ name: dir.name, isDir: true });
      row.onclick = () => this.load(dir.path);
      this.list.appendChild(row);
    }
    for (const file of data.files) {
      this.list.appendChild(this.makeFileRow(file));
    }
    if (!data.directories.length && !data.files.length) {
      this.list.innerHTML = `<div class="mhmp-empty">Nothing here.</div>`;
    }
    this.updateFooter();
  }

  makeRow({ name, isDir, isUp }) {
    const row = document.createElement("div");
    row.className = `mhmp-row${isDir || isUp ? " mhmp-dir" : ""}`;
    row.innerHTML = `<span style="width:14px;opacity:.6">${isUp ? "↑" : isDir ? "▸" : ""}</span>
                     <span class="mhmp-name">${name}</span>`;
    return row;
  }

  makeFileRow(file) {
    const row = document.createElement("div");
    row.className = "mhmp-row";
    row.dataset.key = file.key;

    const box = document.createElement("input");
    box.type = "checkbox";
    box.disabled = file.state !== "absent";
    box.checked = this.selected.has(file.path);
    box.onchange = () => {
      box.checked ? this.selected.add(file.path) : this.selected.delete(file.path);
      this.updateFooter();
    };
    row.appendChild(box);

    const name = document.createElement("span");
    name.className = "mhmp-name";
    name.textContent = file.name;
    name.title = file.path;
    row.appendChild(name);

    const size = document.createElement("span");
    size.className = "mhmp-size";
    size.textContent = fmtSize(file.size);
    row.appendChild(size);

    // Three states, because "you have it" means something different when it is about to expire.
    if (file.state === "managed") {
      const tag = document.createElement("span");
      const soon = file.days_left !== null && file.days_left <= 2;
      tag.className = `mhmp-tag ${soon ? "mhmp-soon" : "mhmp-have"}`;
      tag.textContent = file.days_left === null ? "✓ local"
        : file.days_left === 0 ? "✓ expires today"
        : `✓ ${file.days_left}d left`;
      row.appendChild(tag);

      const keep = document.createElement("button");
      keep.className = "mhmp-keep";
      keep.textContent = "Keep";
      keep.onclick = () => this.keep(file, row);
      row.appendChild(keep);
    } else if (file.state === "kept") {
      row.insertAdjacentHTML("beforeend", `<span class="mhmp-tag mhmp-perm">✓ kept</span>`);
    } else if (file.state === "permanent") {
      row.insertAdjacentHTML("beforeend", `<span class="mhmp-tag mhmp-perm">✓ installed</span>`);
    }

    this.rows.set(file.key, row);
    const live = this.progress.get(file.key);
    if (live) this.showProgress(file.key, live.copied, live.total);
    return row;
  }

  async keep(file, row) {
    const ok = await app.extensionManager.dialog.confirm({
      title: "Keep this model?",
      message: `"${file.name}" will stop being cleaned up automatically and stay until you `
             + `delete it yourself.`,
    });
    if (!ok) return;
    try {
      await call("/keep", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: file.key, kept: true }),
      });
      toast("success", "Kept", file.name);
      this.load(this.path);
    } catch (err) {
      toast("error", "Could not keep it", err.message);
    }
  }

  async pull() {
    const items = [...this.selected].map((path) => ({ path }));
    if (!items.length) return;
    this.pullButton.disabled = true;
    try {
      const result = await call("/pull", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      });
      this.selected.clear();
      toast("info", "Copying", `${result.queued.length} model(s) queued.`);
      this.load(this.path);
    } catch (err) {
      toast("error", "Could not start the copy", err.message);
      this.pullButton.disabled = false;
    }
  }

  showProgress(key, copied, total) {
    const row = this.rows.get(key);
    if (!row) return;
    let track = row.querySelector(".mhmp-track");
    if (!track) {
      row.querySelector(".mhmp-size")?.remove();
      track = document.createElement("div");
      track.className = "mhmp-track";
      track.innerHTML = `<div class="mhmp-bar" style="width:0%"></div>`;
      row.appendChild(track);
      const label = document.createElement("span");
      label.className = "mhmp-size mhmp-pct";
      row.appendChild(label);
    }
    const pct = total ? Math.round((copied / total) * 100) : 0;
    track.querySelector(".mhmp-bar").style.width = `${pct}%`;
    const label = row.querySelector(".mhmp-pct");
    if (label) label.textContent = `${pct}% · ${fmtSize(copied)} / ${fmtSize(total)}`;
  }

  updateFooter() {
    const n = this.selected.size;
    this.pullButton.disabled = n === 0;
    this.pullButton.textContent = n ? `Pull ${n} model${n > 1 ? "s" : ""}` : "Pull selected";
    this.info.textContent = n ? `${n} selected` : "";
  }
}

let activeBrowser = null;

const openBrowser = async () => {
  if (activeBrowser) return;
  activeBrowser = new ModelBrowser();
  try {
    await activeBrowser.open();
  } catch (err) {
    toast("error", "Model browser failed", err.message);
    activeBrowser = null;
  }
};



// ------------------------------------------------------------------ transfer panel

// Copies are started from two different dialogs and outlive both, so progress and cancelling
// live in their own floating panel rather than inside whichever dialog happened to start them.
const transfers = {
  rows: new Map(),

  panel() {
    if (this.el) return this.el;
    injectStyles();
    this.el = document.createElement("div");
    this.el.className = "mhmp-xfers";
    this.el.innerHTML = `<h4><span>Copying models</span>
      <button class="mhmp-all">Cancel all</button></h4><div class="mhmp-body"></div>`;
    this.el.querySelector(".mhmp-all").onclick = () => this.cancel();
    this.body = this.el.querySelector(".mhmp-body");
    document.body.appendChild(this.el);
    return this.el;
  },

  async cancel(key) {
    try {
      await call("/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(key ? { key } : {}),
      });
    } catch (err) {
      toast("error", "Could not cancel", err.message);
    }
  },

  start(key, path, total) {
    this.panel();
    const row = document.createElement("div");
    row.className = "mhmp-xfer";
    row.innerHTML = `<div class="mhmp-xname"><span></span><button>Cancel</button></div>
      <div class="mhmp-xbar"><div class="mhmp-xfill"></div></div>
      <div class="mhmp-xpct">waiting…</div>`;
    row.querySelector("span").textContent = path;
    row.querySelector("span").title = path;
    row.querySelector("button").onclick = () => this.cancel(key);
    this.body.appendChild(row);
    this.rows.set(key, row);
  },

  progress(key, copied, total) {
    const row = this.rows.get(key);
    if (!row) return this.start(key, key, total);
    const pct = total ? Math.round((copied / total) * 100) : 0;
    row.querySelector(".mhmp-xfill").style.width = `${pct}%`;
    row.querySelector(".mhmp-xpct").textContent =
      `${pct}% · ${fmtSize(copied)} / ${fmtSize(total)}`;
  },

  finish(key) {
    this.rows.get(key)?.remove();
    this.rows.delete(key);
    if (this.rows.size === 0) { this.el?.remove(); this.el = null; }
  },
};

// ------------------------------------------------------------------- missing models

/** Every combo widget in the open graph whose value is not one of its own options. */
const findUnsatisfied = () => {
  const out = [];
  for (const node of app.graph?.nodes ?? []) {
    for (const widget of node.widgets ?? []) {
      const options = widget.options?.values;
      if (!Array.isArray(options) || !options.length) continue;
      const value = widget.value;
      if (typeof value !== "string" || !value) continue;
      if (options.includes(value)) continue;
      out.push({ node_type: node.comfyClass ?? node.type, input_name: widget.name, value,
                 nodeId: node.id });
    }
  }
  return out;
};

const pullMissing = async () => {
  injectStyles();
  const unsatisfied = findUnsatisfied();
  if (!unsatisfied.length) {
    toast("success", "Nothing missing", "Every model this workflow needs is already here.");
    return;
  }

  let data;
  try {
    data = await call("/missing", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: unsatisfied }),
    });
  } catch (err) {
    toast("error", "Could not check the server", err.message);
    return;
  }

  if (!data.server_ok) {
    toast("warn", "Server path not set",
      "Set it in Settings → MHNodes, under Model Puller.", 6000);
    return;
  }

  const dialog = new MissingDialog(data.items);
  dialog.render();
};

class MissingDialog {
  constructor(items) {
    this.items = items;
    this.selected = new Set(items.filter((i) => i.available).map((i) => i.path));
  }

  render() {
    this.backdrop = document.createElement("div");
    this.backdrop.className = "mhmp-backdrop";
    this.backdrop.innerHTML = `
      <div class="mhmp" role="dialog" aria-label="Missing models">
        <header>
          <h3>Missing models</h3>
          <button class="mhmp-close" aria-label="Close">&times;</button>
        </header>
        <div class="mhmp-list"></div>
        <footer>
          <span class="mhmp-info"></span>
          <button class="mhmp-primary">Pull all available</button>
        </footer>
      </div>`;
    this.list = this.backdrop.querySelector(".mhmp-list");
    this.info = this.backdrop.querySelector(".mhmp-info");
    this.button = this.backdrop.querySelector(".mhmp-primary");

    this.backdrop.querySelector(".mhmp-close").onclick = () => this.close();
    this.backdrop.onclick = (e) => { if (e.target === this.backdrop) this.close(); };
    this.onKey = (e) => { if (e.key === "Escape") this.close(); };
    document.addEventListener("keydown", this.onKey);
    this.button.onclick = () => this.pull();

    for (const item of this.items) this.list.appendChild(this.makeRow(item));
    this.update();
    document.body.appendChild(this.backdrop);
  }

  makeRow(item) {
    const row = document.createElement("div");
    row.className = "mhmp-row";

    const box = document.createElement("input");
    box.type = "checkbox";
    box.disabled = !item.available;
    box.checked = item.available;
    box.onchange = () => {
      box.checked ? this.selected.add(item.path) : this.selected.delete(item.path);
      this.update();
    };
    row.appendChild(box);

    const name = document.createElement("span");
    name.className = "mhmp-name";
    name.textContent = item.value;
    name.title = `${item.node_type}.${item.input_name}`;
    row.appendChild(name);

    if (item.available) {
      const size = document.createElement("span");
      size.className = "mhmp-size";
      size.textContent = fmtSize(item.size);
      row.appendChild(size);
      // A folder worked out from the node's spelling rather than from the folder's
      // contents is shown differently, so a wrong guess is caught before the copy starts.
      const tag = document.createElement("span");
      tag.className = `mhmp-tag ${item.guessed ? "mhmp-soon" : "mhmp-have"}`;
      tag.textContent = item.guessed ? `${item.folder_type} ?` : item.folder_type;
      if (item.guessed) {
        tag.title = `This folder is empty, so it was worked out from the node name. `
                  + `Check it is right before pulling.`;
      }
      row.appendChild(tag);
    } else {
      const why = document.createElement("span");
      why.className = "mhmp-size";
      why.textContent = item.reason ?? "unavailable";
      row.appendChild(why);
    }
    return row;
  }

  async pull() {
    const items = [...this.selected].map((path) => ({ path }));
    if (!items.length) return this.close();
    this.button.disabled = true;
    try {
      const result = await call("/pull", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      });
      toast("info", "Copying",
        `${result.queued.length} model(s) queued. Re-run the workflow once they finish.`);
      this.close();
    } catch (err) {
      toast("error", "Could not start the copy", err.message);
      this.button.disabled = false;
    }
  }

  update() {
    const n = this.selected.size;
    const blocked = this.items.filter((i) => !i.available).length;
    this.button.disabled = n === 0;
    this.button.textContent = n ? `Pull ${n} model${n > 1 ? "s" : ""}` : "Nothing to pull";
    this.info.textContent = blocked
      ? `${n} available, ${blocked} not on the server`
      : `${n} available`;
  }

  close() {
    document.removeEventListener("keydown", this.onKey);
    this.backdrop?.remove();
  }
}

// ---------------------------------------------------------------------------- extension

app.registerExtension({
  name: "MHNodes.ModelPuller",

  settings: [
    {
      id: S("ServerPath"), category: ["MHNodes", "Model Puller", "Server path"],
      name: "Server model path",
      tooltip: "Root of the shared model store, laid out like ComfyUI's models/ folder. "
             + "A UNC path such as \\\\server\\models works.",
      type: "text", defaultValue: "",
    },
    {
      id: S("LocalPath"), category: ["MHNodes", "Model Puller", "Local path"],
      name: "Preferred destination root",
      tooltip: "Optional. Models are always written into a folder ComfyUI already searches "
             + "(from extra_model_paths.yaml). When a model type has several registered "
             + "folders, this picks which one wins; leave blank to use ComfyUI's default.",
      type: "text", defaultValue: "",
    },
    {
      id: S("PurgeDays"), category: ["MHNodes", "Model Puller", "Purge after"],
      name: "Delete after this many days unused",
      tooltip: "Checked at startup. Only models pulled by this tool are ever deleted.",
      type: "slider", attrs: { min: 1, max: 90, step: 1 }, defaultValue: 7,
    },
    {
      id: S("Enabled"), category: ["MHNodes", "Model Puller", "Enabled"],
      name: "Enable automatic cleanup",
      tooltip: "Turn off to keep pulling models but never delete them.",
      type: "boolean", defaultValue: true,
    },
    {
      id: S("TrackUsage"), category: ["MHNodes", "Model Puller", "Track usage"],
      name: "Track model usage",
      tooltip: "Records when a workflow last used each pulled model, so that models you "
             + "actually use are not deleted. Takes effect after a restart.",
      type: "boolean", defaultValue: true,
    },
  ],

  commands: [
    {
      id: "MHNodes.ModelPuller.browse",
      label: "Pull models from server…",
      icon: "pi pi-cloud-download",
      function: openBrowser,
    },
    {
      id: "MHNodes.ModelPuller.missing",
      label: "Pull missing models for this workflow",
      icon: "pi pi-download",
      function: pullMissing,
    },
  ],

  menuCommands: [{
    path: ["MHNodes"],
    commands: ["MHNodes.ModelPuller.browse", "MHNodes.ModelPuller.missing"],
  }],

  getCanvasMenuItems() {
    return [
      { content: "Pull models from server…", callback: openBrowser },
      { content: "Pull missing models for this workflow", callback: pullMissing },
    ];
  },

  async setup() {
    const on = (event, handler) =>
      api.addEventListener(`mhnodes.model_puller.${event}`, ({ detail }) => handler(detail));

    on("start", (d) => {
      transfers.start(d.key, d.path, d.total);
      activeBrowser?.progress.set(d.key, { copied: 0, total: d.total });
    });
    on("progress", (d) => {
      transfers.progress(d.key, d.copied, d.total);
      activeBrowser?.progress.set(d.key, { copied: d.copied, total: d.total });
      activeBrowser?.showProgress(d.key, d.copied, d.total);
    });
    on("done", (d) => {
      transfers.finish(d.key);
      activeBrowser?.progress.delete(d.key);
      toast("success", "Model ready", d.path);
      if (activeBrowser) activeBrowser.load(activeBrowser.path);
    });
    on("cancelled", (d) => {
      transfers.finish(d.key);
      activeBrowser?.progress.delete(d.key);
      toast("info", "Cancelled", `${d.path} — nothing was left on disk.`);
      if (activeBrowser) activeBrowser.load(activeBrowser.path);
    });
    on("error", (d) => {
      transfers.finish(d.key);
      activeBrowser?.progress.delete(d.key);
      toast("error", `Could not pull ${d.path}`, d.error, 8000);
      if (activeBrowser) activeBrowser.load(activeBrowser.path);
    });
  },
});
