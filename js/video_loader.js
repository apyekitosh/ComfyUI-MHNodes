import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// The loaders' preview plays only the frames that will load. Nothing is re-encoded when start,
// frame_cap or select_every_nth change: the browser plays the file itself and this only moves
// the points it loops between. The server is asked once per file, for the frame rate (browsers
// don't expose it) and, for formats a browser can't play, a small preview copy.
//
// The player is mounted with addDOMWidget and sized through computeLayoutSize, the way core's
// own video preview is, so the frontend lays it out. Drawing widgets by hand is what makes
// other packs' previews overflow their nodes.

// widget: the input naming the file or folder. source: how the server should read it.
const LOADERS = {
  MH_LoadVideoInput: { widget: "video", source: "input" },
  MH_LoadVideoPath: { widget: "path", source: "path" },
  MH_LoadImagesPath: { widget: "path", source: "folder" },
};
const RANGE_WIDGETS = ["start", "frame_cap", "select_every_nth"];
const MARGIN = 10;

const toast = (severity, summary, detail, life = 5000) =>
  app.extensionManager.toast.add({ severity, summary, detail, life });

const chain = (object, key, after) => {
  const before = object[key];
  object[key] = function (...args) {
    const result = before?.apply(this, args);
    after.apply(this, args);
    return result;
  };
};

const widgetValue = (node, name) => node.widgets?.find((w) => w.name === name)?.value;

function attachPreview(node, { widget: sourceName, source }) {
  const container = document.createElement("div");
  // The player never takes the mouse, so dragging, zooming and wheel over it reach the canvas.
  Object.assign(container.style, {
    position: "relative", width: "100%", height: "100%", pointerEvents: "none",
    display: "flex", alignItems: "center", justifyContent: "center",
  });

  const video = document.createElement("video");
  Object.assign(video, { muted: true, playsInline: true, autoplay: true, loop: false });
  Object.assign(video.style, { width: "100%", height: "100%", objectFit: "contain" });

  const label = document.createElement("div");
  Object.assign(label.style, {
    position: "absolute", left: "4px", bottom: "4px", padding: "1px 5px",
    font: "11px sans-serif", color: "#ddd", background: "rgba(0,0,0,0.55)", borderRadius: "3px",
  });
  container.append(video, label);

  const state = { info: null, aspect: 16 / 9, startTime: 0, endTime: Infinity, request: 0 };

  const widget = node.addDOMWidget("mh_video_preview", "video", container, {
    serialize: false,
    hideOnZoom: false,
  });
  widget.serialize = false;
  // Recomputed on every layout, so the height follows the video's shape as the node is resized.
  widget.computeLayoutSize = () => ({
    minHeight: state.info ? Math.max(64, (node.size[0] - MARGIN * 2) / state.aspect) : 32,
    minWidth: 64,
  });

  const grow = () => {
    const needed = node.computeSize()[1];
    if (node.size[1] < needed) node.setSize([node.size[0], needed]);
    app.graph.setDirtyCanvas(true, true);
  };

  const setLabel = (text) => {
    label.textContent = text;
    label.style.display = text ? "" : "none";
  };

  // What will load, in source frames, and the stretch of the file that covers it.
  const updateRange = () => {
    const info = state.info;
    if (!info) return;
    const start = Math.max(0, Number(widgetValue(node, "start")) || 0);
    const cap = Math.max(0, Number(widgetValue(node, "frame_cap")) || 0);
    const nth = Math.max(1, Number(widgetValue(node, "select_every_nth")) || 1);

    if (start >= info.frames) {
      state.startTime = 0;
      state.endTime = Infinity;
      setLabel(`start ${start} is past the end (${info.frames} frames)`);
      return;
    }
    const available = Math.ceil((info.frames - start) / nth);
    const count = cap ? Math.min(cap, available) : available;
    const lastFrame = start + (count - 1) * nth;

    state.startTime = start / info.fps;
    state.endTime = (lastFrame + 1) / info.fps;
    // Every nth frame can't be shown exactly; playing n times faster shows its effect on motion.
    // A folder's preview copy is written at a fixed rate and sped up or slowed down to the
    // node's fps, so changing fps never rebuilds it.
    const fps = Number(widgetValue(node, "fps")) || info.fps;
    video.playbackRate = Math.min(Math.max((nth * fps) / info.fps, 0.0625), 16);

    const proxy = info.proxied && source !== "folder" ? " · preview copy" : "";
    setLabel(`${count} frames · ${start}–${lastFrame} of ${info.frames}${proxy}`);
    if (video.currentTime < state.startTime || video.currentTime >= state.endTime) {
      video.currentTime = state.startTime;
    }
  };

  const restart = () => {
    video.currentTime = state.startTime;
    video.play().catch(() => {});
  };

  // Loop the selected range. requestVideoFrameCallback fires once per painted frame, so the
  // jump back lands on the right frame; timeupdate (about 4 times a second) is the fallback.
  const halfFrame = () => (state.info ? 0.5 / state.info.fps : 0);
  if ("requestVideoFrameCallback" in HTMLVideoElement.prototype) {
    const onFrame = (_now, meta) => {
      if (meta.mediaTime >= state.endTime - halfFrame()) restart();
      video.requestVideoFrameCallback(onFrame);
    };
    video.requestVideoFrameCallback(onFrame);
  } else {
    video.addEventListener("timeupdate", () => {
      if (video.currentTime >= state.endTime) restart();
    });
  }
  video.addEventListener("ended", restart);
  video.addEventListener("loadedmetadata", () => {
    updateRange();
    restart();
  });
  video.addEventListener("error", () => {
    if (state.info) setLabel("this file can't be previewed");
  });

  const clear = (text = "") => {
    state.info = null;
    video.removeAttribute("src");
    video.load();
    setLabel(text);
    grow();
  };

  const load = async () => {
    const value = widgetValue(node, sourceName);
    const request = ++state.request;
    if (!value) return clear();

    const slow = setTimeout(() => {
      if (request === state.request) setLabel("preparing preview…");
    }, 400);
    try {
      const response = await api.fetchApi(
        "/mhnodes/video/info?" + new URLSearchParams({ source, file: value })
      );
      if (request !== state.request) return; // a newer choice won
      if (!response.ok) return clear(response.statusText || "can't read this video");

      const info = await response.json();
      state.info = info;
      state.aspect = info.width && info.height ? info.width / info.height : 16 / 9;
      video.src = api.apiURL(info.url);
      grow();
    } catch (error) {
      if (request === state.request) clear("can't read this video");
    } finally {
      clearTimeout(slow);
    }
  };

  let typing = null;
  const loadSoon = () => {
    clearTimeout(typing);
    typing = setTimeout(load, source === "input" ? 0 : 400);
  };

  for (const name of [sourceName, ...RANGE_WIDGETS, "fps"]) {
    const target = node.widgets?.find((w) => w.name === name);
    if (target) chain(target, "callback", name === sourceName ? loadSoon : updateRange);
  }
  // A saved workflow restores its values after the node is created.
  chain(node, "onConfigure", () => requestAnimationFrame(load));
  chain(node, "onRemoved", () => {
    state.request++;
    video.removeAttribute("src");
    video.load();
  });
  requestAnimationFrame(load);
}

