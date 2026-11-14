# Bounded PDF-to-Excel K/V cache research

**Research only, default off. No production service imports this directory.**
Do not merge or enable this experiment as a release. Model weights, content and
quality gates, the 150-second model deadline, CPU device and two threads remain
unchanged.

## Controlled adapter

`build_converter(models)` returns the existing converter. Only an explicit
`enabled=True` can request the research pipeline; no environment switch exists.
Exact package versions and ten critical Python source hashes must match
`runtime-lock.json`. Otherwise the original converter is returned. This is not
an attestation of every native-library binary.

The pipeline owns its predictor instance. No dependency file or global class is
changed. Original attention modules are restored and cache references released
in `finally`, including setup failures and cancellation. Concurrent entry to the
same predictor is rejected rather than mixing mutable model state.

Caching supports only plain CPU float32, eval/no-grad, single-query, shared K/V,
unmasked attention. Other inputs use the original module. Packed projection,
reshape, SDPA and output-projection order remain unchanged. Bit snapshots detect
sequential alias/.data/NumPy changes and signed zero, not concurrent writers.
Inputs, parameters and backend settings must remain immutable during a call.
Custom dispatch modes, tracing and arbitrary code interception are uncertified.

A cache-path error clears its entry, disables that layer's cache for the table,
and falls back. Original-operator errors propagate without retry. Shadow errors
are not swallowed. The shared persistent-cache reservation limit is 32 MiB and
an entry is at most 8 MiB; excess layers use the original operator. Zero is a
supported budget; a larger limit is rejected.

**This is not a process-memory ceiling.** Transient tensors, images, model
buffers and allocator retention consume more memory. A Docling timeout does not
cancel an already-running Torch call: cleanup occurs on actual predictor exit.
The existing service separately waits for child.close and enforces its own
180-second SIGKILL. Never obtain a fresh deadline for each page to disguise a
full-document timeout.

## Reproduce

Use the existing pinned runtime/model setup in `server/pdf-to-excel/README.md`.
Tested versions: Python3.12, torch2.15.0+cpu, docling-slim2.150.0 and
 docling-ibm-models4.0.4. Inference downloads nothing.

From the repository root:

```sh
OMP_NUM_THREADS=2 python -m unittest discover -s research/pdf-excel-kv -p 'test_*.py'
OMP_NUM_THREADS=2 python research/pdf-excel-kv/benchmark.py public.pdf ../kv-baseline --models MODEL_DIRECTORY
OMP_NUM_THREADS=2 python research/pdf-excel-kv/benchmark.py public.pdf ../kv-cached --models MODEL_DIRECTORY --enabled
python research/pdf-excel-kv/compare.py --baseline ../kv-baseline --candidate ../kv-cached --report ../kv-comparison.json
```

Wait for full process exit between runs, not just a printed result. The benchmark
uses a local engine-factory override and scoped instance observation only inside
its process. Outputs and traces contain document content. **Keep private inputs
and all raw outputs outside Git; never upload them.**

The comparator checks exact complete-trace multisets, since execution order is
not source-page order. It independently checks sheet sets, cell values/types,
formats/comments/semantic styles and merges. Dimension differences are reported
without tolerance. Source accuracy and model equivalence are separate checks.

## Limits and evidence

`validation.json` records fixed public samples and observations. The native
SIGKILL test verifies one process is reaped and creates no cache files; it does
not certify containers, cgroups, hard RSS limits or secure memory erasure.
Docker, Podman, runc and cgroups were unavailable. No other connected execution
environment was available. Real deployment memory/pressure/kill tests are
**not run**, not passing.

General PDF accuracy, OCR coverage, concurrent-predictor support, Office-rendered
visual acceptance and production readiness are not established. Broad frozen
corpus regression, audited integration/admission, deployment resource ceilings
and independent release review remain required. The partial checkout cannot
satisfy the inherited approved-asset inventory check; this is not a pass.

`PYTORCH-LICENSE.txt` retains the license for the operation ordering. No public
PDF, rendered image, model binary, private data or raw trace is included here.

### Additional native resource probes

`test_native_limits.py` exercises three **synthetic small-attention** scenarios in
separate Linux child processes. It does not load TableFormer or convert PDFs:

* Two children simultaneously hold independent caches, then each performs 100
  in-place memory replacements. Every result must exactly match its own original
  attention operator; each local reservation stays within 40,000 bytes and
  reaches zero on explicit cleanup. This is not a shared aggregate budget.
* After Torch warm-up, a child imposes `RLIMIT_AS` at its current virtual mapping
  size plus 64 MiB. A real 256 MiB Torch allocation must fail, while ten subsequent
  calls still match the original result. The allocation failure is outside the
  cache and does not establish recovery from every internal allocation failure.
* A child with a live cache runs attention repeatedly under adjacent soft/hard
  CPU limits. The parent requires termination by `SIGXCPU`, reaps
  it and checks that no files appeared in the isolated working directory.

All limits are set only in the test child. They do not change parent settings.
Before loading Torch the child disables core dumps and Linux dumpability;
failure to do so fails the probe. Child processes are reaped before deleting
their working directory, including assertion/timeout failures.
These tests passed locally alongside the existing research tests (20 total).
They establish native process behavior, **not** a production memory ceiling:
`RLIMIT_AS` is virtual address space, not RSS; CPU time is not a wall deadline;
no aggregate multi-job memory, cgroup OOM, secure erasure, full-model concurrent
load or deployment container acceptance is certified. No runtime or production
code was changed for these probes. The prior public-PDF equivalence measurements
remain the coverage evidence; these new synthetic tests do not increase it.
