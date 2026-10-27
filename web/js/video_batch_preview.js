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
.rtb.rtb-drop { outline:3px dashed #6af; outline-offset:-3px; }
.rtb-tile .rtb-tx { position:absolute; top:2px; left:2px; width:20px; height:18px; padding:0; font-size:11px;
                    background:rgba(90,45,45,.85); color:#fbb; border:1px solid #844; border-radius:3px; cursor:pointer;
                    display:none; }
.rtb-tile:hover .rtb-tx { display:block; }
.rtb-tile.ex img, .rtb-tile.ex .rtb-lbl { opacity:.25; filter:grayscale(1); }
.rtb-tile.ex .rtb-tx { display:none !important; }
.rtb-tile .rtb-undo { position:absolute; inset:auto 0 18px 0; margin:auto; width:72px; height:20px; padding:0;
                      font-size:11px; background:#2d5a8a; color:#fff; border:1px solid #4a7fb5; border-radius:3px;
                      cursor:pointer; display:none; }
.rtb-tile.ex .rtb-undo { display:block; top:0; bottom:0; }
.rtb-group .rtb-rm { float:right; background:#5a2d2d; color:#fbb; border:1px solid #844; border-radius:4px;
                     cursor:pointer; padding:0 6px; margin-left:8px; }
.rtb-status { flex:0 0 auto; padding:2px 8px; background:#202a33; color:#fc3; font-size:11px;
              white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
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

// Set the index widget so the NEXT queued run loads video `value`. With ComfyUI's "control before generate"
// setting, the frontend adds 1 before every queue except the first one after the page loaded; it remembers that
// with a private symbol on the control widget (set after IS_CONTROL_WIDGET). Removing it makes the next queue
// use the value as it is, like the very first run.
function setIndex(node, value) {
    const idx = node.widgets?.find((x) => x.name === "index");
    if (!idx) return;
    idx.value = value;
    const mode = app.extensionManager?.setting?.get?.("Comfy.WidgetControlMode") ??
                 app.ui?.settings?.getSettingValue?.("Comfy.WidgetControlMode");
    if (mode === "before") {
        const ctl = node.widgets.find((x) => x !== idx && typeof x.beforeQueued === "function");
        const syms = ctl ? Object.getOwnPropertySymbols(ctl) : [];
        if (syms.length >= 2) delete ctl[syms[syms.length - 1]];
    }
    node.graph?.setDirtyCanvas?.(true, true);
}

// what the node does, in the browser console (F12), next to the [LoadVideoBatchFolders] lines in ComfyUI's console
const rlog = (...a) => console.info("[RotoTools]", ...a);

// comparable key of a listed path, close to Python's os.path.normcase on Windows
const pkey = (p) => String(p).trim().replace(/\//g, "\\").replace(/\\+$/, "").toLowerCase();

// entries of a batch_folder / excluded text, like batch.split_folders (lines, commas, "quoted" paths)
const parseList = (text) => [...String(text || "").matchAll(/"([^"]*)"|([^",\r\n]+)/g)]
    .map((m) => (m[1] ?? m[2]).trim()).filter(Boolean);

const media = (kind, path) => api.apiURL(`/rototools/batch/${kind}?path=${encodeURIComponent(path)}`);

