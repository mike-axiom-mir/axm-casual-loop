# Deterministic public capability discovery

This repository explicitly opts the bounded Train Platform process adapter into AXM public-safe capability discovery.

The declared capability is `axm.causal-loop.train-platform.process/v1`. Its public registry entry is generated from the existing machine-readable capability descriptor and a real `describe` request through `scripts/causal_loop_ndjson.py`. The generator requires those two views to agree before it emits discovery evidence.

Regenerate after an intentional process-boundary change:

```bash
python tools/generate_public_capabilities.py --write
```

Verify committed evidence without rewriting it:

```bash
python tools/generate_public_capabilities.py --check
python -m unittest discover -s tests -p 'test_public_capability_discovery.py' -v
```

The integration workflow additionally builds Discovery Buddy at pinned ref `565c38ecf93a9d563b02211258d8d36fcb1162b5` into its deterministic one-file `discovery-buddy.pyz`, deletes that source checkout, and uses only the portable artifact to scan, verify, and query this repository.

## Truth and authority boundary

A discovery hit proves only that this source tree explicitly declares the bounded process adapter and that its generated discovery record matches the checked descriptor, executable `describe` result, entrypoint, and license source identities.

The provider descriptor has no maturity/status field, so public discovery preserves that truth as `status: null`; it does not invent `WORKING`, `TEST`, or another stronger label.

Discovery does not execute a causal run, select the adapter for a consumer, install it, commit history, write canonical state, merge a branch, or establish CANON. A consumer must separately choose the provider, invoke it deliberately, and verify any returned run evidence under its own authority rules.

## Pattern provenance

The generated public-discovery pattern is adapted from `mike-axiom-mir/axm-floor-born@2ac02c4ee0d17ea5772ae923aba522c2d3e9f297`, which in turn exercised the portable Discovery Buddy boundary. No Floorborn or Discovery Buddy runtime code is copied into Causal Loop Fabric.
