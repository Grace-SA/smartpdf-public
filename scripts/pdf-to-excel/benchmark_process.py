"""Distinguish expected converter refusals from failed process/protocol results."""

import json


def parse_reply(return_code, stdout):
    try:
        result = json.loads(stdout.decode("utf-8").strip().splitlines()[-1])
        if not isinstance(result, dict):
            raise ValueError("Converter response is not an object")
    except (UnicodeError, ValueError, IndexError) as error:
        return {
            "status": "error",
            "reason": f"Invalid converter response (exit {return_code}): {error}",
        }
    message = result.get("error")
    if return_code:
        if return_code == 2 and isinstance(message, str) and message.strip():
            return {"status": "refused", "reason": message}
        return {
            "status": "error",
            "reason": f"Converter process exited with code {return_code}",
        }
    if "error" in result:
        return {"status": "error", "reason": "Successful process reported an error"}
    return {"status": "converted", "result": result}
