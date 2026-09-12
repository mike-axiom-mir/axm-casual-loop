(function (root, factory) {
  const model = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = model;
  } else {
    root.CausalObserverModel = model;
  }
})(typeof window !== "undefined" ? window : this, function () {
  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function changesBetween(before, after) {
    return [...new Set([...Object.keys(before), ...Object.keys(after)])]
      .sort()
      .filter((key) => JSON.stringify(before[key]) !== JSON.stringify(after[key]))
      .map((key) => ({ key, before: before[key], after: after[key] }));
  }

  function buildFrames(receipt) {
    if (
      !receipt ||
      !receipt.startState ||
      !Array.isArray(receipt.stateTransitions)
    ) {
      throw new Error("Not a causal-loop run receipt");
    }
    let state = clone(receipt.startState);
    const frames = [
      {
        kind: "start",
        wave: null,
        sources: ["START"],
        state: clone(state),
        stateHash: receipt.startStateHash || "",
        changes: [],
      },
    ];
    let index = 0;
    while (index < receipt.stateTransitions.length) {
      const transition = receipt.stateTransitions[index];
      const before = clone(state);
      if (transition.kind === "external") {
        Object.assign(state, clone(transition.writes || {}));
        frames.push({
          kind: "external",
          wave: transition.wave,
          sources: [transition.source || "external"],
          state: clone(state),
          stateHash: transition.stateHash || "",
          changes: changesBetween(before, state),
        });
        index += 1;
        continue;
      }
      if (transition.kind === "module") {
        const wave = transition.wave;
        const merged = {};
        const sources = [];
        let stateHash = "";
        while (
          index < receipt.stateTransitions.length &&
          receipt.stateTransitions[index].kind === "module" &&
          receipt.stateTransitions[index].wave === wave
        ) {
          const member = receipt.stateTransitions[index];
          index += 1;
          sources.push(member.source || "module");
          Object.entries(member.writes || {}).forEach(([key, value]) => {
            if (
              key in merged &&
              JSON.stringify(merged[key]) !== JSON.stringify(value)
            ) {
              throw new Error("Contradictory writes in receipt wave");
            }
            merged[key] = clone(value);
          });
          stateHash = member.stateHash || stateHash;
        }
        Object.assign(state, merged);
        frames.push({
          kind: "wave",
          wave,
          sources,
          state: clone(state),
          stateHash,
          changes: changesBetween(before, state),
        });
        continue;
      }
      throw new Error("Unsupported transition kind: " + transition.kind);
    }
    return frames;
  }

  function humanize(value) {
    return String(value)
      .replace(/^\d+-/, "")
      .replace(/[._-]+/g, " ")
      .replace(/\b\w/g, (character) => character.toUpperCase());
  }

  function displayValue(value) {
    if (value === undefined) return "unset";
    if (typeof value === "boolean") return value ? "true" : "false";
    return String(value);
  }

  function trainLeft(status) {
    if (status === "approaching") return "8%";
    if (status === "arrived") return "39%";
    return "78%";
  }

  return {
    buildFrames,
    changesBetween,
    displayValue,
    humanize,
    trainLeft,
  };
});
