// ComfyUI-RotoTools: preview grid on "Load Video Batch (Folders)".
// Shows every detected video as a thumbnail (grouped per input folder). Hover = play, click = full view (x to close).
// The grid fills the node, so resizing the node resizes the preview; the slider sets the tile size.
import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const NODE = "LoadVideoBatchFolders";
const WATCH = ["batch_folder", "output_folder", "extensions", "recursive"];

const CSS = `
.rtb { display:flex; flex-direction:column; width:100%; height:100%; box-sizing:border-box; position:relative;
       font:12px sans-serif; color:#ddd; background:#1b1b1b; border-radius:6px; overflow:hidden; }
.rtb-bar { display:flex; align-items:center; gap:8px; padding:4px 6px; background:#252525; flex:0 0 auto; }
.rtb-bar .rtb-info { flex:1 1 auto; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.rtb-bar button { background:#383838; color:#ddd; border:1px solid #555; border-radius:4px; cursor:pointer; padding:1px 8px; }
.rtb-bar input[type=range] { width:90px; }
.rtb-bar .rtb-add { background:#2d5a8a; border-color:#4a7fb5; font-weight:bold; }
.rtb-bar button:disabled { opacity:.6; cursor:wait; }
.rtb-group .rtb-rm { float:right; background:#5a2d2d; color:#fbb; border:1px solid #844; border-radius:4px;
                     cursor:pointer; padding:0 6px; margin-left:8px; }
.rtb-scroll { flex:1 1 auto; overflow-y:auto; overflow-x:hidden; padding:6px; }
.rtb-group { grid-column:1/-1; padding:6px 2px 2px; color:#9cf; border-bottom:1px solid #333; }
.rtb-group small { color:#999; display:block; word-break:break-all; }
.rtb-grid { display:grid; gap:6px; }
.rtb-tile { position:relative; aspect-ratio:16/9; background:#000; border:2px solid transparent; border-radius:4px;
            overflow:hidden; cursor:pointer; }
.rtb-tile:hover { border-color:#6af; }
.rtb-tile.cur { border-color:#fc3; }
.rtb-tile img, .rtb-tile video { width:100%; height:100%; object-fit:contain; display:block; }
.rtb-tile .rtb-lbl { position:absolute; left:0; right:0; bottom:0; padding:1px 4px; background:rgba(0,0,0,.65);
                     white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-size:11px; }
.rtb-tile .rtb-done { position:absolute; top:2px; right:4px; color:#5d5; font-weight:bold; text-shadow:0 0 3px #000; }
.rtb-full { position:absolute; inset:0; background:#000; display:flex; flex-direction:column; z-index:2; }
.rtb-full video { flex:1 1 auto; width:100%; min-height:0; object-fit:contain; background:#000; }
.rtb-full .rtb-ftitle { padding:4px 34px 4px 8px; background:#252525; word-break:break-all; }
.rtb-full .rtb-x { position:absolute; top:2px; right:4px; width:26px; height:24px; font-size:16px; line-height:20px;
                   background:#a33; color:#fff; border:none; border-radius:4px; cursor:pointer; }
.rtb-msg { padding:10px; color:#aaa; }
.rtb-err { color:#f88; }
`;

function addCss() {
    if (document.getElementById("rototools-batch-css")) return;
    const s = document.createElement("style");
    s.id = "rototools-batch-css";
    s.textContent = CSS;
    document.head.appendChild(s);
}

function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
}

// value of an input: the widget itself, or (when converted to an input and linked) the source node's widget
function inputValue(node, name) {
    const w = node.widgets?.find((x) => x.name === name);
    const inp = node.inputs?.find((x) => x.name === name);
    if (inp?.link != null) {
        const link = app.graph.links?.[inp.link] ?? app.graph.links?.get?.(inp.link);
        const src = link && app.graph.getNodeById(link.origin_id);
        const sw = src?.widgets?.[0];
        if (sw) return sw.value;
    }
    return w ? w.value : "";
}

const media = (kind, path) => api.apiURL(`/rototools/batch/${kind}?path=${encodeURIComponent(path)}`);

