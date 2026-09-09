# Local process adapter v1

`scripts/causal_loop_ndjson.py` exposes the existing deterministic train-platform loop to any local consumer that can start a process and exchange newline-delimited JSON. It uses only the Python standard library, performs no network access, and works from a working directory outside this repository.

The adapter is a boundary around the current engine, not a second engine. It cannot commit history, write canonical state outside its process, merge changes, or declare anything CANON. A `PASS` means only that the declared request was accepted and its receipt reproduced on this exact loop and engine version.

## Run it

Requires Python 3.11 or newer.

```bash
python scripts/causal_loop_ndjson.py < examples/process-requests.ndjson
```

Each non-empty input line produces exactly one canonical JSON output line. The process exits `0` if every response is `PASS`, and `1` if any response is `HOLD`. It keeps processing after a bad line so batch callers receive a result for every non-empty input.

The machine-readable capability descriptor is `capabilities/causal-loop-process-v1.json`. A consumer can also send a `describe` request to read the live contract.

## Request contract

Every request uses schema `axm.causal-loop.process-request/v1`, a non-empty `requestId` of at most 128 characters, and one operation:

- `describe` accepts no operation-specific fields.
- `run` requires `timedInfluences` and optionally accepts `maxWaves` from 1 through 256. Each influence has exactly `atWave` and `action`; at most 64 are accepted.
- `verify` requires a complete receipt previously produced by this engine version and optionally accepts the original `maxWaves` value (default `64`). Supplying that value is required to reproduce a receipt for a run that stopped at a non-default causal budget.

Unknown or duplicate object fields, unsupported actions, booleans disguised as integers, non-finite numbers, oversized batches, malformed JSON, receipt shape changes, hash mismatches, and replay mismatches fail closed as `HOLD`. Repeated timed influences remain valid because their declared sequence is deterministic engine input.

Allowed directions are `WAIT`, `BLOCK_DOOR`, `TRIGGER_ALARM`, and `TALK_TO_PASSENGER`. They remain direction only. The engine's deterministic modules derive consequences.

Example run request:

```json
{"schema":"axm.causal-loop.process-request/v1","requestId":"run-1","op":"run","timedInfluences":[{"atWave":2,"action":"BLOCK_DOOR"}],"maxWaves":64}
```

The response includes the full uncommitted causal receipt, its integrity hash, the canonical input hash, the effective `executionMaxWaves`, and a replay result. Failed engine executions remain visible as `HOLD` responses with their receipt. To verify a receipt later, pass it unchanged as the `receipt` field of a `verify` request and preserve its `executionMaxWaves` value.

## Compatibility boundary

The v1 process schemas and capability ID are the consumer contract. The descriptor also pins the current loop ID, loop version, and receipt schema. A mismatch is explicit; the adapter does not silently translate receipts between engine versions.

This seam proves local deterministic consumption of the bounded train-platform loop. It does not claim cross-engine compatibility, remote execution, process isolation for hostile code, authorship, production readiness, or general causal-loop portability.
