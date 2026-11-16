"""Official PaddleOCR-VL layout + regional recognition; local inference only."""

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit


def main(request):
    from paddleocr import PaddleOCRVL
    from openai.resources.chat.completions import AsyncCompletions
    from prepare_image import main as prepare

    original = AsyncCompletions.create

    async def bounded(self, *args, **kwargs):
        response = await original(self, *args, **kwargs)
        if any(c.finish_reason != "stop" for c in response.choices):
            raise ValueError("Incomplete Paddle recognition")
        return response

    AsyncCompletions.create = bounded
    url = os.environ.get("PDFWORD_PADDLE_URL", "http://127.0.0.1:18084/v1")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
        or parsed.username
    ):
        raise ValueError("Paddle inference must use a local endpoint")
    root = Path(request["model_root"])
    prepare(request)
    pipeline = PaddleOCRVL(
        pipeline_version="v1.5",
        device="cpu",
        layout_detection_model_dir=str(root / "paddle-layout"),
        vl_rec_backend="mlx-vlm-server",
        vl_rec_server_url=url,
        vl_rec_api_model_name=str(root / "paddle-vl"),
        vl_rec_max_concurrency=1,
        doc_orientation_classify_model_dir=str(root / "paddle-orientation"),
        doc_unwarping_model_dir=str(root / "paddle-unwarp"),
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_chart_recognition=False,
        use_seal_recognition=False,
        use_ocr_for_image_block=False,
        format_block_content=False,
        markdown_ignore_labels=[],
        use_queues=False,
    )
    pages = []
    images = []
    for result in pipeline.predict(request["images"], max_new_tokens=8192):
        value = result.json["res"]
        width = value["width"]
        height = value["height"]
        corrected = result.get("doc_preprocessor_res", {}).get("output_img")
        if corrected is not None:
            import cv2

            height, width = corrected.shape[:2]
            path = Path(request["output"]).with_name(f"corrected-{len(pages)}.png")
            if not cv2.imwrite(str(path), corrected):
                raise ValueError("Cannot retain corrected image")
            images.append(str(path))
        else:
            images.append(None)
        pages.append(
            [
                dict(
                    label=b["block_label"],
                    content=b["block_content"],
                    bbox=[
                        float(v) * 1000 / (width if i % 2 == 0 else height)
                        for i, v in enumerate(b["block_bbox"])
                    ],
                )
                for b in value["parsing_res_list"]
            ]
        )
    Path(request["output"]).write_text(
        json.dumps(
            dict(pages=pages, images=images, truncated=False), ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main(json.loads(Path(sys.argv[1]).read_text()))
