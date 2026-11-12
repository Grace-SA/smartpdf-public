"""Local orientation correction; optional photographic page unwarping."""

import json
import os
import sys
from pathlib import Path

_pipeline = None


def main(request):
    global _pipeline
    import cv2
    from paddleocr import DocPreprocessor
    from scan_quality import enhance

    root = Path(request["model_root"])
    if _pipeline is None:
        _pipeline = DocPreprocessor(
            device="cpu",
            doc_orientation_classify_model_dir=str(root / "paddle-orientation"),
            doc_unwarping_model_dir=str(root / "paddle-unwarp"),
            use_doc_orientation_classify=True,
            use_doc_unwarping=os.environ.get("PDFWORD_PADDLE_UNWARP") == "1",
        )
    for source, result in zip(request["images"], _pipeline.predict(request["images"])):
        prepared, quality = enhance(result["output_img"])
        Path(request["output"] + ".quality.json").write_text(json.dumps(quality))
        if not cv2.imwrite(source, prepared):
            raise ValueError("Image preparation failed")


if __name__ == "__main__":
    from process_server import serve

    serve(main)