function setupNode(node) {
    addCss();
    const root = el("div", "rtb");
    const bar = el("div", "rtb-bar");
    const info = el("span", "rtb-info", "No folder yet");
    const add = el("button", "rtb-add", "+ Add folders…");
    add.title = "Pick one or more folders (Ctrl / Shift click). Open it again to add folders from another drive.";
    const clear = el("button", null, "Clear");
    clear.title = "Remove all folders from the list";
    const refresh = el("button", null, "Refresh");
    const size = el("input");
    size.type = "range";
    size.min = 60;
    size.max = 480;
    size.value = node.properties?.rototools_tile || 150;
    size.title = "Preview size";
    bar.append(add, info, size, clear, refresh);
    const scroll = el("div", "rtb-scroll");
    const grid = el("div", "rtb-grid");
    scroll.appendChild(grid);
    root.append(bar, scroll);

    const state = { data: null, sig: "", tiles: [], current: -1, timer: null, seq: 0 };

    const applySize = () => {
        grid.style.gridTemplateColumns = `repeat(auto-fill, minmax(${size.value}px, 1fr))`;
        node.properties = node.properties || {};
        node.properties.rototools_tile = Number(size.value);
    };
    size.addEventListener("input", applySize);
    applySize();

    function closeFull() {
        root.querySelector(".rtb-full")?.remove();
    }

    function openFull(it, g) {
        closeFull();
        const full = el("div", "rtb-full");
        const title = el("div", "rtb-ftitle", `#${it.i + 1}  ${g.label} \\ ${it.rel}   (${it.path})`);
        const v = el("video");
        v.src = media("video", it.path);
        v.controls = true;
        v.autoplay = true;
        v.loop = true;
        v.muted = true;
        const x = el("button", "rtb-x", "✕");
        x.title = "Close (back to the grid)";
        x.addEventListener("click", (e) => { e.stopPropagation(); v.pause(); v.removeAttribute("src"); full.remove(); });
        full.append(title, v, x);
        root.appendChild(full);
    }

    function tile(it, g) {
        const t = el("div", "rtb-tile");
        t.title = `#${it.i + 1}  ${g.label} \\ ${it.rel}\nzip: ${g.out}\\${it.name}.zip`;
        const img = el("img");
        img.loading = "lazy";
        img.src = media("thumb", it.path);
        img.onerror = () => { img.style.visibility = "hidden"; };
        const lbl = el("div", "rtb-lbl", `${it.i + 1}  ${it.name}`);
        const done = el("span", "rtb-done", it.done ? "✓" : "");
        done.title = "zip already exists (will be skipped)";
        t.append(img, lbl, done);
        let vid = null;
        t.addEventListener("mouseenter", () => {
            vid = el("video");
            vid.src = media("video", it.path);
            vid.muted = true;
            vid.loop = true;
            vid.autoplay = true;
            vid.playsInline = true;
            vid.style.position = "absolute";
            vid.style.inset = "0";
            t.insertBefore(vid, lbl);
        });
        t.addEventListener("mouseleave", () => {
            if (vid) { vid.pause(); vid.removeAttribute("src"); vid.load(); vid.remove(); vid = null; }
        });
        t.addEventListener("click", () => openFull(it, g));
        t._done = done;
        return t;
    }

    function markCurrent(i) {
        state.current = i;
        state.tiles.forEach((t, k) => t.classList.toggle("cur", k === i));
    }

    function render(data) {
        const sig = JSON.stringify([data.groups.map((g) => [g.label, g.root, g.out]), data.items.map((i) => i.path)]);
        state.data = data;
        const doneCount = data.items.filter((i) => i.done).length;
        info.textContent = `${data.total} videos in ${data.groups.length} folder(s)` +
            (doneCount ? `, ${doneCount} done (✓ skipped)` : "") + "  — set Run batch count to " + data.total;
        if (sig === state.sig) {  // same list: only refresh the done marks
            data.items.forEach((it, k) => { if (state.tiles[k]) state.tiles[k]._done.textContent = it.done ? "✓" : ""; });
            return;
        }
        state.sig = sig;
        closeFull();
        grid.textContent = "";
        state.tiles = [];
        for (const e of data.errors) grid.appendChild(el("div", "rtb-group rtb-err", e));
        if (!data.total && !data.errors.length) grid.appendChild(el("div", "rtb-group", "No videos found."));
        data.groups.forEach((g, gi) => {
            const h = el("div", "rtb-group");
            const rm = el("button", "rtb-rm", "✕ remove");
            rm.title = "Take this folder out of the batch (nothing is deleted on disk)";
            rm.addEventListener("click", () => removeFolder(g.key));
            h.append(rm, `${g.label}  (${g.count} videos)  → ${g.out}`, el("small", null, g.root));
            grid.appendChild(h);
            for (const it of data.items) {
                if (it.group !== gi) continue;
                const t = tile(it, g);
                state.tiles[it.i] = t;
                grid.appendChild(t);
            }
        });
        markCurrent(state.current);
    }

    async function scan() {
        const folders = String(inputValue(node, "batch_folder") || "").trim();
        if (!folders) {
            state.sig = "";
            grid.textContent = "";
            info.textContent = "Type or paste one or more folders (comma separated) in batch_folder";
            return;
        }
        const seq = ++state.seq;
        info.textContent = "Scanning…";
        const q = new URLSearchParams({
            folders,
            output_folder: String(inputValue(node, "output_folder") || ""),
            extensions: String(inputValue(node, "extensions") || ""),
            recursive: inputValue(node, "recursive") === false ? "0" : "1",
        });
        try {
            const r = await api.fetchApi(`/rototools/batch/scan?${q}`);
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data = await r.json();
            if (seq === state.seq) render(data);
        } catch (e) {
            if (seq === state.seq) info.textContent = "Scan failed: " + e.message;
        }
    }
    const scanSoon = (ms = 500) => { clearTimeout(state.timer); state.timer = setTimeout(scan, ms); };
    refresh.addEventListener("click", () => { state.sig = ""; scan(); });

    function setFolders(text) {
        const w = node.widgets?.find((x) => x.name === "batch_folder");
        if (!w) return;
        w.value = text;
        node.graph?.setDirtyCanvas?.(true, true);
        scanSoon(50);
    }

    function removeFolder(key) {
        const left = (state.data?.folders ?? []).filter((f) => f.key !== key).map((f) => f.path);
        setFolders(left.join("\n"));
    }

    clear.addEventListener("click", () => {
        if (!String(inputValue(node, "batch_folder") || "").trim()) return;
        if (confirm("Remove all folders from this batch? (Nothing is deleted on disk.)")) setFolders("");
    });

    add.addEventListener("click", async () => {
        const current = String(inputValue(node, "batch_folder") || "");
        const last = state.data?.folders?.at(-1)?.path ?? "";
        add.disabled = true;
        const label = add.textContent;
        add.textContent = "Dialog open on the ComfyUI PC…";
        try {
            const r = await api.fetchApi("/rototools/batch/pick", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ current, start: last }),
            });
            const data = await r.json();
            if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
            if (data.picked.length) setFolders(data.text);
        } catch (e) {
            alert("Add folders: " + e.message);
        } finally {
            add.disabled = false;
            add.textContent = label;
        }
    });

    for (const name of WATCH) {
        const w = node.widgets?.find((x) => x.name === name);
        if (!w) continue;
        const cb = w.callback;
        w.callback = function () { const r = cb?.apply(this, arguments); scanSoon(); return r; };
    }

    const widget = node.addDOMWidget("video_batch_preview", "rototools_preview", root, {
        serialize: false,
        hideOnZoom: false,
        getMinHeight: () => 220,
    });
    widget.serialize = false;

    node.rototools = { scan, scanSoon, markCurrent, state };
    const s = node.size;
    node.setSize([Math.max(s[0], 560), Math.max(s[1], 640)]);
}

app.registerExtension({
    name: "rototools.VideoBatchPreview",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE) return;
        const onCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onCreated?.apply(this, arguments);
            setupNode(this);
            this.rototools.scanSoon(300);
            return r;
        };
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = onConfigure?.apply(this, arguments);
            this.rototools?.scanSoon(300);  // values from the saved workflow are in place now
            return r;
        };
        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            const r = onConnectionsChange?.apply(this, arguments);
            this.rototools?.scanSoon();
            return r;
        };
        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (msg) {
            const r = onExecuted?.apply(this, arguments);
            const i = msg?.rototools_index?.[0];
            if (i != null) this.rototools?.markCurrent(i);
            return r;
        };
    },
    setup() {
        // after each finished run, refresh the done marks (zips written by the saver)
        api.addEventListener("execution_success", () => {
            for (const n of app.graph?._nodes ?? []) if (n.type === NODE) n.rototools?.scanSoon(800);
        });
    },
});
