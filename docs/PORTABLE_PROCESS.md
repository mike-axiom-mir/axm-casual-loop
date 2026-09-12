# Portable Causal Loop process v1

This lane packages the existing PR #8 train-platform NDJSON provider as one deterministic local Python ZIP application. It is a distribution boundary around the same process contract, not a second causal engine and not a new authority.

## Why this exists

PR #8 makes `axm.causal-loop.train-platform.process/v1` callable from outside the repository working directory, but the caller still needs the Causal Loop checkout. The portable builder removes that checkout dependency for deliberate local transfer:

```text
trusted provider checkout
  -> deterministic builder
  -> causal-loop-process.pyz
  -> copy one file to another local directory
  -> caller explicitly invokes the same describe/run/verify NDJSON process
```

The process remains Python 3.11+, standard-library only, offline, headless, and uncommitted. No network, account, cloud, model, package registry, or installation step is added.

## Build and verify

```bash
python scripts/build_causal_loop_portable.py build \
  --output causal-loop-process.pyz

python scripts/build_causal_loop_portable.py verify \
  causal-loop-process.pyz

python causal-loop-process.pyz portable-verify
python causal-loop-process.pyz portable-describe
python causal-loop-process.pyz < examples/process-requests.ndjson
```

`build` is create-only and refuses to replace an existing output path. The archive uses a fixed member set, fixed timestamps, fixed regular-file modes, stored ZIP members, canonical metadata, per-member SHA-256 evidence, and the exact provider files required by the PR #8 process boundary. Rebuilding unchanged source produces byte-identical output.

Provider-side `verify` binds the archive back to the current trusted checkout bytes. Standalone `portable-verify` proves only that the copied archive is internally consistent with its embedded descriptor and declared authority. It is not a signature and cannot authenticate a producer that deliberately replaces and re-seals the whole artifact.

The wrapper verifies itself before importing the embedded provider and requires the embedded live `capability_descriptor()` to equal the embedded machine descriptor. With no portable command argument, stdin/stdout behavior remains the existing NDJSON process contract.

## Authority

The portable metadata explicitly keeps all of these false:

- automatic execution;
- automatic provider selection;
- installation authority;
- history commit authority;
- canonical-state write authority;
- merge authority;
- CANON authority.

The artifact executes only because a caller explicitly invokes it. Process receipts remain the existing uncommitted deterministic evidence.

## Provenance

The deterministic ZIP-application pattern is adapted from the verified Reference-state Closure portable lane in `mike-axiom-mir/axm-state-research` PR #22 at exact head `ec159470bef52974dad25292ea7a6b34be54ccd4`.

That is pattern provenance, not a runtime dependency. No State Research runtime code is imported into the Causal Loop artifact.

## Evidence contract

Focused tests and CI require:

- byte-identical rebuilds from unchanged source;
- provider-side source binding;
- standalone self-verification from an unrelated directory with `PYTHONPATH` removed;
- byte-identical process responses between the source entrypoint and the copied ZIP application for the real example request batch;
- fail-closed rejection of a tampered member;
- fail-closed rejection of an unexpected archive member;
- the complete inherited deterministic repository suite.

This proves one portable local distribution seam for the exact PR #8 train-platform provider. It does not prove producer authorship, signatures, hostile-process isolation, generic Causal Loop portability, arbitrary consumer compatibility, Windows/macOS behavior, package-registry publication, or permission to execute a discovered provider.
