"""Isolated, optional Camelot runtime. No network or document contents in logs."""
import json
import sys
from pathlib import Path


def main():
    import camelot
    import cv2
    cv2.setNumThreads(1)
    tables = camelot.read_pdf(sys.argv[1], flavor="stream", pages="all",
                              parallel=False, suppress_stdout=True)
    result = []
    for table in tables:
        if len(result) >= 1000:
            raise ValueError("Table proposal budget exceeded")
        result.append(dict(page=table.page, rotation=table.rotation,
                           pdf_size=list(table.pdf_size), cols=table.cols,
                           rows=table.rows, grid=table.df.values.tolist()))
    payload = json.dumps(result)
    if len(payload.encode()) > 8 * 1024**2:
        raise ValueError("Table proposal budget exceeded")
    Path(sys.argv[2]).write_text(payload)


if __name__ == "__main__":
    main()
