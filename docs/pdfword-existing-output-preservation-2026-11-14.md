# Preserve an existing result when the local Word runner is retried

Base: `codex/pdfword-general` at `0d4ad530787390944c8c278c1853388ebb562f35`.
This change concerns the explicitly enabled local acceptance runner, not the
Docker production runner.

## Actual reproduction

Place an existing `output.docx` in the task directory and call
`local_runner.run()` with `PDFWORD_LOCAL_V2=1` and shared mode disabled.
The actual `convert()` correctly rejects an existing output, but the runner's
`except Rejected` cleanup unconditionally unlinks that output. A retry thus
deletes a result that this invocation did not create. The baseline regression
test observes the missing file after the real conversion entry point refuses;
conversion is not mocked for this reproduction.

## Fix and scope

Before entering the conversion/failure-cleanup region, refuse an existing output
path, including a directory or dangling symbolic link. Emit the existing
`INPUT_REJECTED` error and leave its bytes/inode or link untouched. Fresh tasks
continue using their existing success, failure cleanup and deadline handling.

This is a startup ownership check, not a cross-process lock. Task directories
must remain private to a single active invocation. It does not establish safety
against another writer creating an output after the check. No output contents,
PDF reconstruction, OCR, visuals, container settings or permissions change.

## Validation

Four new tests cover preservation of existing file bytes/inode, dangling link,
directory contents, and normal fresh success/failure cleanup. Together with the
existing deadline test and seven Docker-runner lifecycle tests, all 12 pass:

```sh
python -m unittest test_local_existing_output test_local_deadline test_runner -v
```

The Docker tests use fault injection; this does not add actual Docker or Office
acceptance. No merge, deployment or production-readiness claim.
