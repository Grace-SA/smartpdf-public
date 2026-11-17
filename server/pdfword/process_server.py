"""Private, job-scoped request loop. Model state never crosses document jobs."""

import json
import signal
import sys
import traceback
from pathlib import Path


def serve(main):
    if sys.argv[1] != "--serve":
        main(json.loads(Path(sys.argv[1]).read_text()))
        return
    for line in sys.stdin:
        request = Path(line.strip())
        result = {"ok": False}
        try:
            # Independent ceiling also bounds a busy child if its parent dies.
            signal.alarm(180)
            main(json.loads(request.read_text()))
            result["ok"] = True
        except Exception:
            # Only the private log contains exception details or document content.
            traceback.print_exc()
        finally:
            signal.alarm(0)
        done = Path(str(request) + ".done")
        temporary = done.with_suffix(".tmp")
        temporary.write_text(json.dumps(result))
        temporary.replace(done)
