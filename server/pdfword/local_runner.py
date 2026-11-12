"""Opt-in local acceptance runtime. Production continues using the pinned sandbox."""

import json
import os
import signal
import sys
from pathlib import Path
from worker import convert, Rejected


def emit(**value):
    print(json.dumps(value), flush=True)


def run(directory):
    if (
        os.environ.get("PDFWORD_LOCAL_V2") != "1"
        or os.environ.get("OFFICE_SHARED_MODE") == "true"
    ):
        raise RuntimeError("The v2 reference runtime is local acceptance only")
    directory = Path(directory).resolve()
    cancel = directory / "cancel"
    signal.signal(signal.SIGTERM, lambda *_: cancel.touch())
    signal.signal(signal.SIGINT, lambda *_: cancel.touch())
    timed_out = False

    def timeout(*_):
        nonlocal timed_out
        timed_out = True
        cancel.touch()
        raise Rejected("Conversion exceeded the local task time limit.")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(270)
    try:
        emit(state="checking")
        report = convert(
            directory / "input.pdf",
            directory / "output.docx",
            cancel=cancel,
            progress=lambda value: emit(**value),
        )
        if cancel.exists():
            raise Rejected("Conversion cancelled.")
        (directory / "expected.json").write_text(json.dumps(report))
        emit(state="checking-result", warnings=report["warnings"])
        return 0
    except Rejected as error:
        (directory / "output.docx").unlink(missing_ok=True)
        emit(
            error=(
                "Conversion exceeded the local task time limit."
                if timed_out
                else str(error)
            ),
            code="TIME_LIMIT" if timed_out else "INPUT_REJECTED",
        )
        return 2
    except Exception:
        (directory / "output.docx").unlink(missing_ok=True)
        emit(error="The PDF could not be converted safely.", code="CONVERSION_FAILED")
        return 3
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    if sys.argv[1] == "--reap":
        sys.exit(0)
    sys.exit(run(sys.argv[1]))
