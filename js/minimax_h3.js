import { app } from "../../scripts/app.js";

const fields = ["width", "height", "frames", "seconds"];

app.registerExtension({
  name: "MHNodes.MiniMaxH3LatentInfo",

  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "MH_MiniMaxH3LatentInfo") return;

    const onExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (message) {
      const result = onExecuted?.apply(this, arguments);
      for (const field of fields) {
        const output = this.outputs?.find((slot) => slot.name === field);
        const values = message?.[field];
        const value = Array.isArray(values) ? values.at(-1) : values;
        if (!output || !Number.isFinite(value)) continue;
        const display = field === "seconds" ? Number(value.toFixed(3)) : value;
        output.label = `${display} ${field}`;
      }
      this.setDirtyCanvas(true, true);
      return result;
    };

    const onConnectionsChange = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function (type, index) {
      const result = onConnectionsChange?.apply(this, arguments);
      if (type === 1 && index === 0) {
        for (const output of this.outputs ?? []) {
          if (fields.includes(output.name)) output.label = output.name;
        }
        this.setDirtyCanvas(true, true);
      }
      return result;
    };
  },
});
