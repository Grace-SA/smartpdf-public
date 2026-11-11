"""Bounded Apple Silicon OCR subprocesses for local acceptance only."""

import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit


def main(request):
    from mlx_vlm import apply_chat_template, generate, load
    from PIL import Image
    from ocr import parse_u2

    engine = request["engine"]
    root = Path(request["model_root"])
    name = {"u2": "u2", "oxr": "oxr", "paddle": "paddle-vl"}[engine]
    model, processor = load(str(root / name), trust_remote_code=False)
    limit = min(int(request.get("max_tokens", 8192)), 8192)
    truncated = False

    def infer(image, prompt, cap=limit):
        nonlocal truncated
        text = apply_chat_template(processor, model.config, prompt, num_images=1)
        out = generate(
            model, processor, text, image=[image], max_tokens=cap, temperature=0
        )
        truncated |= out.generation_tokens >= cap
        return out.text

    if engine == "u2":
        pages = []
        for image in request["images"]:
            parsed = parse_u2(infer(image, "Multi page parsing."))
            if len(parsed) != 1:
                raise ValueError("page mismatch")
            pages.extend(parsed)
    elif engine == "oxr":
        import cv2
        from oxr.config.settings import settings
        from oxr.model.client import ModelOutput, model_client
        from oxr.pipeline.orchestrator import process_decoded_document

        endpoint = urlsplit(settings.layout_analyze_model.url)
        if (
            endpoint.scheme != "http"
            or endpoint.hostname not in ("127.0.0.1", "localhost", "::1")
            or endpoint.username
        ):
            raise ValueError("OXR layout inference must use a local endpoint")

        async def local_inference(
            prompt, image, timeout, model_options=None, max_tokens=None
        ):
            value = infer(
                Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)),
                prompt,
                min(max_tokens or limit, limit),
            )
            return ModelOutput(value, finish_reason="length" if truncated else "stop")

        model_client._call_vision_model = local_inference
        settings.oxr_model.max_concurrency = 1
        settings.debug = False
        settings.pipeline.image_output_dir = str(
            Path(request["output"]).parent / "figures"
        )

        async def run():
            images = [cv2.imread(p) for p in request["images"]]
            return await process_decoded_document(
                images, "document.pdf", ["json"], keep_header_footer=True
            )

        result = asyncio.run(run())
        pages = []
        for page in result["outputs"]["json"]["pages"]:
            size = page["page_size"]
            pages.append(
                [
                    dict(
                        label=b["type"].lower(),
                        bbox=[
                            v * 1000 / size["w" if i % 2 == 0 else "h"]
                            for i, v in enumerate(b["bbox"])
                        ],
                        content=b.get("content", ""),
                    )
                    for b in page["blocks"]
                ]
            )
    else:
        raise ValueError("Use the official Paddle pipeline adapter")
    Path(request["output"]).write_text(
        json.dumps(dict(pages=pages, truncated=truncated), ensure_ascii=False)
    )


if __name__ == "__main__":
    main(json.loads(Path(sys.argv[1]).read_text()))