function setupNode(node) {
    addCss();
    const root = el("div", "rtb");
    const bar = el("div", "rtb-bar");
    const info = el("span", "rtb-info", "No folder yet");
    const add = el("button", "rtb-add", "+ Add folders…");
    add.title = "Pick one or more folders (Ctrl / Shift click). Open it again to add folders from another drive.";
    const clear = el("button", null, "Clear");
    clear.title = "Remove all folders, videos and exclusions; the node is ready for new folders";
    const refresh = el("button", null, "Refresh");
    const size = el("input");
    size.type = "range";
    size.min = 60;
    size.max = 480;
    size.value = node.properties?.rototools_tile || 150;
    size.title = "Preview size";
    bar.append(add, info, size, clear, refresh);
    const status = el("div", "rtb-status");   // last run, one line (hidden until the node has run)
    status.hidden = true;
    const scroll = el("div", "rtb-scroll");
    const grid = el("div", "rtb-grid");
    scroll.appendChild(grid);
    root.append(bar, status, scroll);

    const state = { data: null, sig: "", tiles: [], current: -1, timer: null, seq: 0 };

    // ---- excluded videos: kept in the hidden "excluded" widget (one path per line), saved with the workflow
    const exW = node.widgets?.find((x) => x.name === "excluded");
    if (exW) {   // hidden on both the classic canvas and the "Nodes 2.0" renderer (which reads options.hidden)
        exW.hidden = true;
        exW.options = exW.options || {};
        exW.options.hidden = true;
        exW.computeSize = () => [0, -4];
    }
    const excludedSet = () => new Set(parseList(exW?.value).map(pkey));
    function setExcluded(paths) {
        if (!exW) return;
        exW.value = paths.join("\n");
        node.graph?.setDirtyCanvas?.(true, true);
    }
    function toggleExcluded(it) {
        const cur = parseList(exW?.value);
        const k = pkey(it.path);
        const on = !cur.some((p) => pkey(p) === k);
        setExcluded(on ? [...cur, it.path] : cur.filter((p) => pkey(p) !== k));
        rlog(on ? "excluded" : "included again", it.path);
        if (state.data) render(state.data, true);
    }

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
        const title = el("div", "rtb-ftitle", `#${it.i + 1}  ${g.label || "single video"} \\ ${it.rel}   (${it.path})`);
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
        t.title = `#${it.i + 1}  ${g.label || "single video"} \\ ${it.rel}\n${it.path}\nzip: ${g.out}\\${it.name}.zip`;
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
        const x = el("button", "rtb-tx", "✕");
        x.title = "Leave this video out of the batch (nothing is deleted on disk)";
        x.addEventListener("click", (e) => { e.stopPropagation(); toggleExcluded(it); });
        const undo = el("button", "rtb-undo", "↺ undo");
        undo.title = "Put this video back in the batch";
        undo.addEventListener("click", (e) => { e.stopPropagation(); toggleExcluded(it); });
        t.append(x, undo);
        t._done = done;
        t._key = pkey(it.path);
        return t;
    }

    function markCurrent(i, text) {
        state.current = i;
        state.tiles.forEach((t, k) => t.classList.toggle("cur", k === i));
        if (text) {
            status.textContent = "Last run: " + text;
            status.title = text;
            status.hidden = false;
        }
    }

    function render(data) {
        const sig = JSON.stringify([data.groups.map((g) => [g.label, g.root, g.out]), data.items.map((i) => i.path)]);
        state.data = data;
        const ex = excludedSet();
        const nEx = data.items.filter((i) => ex.has(pkey(i.path))).length;
        const doneCount = data.items.filter((i) => i.done && !ex.has(pkey(i.path))).length;
        const left = data.total - nEx - doneCount;
        const nFolders = data.groups.filter((g) => g.kind !== "files").length;
        const nSingles = data.groups.find((g) => g.kind === "files")?.count ?? 0;
        info.textContent = `${data.total} videos (${nFolders} folder(s)` + (nSingles ? `, ${nSingles} single` : "") + ")" +
            (doneCount ? `, ${doneCount} done` : "") + (nEx ? `, ${nEx} left out` : "") +
            `  — ${left} to do: set Run batch count to ${left}`;
        // A new or finished list starts again at index 0 (only matters with skip_if_zip_exists off: otherwise
        // every run takes the next video without a zip by itself). Not on the first scan after opening a workflow.
        const listChanged = state.sig !== "" && sig !== state.sig;
        const idx = node.widgets?.find((x) => x.name === "index");
        if (idx && idx.value !== 0 && (listChanged || (data.total > 0 && idx.value >= data.total))) setIndex(node, 0);
        if (sig === state.sig) {  // same list: only refresh the done and left-out marks
            data.items.forEach((it, k) => {
                const t = state.tiles[k];
                if (!t) return;
                t._done.textContent = it.done ? "✓" : "";
                t.classList.toggle("ex", ex.has(t._key));
            });
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
            if (g.kind === "files") {
                rm.textContent = "✕ remove all";
                rm.title = "Take all single videos out of the batch (nothing is deleted on disk)";
                rm.addEventListener("click", () => removeEntries(data.items.filter((i) => i.group === gi).map((i) => i.key)));
                h.append(rm, `Single videos  (${g.count})  → ${g.out}`,
                         el("small", null, "zips go straight into the save folder, named after each video"));
            } else {
                rm.title = "Take this folder out of the batch (nothing is deleted on disk)";
                rm.addEventListener("click", () => removeEntries([g.key]));
                h.append(rm, `${g.label}  (${g.count} videos)  → ${g.out}`, el("small", null, g.root));
            }
            grid.appendChild(h);
            for (const it of data.items) {
                if (it.group !== gi) continue;
                const t = tile(it, g);
                t.classList.toggle("ex", ex.has(t._key));
                state.tiles[it.i] = t;
                grid.appendChild(t);
            }
        });
        markCurrent(state.current);
    }

    async function scan() {
        const folders = String(inputValue(node, "batch_folder") || "").trim();
        const seq = ++state.seq;
        if (!folders) {
            if (state.sig !== "") setIndex(node, 0);   // emptied list: the next list starts at the first video
            // forget the old list completely, or videos dropped next would look "already listed"
            state.sig = "";
            state.data = null;
            state.tiles = [];
            closeFull();
            grid.textContent = "";
            info.textContent = "Add folders, drop videos here, or paste paths in batch_folder";
            return;
        }
        info.textContent = "Scanning…";
        const body = {
            folders,
            output_folder: String(inputValue(node, "output_folder") || ""),
            extensions: String(inputValue(node, "extensions") || ""),
            recursive: inputValue(node, "recursive") === false ? "0" : "1",
        };
        try {
            const r = await api.fetchApi("/rototools/batch/scan", {
                method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
            });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data = await r.json();
            if (seq !== state.seq) return;
            render(data);
            rlog(`scan: ${data.total} videos in ${data.groups.length} group(s)` +
                 (data.errors.length ? `, problems: ${data.errors.join(" | ")}` : ""));
        } catch (e) {
            console.error("[RotoTools] scan failed", e);
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

    function removeEntries(keys) {
        const drop = new Set(keys);
        const left = (state.data?.folders ?? []).filter((f) => !drop.has(f.key)).map((f) => f.path);
        rlog(`removed ${keys.length} entr${keys.length === 1 ? "y" : "ies"} from the list`);
        setFolders(left.join("\n"));
    }

    // ---- dropped videos: uploaded (copied) into ComfyUI's input folder, then listed by that path
    async function addDropped(dt) {
        const exts = String(inputValue(node, "extensions") || "mp4,mov,mkv,avi,webm,m4v")
            .split(",").map((e) => "." + e.trim().toLowerCase().replace(/^\./, "")).filter((e) => e.length > 1);
        const entries = [...(dt.items ?? [])].map((i) => i.webkitGetAsEntry?.()).filter(Boolean);
        const folders = entries.filter((e) => e.isDirectory).length;
        const files = [...(dt.files ?? [])].filter((f) => exts.some((e) => f.name.toLowerCase().endsWith(e)));
        if (!files.length) {
            alert(folders ? "Folders cannot be dropped (the browser does not tell ComfyUI where they are). " +
                            "Use + Add folders… instead." : "No video files in what was dropped (" + exts.join(" ") + ").");
            return;
        }
        const added = [];
        try {
            for (const [k, f] of files.entries()) {
                info.textContent = `Copying dropped video ${k + 1} / ${files.length} into ComfyUI: ${f.name}…`;
                const body = new FormData();
                body.append("file", f, f.name);
                const r = await api.fetchApi("/rototools/batch/upload", { method: "POST", body });
                const data = await r.json();
                if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
                added.push(data.path);
            }
        } catch (e) {
            alert("Dropping videos: " + e.message);
        } finally {
            if (added.length) {
                // compare with what is listed NOW (not the last scan, which can be from before Clear)
                const cur = String(inputValue(node, "batch_folder") || "").trim();
                const have = new Set(parseList(cur).map(pkey));
                const fresh = added.filter((p) => !have.has(pkey(p)));
                rlog(`dropped ${files.length} video(s): ${fresh.length} added` +
                     (added.length - fresh.length ? `, ${added.length - fresh.length} already in the list` : ""), fresh);
                setFolders([cur, ...fresh].filter(Boolean).join("\n"));
            } else {
                scanSoon(50);
            }
            if (folders) alert(`${folders} folder(s) were skipped: folders cannot be dropped, use + Add folders…`);
        }
    }
    const isFileDrag = (e) => [...(e.dataTransfer?.types ?? [])].includes("Files");
    root.addEventListener("dragover", (e) => {
        if (!isFileDrag(e)) return;
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = "copy";
        root.classList.add("rtb-drop");
    });
    root.addEventListener("dragleave", (e) => { if (!root.contains(e.relatedTarget)) root.classList.remove("rtb-drop"); });
    root.addEventListener("drop", (e) => {
        if (!isFileDrag(e)) return;
        e.preventDefault();
        e.stopPropagation();
        root.classList.remove("rtb-drop");
        addDropped(e.dataTransfer);
    });

    clear.addEventListener("click", () => {
        const listed = String(inputValue(node, "batch_folder") || "").trim() || String(exW?.value || "").trim();
        if (listed && !confirm("Remove all folders, videos and left-out marks from this batch? " +
                               "(Nothing is deleted on disk.)")) return;
        // back to an empty node: list, left-out videos, last-run line, index and the failed-video memory
        setExcluded([]);
        status.hidden = true;
        status.textContent = "";
        state.current = -1;
        setFolders("");
        api.fetchApi("/rototools/batch/reset", { method: "POST" }).catch(() => {});
        rlog("cleared: the node is empty and ready for new folders / videos");
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
            rlog(`folder dialog: ${data.picked.length} folder(s) picked`, data.picked);
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

    node.rototools = { scan, scanSoon, markCurrent, addDropped, isFileDrag, state };
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
        // videos dropped on the node itself (title, widgets), not only on the preview area
        const onDragOver = nodeType.prototype.onDragOver;
        nodeType.prototype.onDragOver = function (e) {
            return this.rototools?.isFileDrag(e) || onDragOver?.apply(this, arguments) || false;
        };
        const onDragDrop = nodeType.prototype.onDragDrop;
        nodeType.prototype.onDragDrop = function (e) {
            if (this.rototools?.isFileDrag(e)) {
                this.rototools.addDropped(e.dataTransfer);
                return true;
            }
            return onDragDrop?.apply(this, arguments) || false;
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
            if (i != null) this.rototools?.markCurrent(i, msg?.rototools_status?.[0]);
            if (msg?.rototools_status) rlog("run:", msg.rototools_status[0]);
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
