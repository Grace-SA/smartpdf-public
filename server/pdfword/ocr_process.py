"""Bounded Apple Silicon OCR subprocesses for local acceptance only."""

import asyncio
from contextvars import ContextVar
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
from ocr_recovery import bounded_generate, recognize_block as recover_text_block

_loaded = None
_loop = None


def main(request):
    global _loaded, _loop
    from mlx_vlm import apply_chat_template, generate, load
    from PIL import Image
    from ocr import parse_u2

    engine = request["engine"]
    root = Path(request["model_root"])
    name = {"u2": "u2", "oxr": "oxr", "paddle": "paddle-vl"}[engine]
    key = str(root / name)
    if _loaded is None:
        _loaded = (key, *load(key, trust_remote_code=False))
    if _loaded[0] != key:
        raise ValueError("A model process is scoped to one engine")
    _, model, processor = _loaded
    limit = min(int(request.get("max_tokens", 8192)), 8192)
    truncated = False

    def infer(image, prompt, cap=limit, options=None):
        nonlocal truncated
        text = apply_chat_template(processor, model.config, prompt, num_images=1)
        out, hit_limit = bounded_generate(
            generate, model, processor, text, image, cap, options,
            guard_repetition=engine == 'oxr' and prompt == 'Recognize the content of the image.'
        )
        if engine == "u2":
            truncated |= hit_limit
        return out.text, hit_limit

    if engine == "u2":
        pages = []
        for image in request["images"]:
            parsed = parse_u2(infer(image, "Multi page parsing.")[0])
            if len(parsed) != 1:
                raise ValueError("page mismatch")
            pages.extend(parsed)
    elif engine == "oxr":
        import cv2
        from oxr.config.settings import settings
        from oxr.model.client import ModelOutput, model_client
        from oxr.pipeline.orchestrator import process_decoded_document
        from oxr.pipeline import recognition

        active_block = ContextVar("ocr_block", default=None)
        recognize_block = recognition.recognize_block

        async def checked_block(*args, **kwargs):
            nonlocal truncated
            state = {}
            token = active_block.set(state)
            try:
                result = await recognize_block(*args, **kwargs)
                # A discarded truncated attempt may have recovered. Only the
                # final inference for each block determines completeness.
                truncated |= state.get("truncated", False)
                return result
            finally:
                active_block.reset(token)

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
            original = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            cap = min(max_tokens or limit, limit)
            # Tables/formulae and unpartitionable text retain their original
            # ceiling. All text bands must terminate; no partial output succeeds.
            value, hit_limit = recover_text_block(infer, original, prompt, cap, model_options)
            state = active_block.get()
            if state is not None:
                state["truncated"] = hit_limit
            return ModelOutput(value, finish_reason="length" if hit_limit else "stop")

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

        if _loop is None:
            _loop = asyncio.new_event_loop()
        recognition.recognize_block = checked_block
        try:
            result = _loop.run_until_complete(run())
        finally:
            recognition.recognize_block = recognize_block
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
    from process_server import serve

    serve(main)
