"""Local orientation correction; optional photographic page unwarping."""

import json
import os
import sys
from pathlib import Path

_pipeline = None
_orientation = None


def main(request):
    global _pipeline, _orientation
    import cv2
    from paddleocr import DocPreprocessor, DocImgOrientationClassification
    from scan_quality import enhance
    from dark_contrast import prepare_dark_document
    from scan_orientation import line_axis, guarded_angle, rotate_quarter

    root = Path(request["model_root"])
    if _orientation is None:
        _orientation = DocImgOrientationClassification(
            device="cpu", model_dir=str(root / "paddle-orientation"), topk=1,
        )
    unwarp = os.environ.get("PDFWORD_PADDLE_UNWARP") == "1"
    if unwarp and _pipeline is None:
        _pipeline = DocPreprocessor(
            device="cpu",
            doc_unwarping_model_dir=str(root / "paddle-unwarp"),
            use_doc_orientation_classify=False,
            use_doc_unwarping=True,
        )
    for source in request["images"]:
        image = cv2.imread(source)
        if image is None:
            raise ValueError("Cannot read OCR page")
        image, contrast = prepare_dark_document(image)
        prediction = next(iter(_orientation.predict(image)))
        proposed = int(prediction["label_names"][0])
        confidence = float(prediction["scores"][0])
        evidence = line_axis(image) if proposed in (90, 270) and confidence < .9 else None
        angle, rejected = guarded_angle(proposed, confidence, evidence)
        prepared = rotate_quarter(image, angle)
        if unwarp:
            prepared = next(iter(_pipeline.predict(prepared)))["output_img"]
        prepared, quality = enhance(prepared)
        quality.update(contrast)
        quality["enhanced"] = quality["enhanced"] or contrast["dark_contrast_stretched"]
        quality.update(orientation_proposed=proposed, orientation_applied=angle,
                       orientation_confidence=confidence, orientation_rejected=rejected,
                       line_axis=evidence)
        Path(request["output"] + ".quality.json").write_text(json.dumps(quality))
        if not cv2.imwrite(source, prepared):
            raise ValueError("Image preparation failed")


if __name__ == "__main__":
    from process_server import serve

    serve(main)
