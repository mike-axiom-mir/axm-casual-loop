# Checkpoint Recovery Station

The Checkpoint Recovery Station is a local, read-mostly human surface for the persisted checkpoint chain introduced by PRs #11, #13, and #14.

It closes one narrow loop:

```text
inspect verified candidates
-> choose one exact checkpoint
-> revalidate the candidate set
-> prepare the existing deterministic resume plan
-> copy that exact plan for an explicit caller handoff
```

It does **not** choose a latest/best checkpoint, execute `engine.resume()`, mutate causal state, delete checkpoints, repair held files, reach the network, or grant merge/CANON authority.

## Run

Requires Python 3.11+ and an existing `LocalCheckpointStore` directory.

```bash
python -m tools.checkpoint_recovery_station --store /path/to/checkpoints
```

Then open the printed loopback URL. The station binds only to `127.0.0.1`.

The page starts with no selected checkpoint. Candidate order remains the inventory's deterministic content-hash order and is explicitly not a freshness/preference ranking. `wavesExecuted / maxWaves` is shown only as recorded causal-depth context.

Selecting **Prepare exact plan** sends the visible `candidateSetHash` and chosen `checkpointHash` back through the existing `prepare_checkpoint_resume()` contract. That function re-scans the store and refuses a stale candidate set before returning a plan. The station displays the plan receipt and keeps the complete plan only for the explicit **Copy exact plan JSON** action.

A copied plan is still not a resume. A caller must deliberately pass its checkpoint into the existing engine path, where checkpoint-prefix admission remains authoritative.

## Truth boundary

- Checkpoint files are canonical content-addressed evidence under `LocalCheckpointStore`.
- Inventory is derived discovery evidence.
- The resume plan is caller-selected derived evidence.
- The station is presentation and handoff only.
- SHA-256 establishes deterministic content identity inside these contracts, not authorship.
- Browser clipboard failure does not trigger a hidden file write or download fallback.
- The station exposes held/temporary/ignored inventory diagnostics but does not repair them.

The product surface has no third-party runtime dependency, account, cloud service, telemetry, relay, or internet requirement. Browser automation used by CI is evidence tooling only.