// Upload for Load Video - Input: a button and drag & drop, through core's own upload endpoint,
// so uploads land in the input folder exactly as core's loaders put them there.
function attachUpload(node) {
  const combo = node.widgets?.find((w) => w.name === "video");
  if (!combo) return;

  const upload = async (file) => {
    const body = new FormData();
    body.append("image", file);
    try {
      const response = await api.fetchApi("/upload/image", { method: "POST", body });
      if (response.status === 413) {
        return toast("warn", "Too big to upload",
          `${file.name} is over the server's upload limit. Use Load Video - Path for it.`);
      }
      if (!response.ok) return toast("error", "Upload failed", response.statusText);
      const { name, subfolder } = await response.json();
      const value = subfolder ? `${subfolder}/${name}` : name;
      if (!combo.options.values.includes(value)) {
        combo.options.values = [...combo.options.values, value].sort();
      }
      combo.value = value;
      combo.callback?.(value);
    } catch (error) {
      toast("error", "Upload failed", String(error));
    }
  };

  const picker = document.createElement("input");
  Object.assign(picker, { type: "file", accept: "video/*,.mov,.mkv,.avi" });
  picker.style.display = "none";
  picker.onchange = () => {
    if (picker.files?.length) upload(picker.files[0]);
    picker.value = "";
  };
  document.body.append(picker);

  const button = node.addWidget("button", "choose video to upload", null, () => picker.click(),
    { serialize: false });
  button.serialize = false;
  // Sit right under the combo rather than at the bottom.
  node.widgets.splice(node.widgets.indexOf(button), 1);
  node.widgets.splice(node.widgets.indexOf(combo) + 1, 0, button);

  const isVideo = (file) => file && (file.type.startsWith("video/") ||
    /\.(mov|mkv|avi|mp4|webm|m4v)$/i.test(file.name));
  node.onDragOver = (event) => !!event?.dataTransfer?.types?.includes?.("Files");
  node.onDragDrop = (event) => {
    const file = [...(event.dataTransfer?.files ?? [])].find(isVideo);
    if (!file) return false;
    upload(file);
    return true;
  };
  chain(node, "onRemoved", () => picker.remove());
}

app.registerExtension({
  name: "MHNodes.VideoLoader",

  nodeCreated(node) {
    const loader = LOADERS[node.comfyClass];
    if (!loader) return;
    if (loader.source === "input") attachUpload(node);
    attachPreview(node, loader);
  },
});
