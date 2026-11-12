"""Exercise the adapter's final-block completeness contract without model weights."""

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import ocr_process


class CompletionTests(unittest.TestCase):
    def run_pipeline(self, blocks, lengths, engine="oxr"):
        def module(name, **values):
            result = types.ModuleType(name)
            result.__dict__.update(values)
            return result

        class ModelOutput(str):
            def __new__(cls, value, finish_reason):
                result = super().__new__(cls, value)
                result.finish_reason = finish_reason
                return result

        client = types.SimpleNamespace()
        finish_reasons = []

        async def recognize_block(attempts):
            for _ in range(attempts):
                out = await client._call_vision_model("synthetic", object(), 1)
                finish_reasons.append(out.finish_reason)
            return out

        recognition = module(
            "oxr.pipeline.recognition", recognize_block=recognize_block
        )

        async def process(*args, **kwargs):
            for attempts in blocks:
                await recognition.recognize_block(attempts)
            return {
                "outputs": {
                    "json": {
                        "pages": [{"page_size": {"w": 100, "h": 100}, "blocks": []}]
                    }
                }
            }

        lengths = iter(lengths)
        modules = {
            "mlx_vlm": module(
                "mlx_vlm",
                load=lambda *a, **k: (types.SimpleNamespace(config={}), object()),
                apply_chat_template=lambda *a, **k: "prompt",
                generate=lambda *a, **k: types.SimpleNamespace(
                    text="<PAGE><BLOCK>text [0,0,1000,1000]<FORK>complete",
                    generation_tokens=next(lengths),
                ),
            ),
            "cv2": module(
                "cv2",
                imread=lambda p: object(),
                cvtColor=lambda *a: object(),
                COLOR_BGR2RGB=1,
            ),
            "oxr": module("oxr"),
            "oxr.config": module("oxr.config"),
            "oxr.config.settings": module(
                "oxr.config.settings",
                settings=types.SimpleNamespace(
                    layout_analyze_model=types.SimpleNamespace(
                        url="http://127.0.0.1:18083"
                    ),
                    oxr_model=types.SimpleNamespace(),
                    pipeline=types.SimpleNamespace(),
                ),
            ),
            "oxr.model": module("oxr.model"),
            "oxr.model.client": module(
                "oxr.model.client", ModelOutput=ModelOutput, model_client=client
            ),
            "oxr.pipeline": module("oxr.pipeline", recognition=recognition),
            "oxr.pipeline.recognition": recognition,
            "oxr.pipeline.orchestrator": module(
                "oxr.pipeline.orchestrator", process_decoded_document=process
            ),
        }
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            sys.modules, modules
        ), patch("PIL.Image.fromarray", return_value=object()), patch.object(
            ocr_process, "_loaded", None
        ), patch.object(
            ocr_process, "_loop", None
        ):
            output = Path(temp) / "result.json"
            try:
                ocr_process.main(
                    dict(
                        engine=engine,
                        model_root=temp,
                        images=["synthetic.png"],
                        output=str(output),
                        max_tokens=8,
                    )
                )
                result = json.loads(output.read_text())
                self.assertIs(recognition.recognize_block, recognize_block)
            finally:
                if ocr_process._loop is not None:
                    ocr_process._loop.close()
        return result, finish_reasons

    def test_complete_retry_clears_only_its_own_discarded_attempt(self):
        result, reasons = self.run_pipeline([2], [8, 1])
        self.assertEqual(reasons, ["length", "stop"])
        self.assertFalse(result["truncated"])

    def test_later_complete_block_does_not_hide_an_incomplete_block(self):
        result, reasons = self.run_pipeline([1, 1], [8, 1])
        self.assertEqual(reasons, ["length", "stop"])
        self.assertTrue(result["truncated"])

    def test_u2_still_refuses_token_limited_whole_page(self):
        result, _ = self.run_pipeline([], [8], engine="u2")
        self.assertTrue(result["truncated"])
