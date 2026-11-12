"""Bounded adapters for a separately provisioned OCR process; no document uploads."""

import json
import os
import re
import signal
import shutil
import subprocess
import time
from pathlib import Path
from model import Rejected, box, plain, table_from_html


def parse_u2(raw):
    if len(raw) > 1000000:
        raise Rejected("OCR output exceeds limit.")
    pages = re.split(r"<PAGE>", raw)
    if not pages[0].strip():
        pages = pages[1:]
    result = []
    pattern = re.compile(
        r"<BLOCK>\s*([a-z_]+)(?:<LEVEL(\d+)>)?\s*\[\s*(-?\d+)\s*[,，]\s*(-?\d+)\s*[,，]\s*(-?\d+)\s*[,，]\s*(-?\d+)\s*\](?:<LEVEL(\d+)>)?\s*<FORK>",
        re.I,
    )
    for page in pages:
        matches = list(pattern.finditer(page))
        blocks = []
        if not matches and page.strip():
            raise Rejected("OCR did not return page structure.")
        if matches and page[: matches[0].start()].strip():
            raise Rejected("OCR has unassigned content.")
        for i, m in enumerate(matches):
            content = page[
                m.end() : matches[i + 1].start() if i + 1 < len(matches) else len(page)
            ].strip()
            content = re.sub(r"<MERGE>|<\|[^>]+\|>|<｜[^>]+｜>", "", content).strip()
            blocks.append(
                dict(
                    label=m[1].lower(),
                    bbox=[int(m[j]) for j in range(3, 7)],
                    content=content,
                )
            )
        result.append(blocks)
    return result


def normalize(records, width, height, engine):
    result = []
    for r in records:
        label = r["label"].lower().replace("-", "_").replace(" ", "_")
        base = re.sub(r"^(append_|cross_)", "", label)
        # U2 uses `other` for ordinary text that has no more specific region
        # class. Preserve only real text, not its unreadable/image placeholders.
        if base == "other" and engine == "u2":
            if r["content"].strip().lower() in {
                "",
                "[non-text]",
                "[unreadable]",
                "[image]",
                "[figure]",
            }:
                raise Rejected("OCR returned an unclassified visual region.")
            base = "text"
        base = {
            "page_header": "header",
            "page_footer": "footer",
            "section_title": "title",
            "figure_caption": "caption",
            "table_caption": "caption",
            "list_item": "list",
            "header_image": "image",
            "footer_image": "image",
            "inline_formula": "formula",
            "stamp": "image",
            "chemical_structure": "image",
            "code_block": "text",
        }.get(base, base)
        bounds = box(
            [
                v * (width if i % 2 == 0 else height) / 1000
                for i, v in enumerate(r["bbox"])
            ],
            width,
            height,
        )
        b = dict(bbox=bounds, source=engine)
        if base in {"table"}:
            b.update(
                kind="table",
                **table_from_html(r["content"]),
                continuation=label.startswith("append_"),
            )
        elif base in {
            "image",
            "figure",
            "picture",
            "chart",
            "seal",
            "img",
            "formula",
            "equation",
            "display_formula",
            "formula_number",
        }:
            b.update(
                kind="formula" if "formula" in base or base == "equation" else "image"
            )
        else:
            kinds = {
                "title": "heading",
                "doc_title": "heading",
                "paragraph_title": "heading",
                "section_header": "heading",
                "header": "header",
                "footer": "footer",
                "page_number": "footer",
                "number": "footer",
                "list": "list",
            }
            if base not in {
                "text",
                "paragraph",
                "title",
                "doc_title",
                "paragraph_title",
                "abstract",
                "content",
                "figure_title",
                "vision_footnote",
                "reference_content",
                "number",
                "header",
                "footer",
                "page_number",
                "list",
                "image_caption",
                "image_footnote",
                "page_footnote",
                "ref_text",
                "aside_text",
                "algorithm",
                "caption",
                "footnote",
                "reference",
                "section_header",
            }:
                raise Rejected("OCR returned an unsupported region.")
            text = plain(r["content"].strip())
            if "<table" in text.lower() or "<BLOCK>" in text:
                raise Rejected("OCR structure is incomplete.")
            if not text:
                continue
            b.update(kind=kinds.get(base, "paragraph"), text=text, size=11)
        result.append(b)
    return result


