"""Local orientation correction; optional photographic page unwarping."""

import json
import os
import sys
from pathlib import Path


def main(request):
    import cv2
    from paddleocr import DocPreprocessor

    root = Path(request["model_root"])
    pipeline = DocPreprocessor(
        device="cpu",
        doc_orientation_classify_model_dir=str(root / "paddle-orientation"),
        doc_unwarping_model_dir=str(root / "paddle-unwarp"),
        use_doc_orientation_classify=True,
        use_doc_unwarping=os.environ.get("PDFWORD_PADDLE_UNWARP") == "1",
    )
    for source, result in zip(request["images"], pipeline.predict(request["images"])):
        if not cv2.imwrite(source, result["output_img"]):
            raise ValueError("Image preparation failed")


if __name__ == "__main__":
    main(json.loads(Path(sys.argv[1]).read_text()))
