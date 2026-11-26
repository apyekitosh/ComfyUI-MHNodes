// Run with node; no packages or live ComfyUI server required.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

let extension;
const source = readFileSync(new URL("../js/minimax_h3.js", import.meta.url), "utf8")
  .replace(/^import \{ app \} from .*;\r?\n/, "");
new Function("app", source)({ registerExtension: (value) => { extension = value; } });

const unrelated = { prototype: {} };
extension.beforeRegisterNodeDef(unrelated, { name: "OtherNode" });
assert.deepEqual(unrelated.prototype, {});

let executions = 0;
let connections = 0;
let redraws = 0;
class InfoNode {
  onExecuted() { executions++; return "executed"; }
  onConnectionsChange() { connections++; return "connected"; }
  setDirtyCanvas() { redraws++; }
}
extension.beforeRegisterNodeDef(InfoNode, { name: "MH_MiniMaxH3LatentInfo" });
const node = new InfoNode();
node.outputs = ["latent", "width", "height", "frames", "seconds"]
  .map((name) => ({ name, type: name === "latent" ? "LATENT" : name === "seconds" ? "FLOAT" : "INT" }));

const message = { width: [864], height: [480], frames: [124], seconds: [124 / 24] };
assert.equal(node.onExecuted(message), "executed");
assert.deepEqual(node.outputs.slice(1).map((slot) => slot.label),
  ["864 width", "480 height", "124 frames", "5.167 seconds"]);
assert.deepEqual(node.outputs.map((slot) => slot.name), ["latent", "width", "height", "frames", "seconds"]);
assert.equal(node.outputs[0].label, undefined);
assert.equal(message.seconds[0], 124 / 24);

// List execution shows the last result. Missing UI fields leave valid labels intact.
node.onExecuted({ width: [864, 1344], seconds: [1, 2.25] });
assert.equal(node.outputs[1].label, "1344 width");
assert.equal(node.outputs[4].label, "2.25 seconds");
node.onExecuted({});
assert.equal(node.outputs[2].label, "480 height");

// Output connection changes must not erase the display; input changes clear stale values.
assert.equal(node.onConnectionsChange(2, 0), "connected");
assert.equal(node.outputs[1].label, "1344 width");
assert.equal(node.onConnectionsChange(1, 0), "connected");
assert.deepEqual(node.outputs.slice(1).map((slot) => slot.label), ["width", "height", "frames", "seconds"]);
assert.equal(executions, 3);
assert.equal(connections, 2);
assert.equal(redraws, 4);
console.log("H3 socket labels, callback chaining, list results and input resets passed.");
