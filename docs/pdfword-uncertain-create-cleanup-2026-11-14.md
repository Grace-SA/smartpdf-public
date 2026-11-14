# PDF-to-Word: clean up an uncertain container creation

Base: `codex/pdfword-general` at `d554668c77724f7ff339790f736f2ff778f01085`.

## Reproduction

`runner.py` previously marked `created = True` only after the Docker CLI
returned success. A create request can take effect at the daemon while the CLI
returns an error or times out. In that case, the finalizer skipped its
name-scoped inspection and removal, leaving the job's container behind.

Fault injection models the ordering explicitly: the mock daemon records the
container as present, then `docker create` raises `TimeoutExpired` or
`CalledProcessError`. Both new subcases fail on the original runner because the
container remains present. This is a daemon/CLI uncertainty reproduction, not
an assertion that a real Docker daemon was exercised in this environment.

No document has been copied into the container at this stage; this change
addresses orphaned container state, not a demonstrated document-data leak.

## Change

Record `create_attempted` immediately before issuing `docker create`. After an
attempt, always run the existing finalizer: inspect the exact random job name,
remove it if present, and query again to verify removal. Do not use broad labels
or remove another job. If the create request had no daemon-side effect, the
queries find nothing and no removal command is issued. Existing cleanup failure
reporting remains intact.

This does not change conversion output, OCR, resource limits, container flags,
network settings, image pins, or Office rendering. No visual acceptance claim
is needed for this lifecycle-only change.

## Validation and limits

Seven unit tests pass, covering normal conversion/isolation, worker refusal and
timeout, cancellation, both uncertain-create failures, create failure without
a container, cleanup-query failure reporting, and event-synchronized cancellation
while create is pending (both success and timeout after the watcher removes
the not-yet-created container). Tests are fault-injected and
do not require Docker. Run from `server/pdfword`:

```sh
python -m unittest test_runner -v
```

A real Docker daemon/container runtime is unavailable here; actual daemon
restart behavior, host reboot, SIGKILL and service-wide reaping are not newly
validated. Existing service reaping remains necessary when the runner cannot
execute its finalizer. A daemon operation that creates the container only after
the final verification query can still escape this finalizer; external reaping
is a compensating mechanism, not newly demonstrated here. No merge, deployment, or production-readiness claim.
