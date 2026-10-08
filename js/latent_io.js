import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Discarding lives in the node's context menu rather than in a node of its own, so that
// deleting files is always something you did on purpose -- never a side effect of running
// a workflow that happens to contain a "delete" node.

const toast = (severity, summary, detail, life = 4000) =>
  app.extensionManager.toast.add({ severity, summary, detail, life });

const refreshCombo = async (node) => {
  const widget = node.widgets?.find((w) => w.name === "preview");
  if (!widget) return;
  try {
    const response = await api.fetchApi("/mhnodes/latent_store/list");
    const { previews } = await response.json();
    widget.options.values = previews;
    if (!previews.includes(widget.value)) widget.value = previews[0] ?? "";
    app.graph.setDirtyCanvas(true, true);
  } catch {
    /* the dropdown repopulates on the next refresh anyway */
  }
};

const discard = async (node) => {
  const widget = node.widgets?.find((w) => w.name === "preview");
  const value = widget?.value;
  if (!value) {
    toast("warn", "Nothing selected", "Pick a saved latent first.");
    return;
  }

  const ok = await app.extensionManager.dialog.confirm({
    title: "Discard this latent?",
    message: `"${value}" and the latent saved beside it will be deleted from disk. `
           + `This cannot be undone.`,
  });
  if (!ok) return;

  try {
    const response = await api.fetchApi("/mhnodes/latent_store/discard", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: value }),
    });
    if (!response.ok) {
      let reason = response.statusText;
      try { reason = (await response.json()).error || reason; } catch { /* keep statusText */ }
      throw new Error(reason);
    }
    const { removed } = await response.json();
    toast("success", "Discarded", removed.join(", "));
    await refreshCombo(node);
  } catch (err) {
    toast("error", "Could not discard", err.message);
  }
};

app.registerExtension({
  name: "MHNodes.LatentStore",

  getNodeMenuItems(node) {
    if (node.comfyClass !== "MH_LoadLatentPreview") return [];
    return [
      { content: "Discard this latent and its preview", callback: () => discard(node) },
      { content: "Refresh list", callback: () => refreshCombo(node) },
    ];
  },
});
