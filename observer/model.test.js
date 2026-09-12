"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {
  buildFrames,
  changesBetween,
  displayValue,
  humanize,
  trainLeft,
} = require("./model.js");

const receipt = JSON.parse(
  fs.readFileSync(path.join(__dirname, "demo-receipt.json"), "utf8"),
);
const frames = buildFrames(receipt);
const external = frames.filter((frame) => frame.kind === "external");

assert.equal(frames[0].kind, "start");
assert.equal(external.length, 2);
assert.deepEqual(
  external[0].changes,
  [{ key: "player.blockingDoor", before: false, after: true }],
);
assert.ok(
  frames.some((frame) =>
    frame.changes.some(
      (change) => change.key === "platform.obstructed" && change.after === true,
    ),
  ),
);
assert.equal(frames.at(-1).state["train.status"], "departed");
assert.equal(frames.at(-1).stateHash, receipt.endStateHash);
assert.deepEqual(changesBetween({ a: 1 }, { a: 2 }), [
  { key: "a", before: 1, after: 2 },
]);
assert.equal(humanize("09-guard-investigate"), "Guard Investigate");
assert.equal(displayValue(false), "false");
assert.equal(trainLeft("arrived"), "39%");

console.log("observer causal model: PASS");