class OCR:
    def __init__(self, work, cancel=None, engine=None):
        self.work = Path(work)
        self.cancel = cancel
        self.engine = engine or os.environ.get("PDFWORD_OCR_ENGINE", "auto")
        self.python = os.environ.get("PDFWORD_OCR_PYTHON")
        self.model_root = os.environ.get("PDFWORD_MODEL_ROOT")
        self.calls = 0
        self.last_engine = None

    def recognize(self, image, width, height, complex_layout=False):
        if not self.python or not self.model_root:
            raise Rejected("This page needs OCR. The OCR worker is not configured.")
        self.last_engine = None
        if self.engine != "auto" or not (Path(self.model_root) / "u2").is_dir():
            engine = "oxr" if self.engine == "auto" else self.engine
            result = self._recognize(image, width, height, engine, 180)
            self.last_engine = engine
            return result
        # A failed structural response is never exported. Retry independently from
        # the original pixels; both attempts share a fixed 180-second page budget.
        started = time.monotonic()
        backup = self.work / "ocr-original.png"
        shutil.copyfile(image, backup)
        try:
            try:
                result = self._recognize(image, width, height, "oxr", 120)
                self.last_engine = "oxr"
                return result
            except Rejected:
                if self.cancel and Path(self.cancel).exists():
                    raise Rejected("Conversion cancelled.")
                remaining = 180 - (time.monotonic() - started)
                if remaining < 1:
                    raise
                shutil.copyfile(backup, image)
                result = self._recognize(image, width, height, "u2", remaining)
                self.last_engine = "u2-fallback"
                return result
        finally:
            backup.unlink(missing_ok=True)

    def _recognize(self, image, width, height, engine, budget):
        if engine not in {"u2", "oxr", "paddle"}:
            raise Rejected("OCR engine unavailable.")
        self.calls += 1
        request = self.work / f"ocr-{self.calls}.request.json"
        output = self.work / f"ocr-{self.calls}.result.json"
        request.write_text(
            json.dumps(
                dict(
                    engine=engine,
                    images=[str(image)],
                    model_root=self.model_root,
                    output=str(output),
                    max_tokens=8192,
                )
            )
        )
        python = (
            os.environ.get("PDFWORD_PADDLE_PYTHON", self.python)
            if engine == "paddle"
            else self.python
        )
        script = "paddle_process.py" if engine == "paddle" else "ocr_process.py"
        command = [python, str(Path(__file__).with_name(script)), str(request)]
        commands = []
        if engine != "paddle" and os.environ.get("PDFWORD_PADDLE_PYTHON"):
            commands.append(
                [
                    os.environ["PDFWORD_PADDLE_PYTHON"],
                    str(Path(__file__).with_name("prepare_image.py")),
                    str(request),
                ]
            )
        commands.append(command)
        env = dict(
            os.environ,
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            TOKENIZERS_PARALLELISM="false",
        )
        # Output may contain document text: keep it inside the private task directory.
        with (self.work / f"ocr-{self.calls}.log").open("wb") as log:
            started = time.monotonic()
            for command in commands:
                process = subprocess.Popen(
                    command, stdout=log, stderr=log, env=env, start_new_session=True
                )
                try:
                    while process.poll() is None:
                        if self.cancel and Path(self.cancel).exists():
                            raise Rejected("Conversion cancelled.")
                        if time.monotonic() - started > budget:
                            raise Rejected("OCR timed out. Try a shorter document.")
                        time.sleep(0.1)
                    if process.returncode:
                        raise Rejected(
                            "OCR could not finish. Retry or choose a clearer scan."
                        )
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
            if not output.exists():
                raise Rejected("OCR returned no result.")
        if output.stat().st_size > 2 * 1024**2:
            raise Rejected("OCR output exceeds limit.")
        data = json.loads(output.read_text())
        if data.get("truncated") or len(data.get("pages", [])) != 1:
            raise Rejected("OCR output is incomplete.")
        if data.get("images") and data["images"][0]:
            corrected = Path(data["images"][0]).resolve()
            if corrected.parent != self.work.resolve() or corrected.suffix != ".png":
                raise Rejected("Invalid corrected image.")
            from PIL import Image

            with Image.open(corrected) as prepared:
                if prepared.width * prepared.height > 16000000:
                    raise Rejected("Corrected image exceeds pixel budget.")
                prepared.convert("RGB").save(image)
        return normalize(data["pages"][0], width, height, engine)
