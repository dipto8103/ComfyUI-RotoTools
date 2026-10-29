// ComfyUI-RotoTools: Roto Review player. Based on ComfyUI-KM-VideoReview (web/js/videoReview.js)
// by Kasun Malinda, https://github.com/KasunMalinda/ComfyUI-KM-VideoReview
// MIT License, Copyright (c) 2026 Kasun Malinda (full text in LICENSE-KM-VideoReview).
// RotoTools changes: registered for the RotoReview node (paths and names adjusted), plus the review
// history (newest run of the session at the end of the strip) and room for the roto / history rows.
//
// VideoReview — extension registration and node/widget glue.
import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { VideoReviewPlayer } from "./roto_review_player.js";

const CONTROLS_H = 40;
const INFO_HEADER_H = 26; // collapsed info section (header only)
const ROTO_ROWS_H = 32 + 70; // RotoTools: roto/download row + history strip
const MIN_WIDTH = 320;

// Resize the node so the viewport matches the loaded footage aspect while
// keeping the user's chosen width.
function fitNodeToAspect(node, player) {
  const widget = node.widgets?.find((w) => w.name === "vr_player");
  const topY = widget?.y || 142; // y of the player widget inside the node
  const width = Math.max(node.size[0], MIN_WIDTH);
  node.setSize([
    width,
    topY + Math.round(width * player.aspect) + CONTROLS_H + INFO_HEADER_H + ROTO_ROWS_H + 8,
  ]);
  app.graph.setDirtyCanvas(true, true);
}

// After a page reload app.nodeOutputs is empty, but the server's history still
// has this node's last outputs and the temp frames still exist — restore from
// there so a reload doesn't force a re-run.
async function restoreFromHistory(node, player) {
  try {
    const res = await api.fetchApi("/history?max_items=64");
    const history = await res.json();
    const entries = Object.values(history).sort(
      (x, y) => (y.prompt?.[0] ?? 0) - (x.prompt?.[0] ?? 0) // newest first
    );
    const id = String(node.id);
    for (const entry of entries) {
      const out = entry.outputs?.[id];
      if (out?.a_frames?.length && entry.prompt?.[2]?.[id]?.class_type === "RotoReview") {
        player.load(out);
        fitNodeToAspect(node, player);
        return;
      }
    }
  } catch (e) {
    console.warn("[videoreview] history restore failed", e);
  }
}

function chain(proto, name, fn) {
  const orig = proto[name];
  proto[name] = function (...args) {
    const r = orig?.apply(this, args);
    fn.apply(this, args);
    return r;
  };
}

// RotoTools: the shots reviewed in this ComfyUI session (kept by the server, survives a page reload).
async function refreshHistory(player) {
  try {
    const res = await api.fetchApi("/rototools/review/history");
    if (res.ok) player.setHistory((await res.json()).runs || []);
  } catch (e) {
    console.warn("[RotoReview] history unavailable", e);
  }
}

app.registerExtension({
  name: "rototools.rotoreview.player",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "RotoReview") return;

    chain(nodeType.prototype, "onNodeCreated", function () {
      const player = new VideoReviewPlayer(this, api);
      this.vrPlayer = player;
      this.addDOMWidget("vr_player", "VR_PLAYER", player.rootEl, {
        serialize: false, // frames belong to an execution, never to workflow JSON
        hideOnZoom: false,
        // Sizing contract of the current frontend (DOMWidgetImpl.computeLayoutSize):
        // the widget fills the node's remaining height, clamped by getMinHeight.
        // Overriding widget.computeSize instead collapses the host to 0px.
        getMinHeight: () => 220,
      });
      // Default a freshly created node wide/tall enough to show the transport
      // controls. Restored nodes get their saved size from configure() afterward.
      this.setSize([Math.max(this.size[0], 480), Math.max(this.size[1], 400)]);
      // Restore the preview after a page reload within the same server session.
      requestAnimationFrame(() => {
        const cached = app.nodeOutputs?.[String(this.id)];
        if (cached?.a_frames?.length) {
          player.load(cached);
          fitNodeToAspect(this, player);
        } else {
          restoreFromHistory(this, player);
        }
        refreshHistory(player);
      });
    });

    chain(nodeType.prototype, "onExecuted", function (message) {
      if (!message?.a_frames) return;
      this.vrPlayer?.load(message);
      fitNodeToAspect(this, this.vrPlayer);
      if (this.vrPlayer) refreshHistory(this.vrPlayer);
    });

    chain(nodeType.prototype, "onRemoved", function () {
      this.vrPlayer?.destroy();
    });
  },
});
