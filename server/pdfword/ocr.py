"""Bounded adapters for a separately provisioned OCR process; no document uploads."""

import json
import os
import re
import signal
import shutil
import subprocess
import time
import unicodedata
from pathlib import Path
from model import Rejected, box, plain, table_from_html


def suppress_duplicate_text_regions(blocks):
    """Remove duplicate OCR regions, never deduplicate text across the page.

    Layout detectors can return both a complete multiline region and its lines.
    Require spatial containment, exact normalized line sequences and matching
    vertical positions. A repeated phrase elsewhere, a partial line, a changed
    number, or uncertain wrapping retains its separate region.
    """
    if len(blocks) > 2000:
        return blocks
    compact = lambda value: "".join(unicodedata.normalize("NFKC", value).split())
    area = lambda bounds: (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
    candidates = [i for i, b in enumerate(blocks)
                  if b["kind"] in {"paragraph", "list"} and b.get("text", "").strip()]
    lines = {i: [compact(line) for line in blocks[i]["text"].splitlines() if line.strip()]
             for i in candidates}
    kept, removed = [], set()
    for index in sorted(candidates, key=lambda i: -area(blocks[i]["bbox"])):
        small = blocks[index]["bbox"]
        small_area = area(small)
        if small_area <= 0:
            kept.append(index)
            continue
        for parent in kept:
            large = blocks[parent]["bbox"]
            overlap = max(0, min(small[2], large[2]) - max(small[0], large[0])) * max(
                0, min(small[3], large[3]) - max(small[1], large[1]))
            if overlap < .98 * small_area:
                continue
            union = small_area + area(large) - overlap
            if lines[index] == lines[parent] and overlap >= .9 * union:
                removed.add(index)
                break
            count, total = len(lines[index]), len(lines[parent])
            if not 0 < count < total:
                continue
            # A wrapped paragraph's logical lines have unequal visual heights.
            # Its first two long, single-line children can instead be anchored
            # using their own measured height. Never apply this to short labels.
            child_height = small[3] - small[1]
            if (count == 1 and 60 <= len(lines[index][0]) <= 1000
                    and small[2] - small[0] >= .7 * (large[2] - large[0])
                    and child_height < .3 * (large[3] - large[1])):
                for start in range(min(2, total)):
                    a, b = lines[index][0], lines[parent][start]
                    if any(len(line) > 1.25 * len(a) for line in lines[parent][:start]):
                        continue
                    if abs(small[1] - large[1] - start * child_height) > .55 * child_height:
                        continue
                    exact = a == b
                    if exact:
                        removed.add(index)
                        break
                    if start == 0 and a[:10] == b[:10] and a[-10:] == b[-10:]:
                        # Do not silently pick between conflicting words/numbers.
                        blocks[parent]["ocr_overlap_review"] = True
                if index in removed:
                    break
            line_height = (large[3] - large[1]) / total
            for start in range(total - count + 1):
                if lines[parent][start:start + count] != lines[index]:
                    continue
                expected_top = large[1] + start * line_height
                expected_bottom = expected_top + count * line_height
                if max(abs(small[1] - expected_top), abs(small[3] - expected_bottom)) <= .55 * line_height:
                    removed.add(index)
                    break
            if index in removed:
                break
        if index not in removed:
            kept.append(index)
    return [b for i, b in enumerate(blocks) if i not in removed]


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
            # Dense tables carry a real page-space height even when the model
            # does not return font metrics. Bound the fallback by row height.
            size = max(6, min(10, (bounds[3] - bounds[1]) / (b["rows"] * 1.2)))
            for cell in b["cells"]:
                cell["size"] = size
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
    return suppress_duplicate_text_regions(result)


class OCR:
    def __init__(self, work, cancel=None, engine=None):
        self.work = Path(work)
        self.cancel = cancel
        self.engine = engine or os.environ.get("PDFWORD_OCR_ENGINE", "auto")
        self.python = os.environ.get("PDFWORD_OCR_PYTHON")
        self.model_root = os.environ.get("PDFWORD_MODEL_ROOT")
        self.calls = 0
        self.last_engine = None
        self.last_page_size = None
        self.processes = {}

    def close(self):
        for process in self.processes.values():
            self._stop(process)
        self.processes.clear()

    @staticmethod
    def _stop(process):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait()
        if process.stdin:
            process.stdin.close()

    def _request(self, python, script, request, env, started, budget):
        # Keep CPU preprocessing and one inference model alive within this job.
        # Switching engines releases the previous model before loading another.
        key = (
            python,
            script,
            (
                json.loads(request.read_text())["engine"]
                if script == "ocr_process.py"
                else "cpu"
            ),
        )
        for previous in list(self.processes):
            if previous != key and previous[1] == script:
                self._stop(self.processes.pop(previous))
        process = self.processes.get(key)
        if process is None or process.poll() is not None:
            if process is not None:
                self._stop(process)
            with (self.work / f"process-{self.calls}-{script}.log").open("ab") as log:
                process = subprocess.Popen(
                    [python, str(Path(__file__).with_name(script)), "--serve"],
                    stdin=subprocess.PIPE,
                    stdout=log,
                    stderr=log,
                    env=env,
                    text=True,
                    start_new_session=True,
                )
            self.processes[key] = process
        done = Path(str(request) + ".done")
        done.unlink(missing_ok=True)
        try:
            process.stdin.write(str(request) + "\n")
            process.stdin.flush()
            while not done.exists():
                if self.cancel and Path(self.cancel).exists():
                    raise Rejected("Conversion cancelled.")
                if time.monotonic() - started > budget:
                    raise Rejected("OCR timed out. Try a shorter document.")
                if process.poll() is not None:
                    raise Rejected("OCR process stopped before completing the page.")
                time.sleep(0.05)
            if done.stat().st_size > 1024 or json.loads(done.read_text()) != {
                "ok": True
            }:
                raise Rejected("OCR could not finish. Retry or choose a clearer scan.")
        except BaseException:
            self._stop(self.processes.pop(key))
            raise
        finally:
            done.unlink(missing_ok=True)

    def recognize(self, image, width, height, complex_layout=False):
        if not self.python or not self.model_root:
            raise Rejected("This page needs OCR. The OCR worker is not configured.")
        self.last_engine = None
        self.last_page_size = None
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
                if Path(command[1]).name in {"ocr_process.py", "prepare_image.py"}:
                    self._request(
                        command[0], Path(command[1]).name, request, env, started, budget
                    )
                    continue
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
        quality_path = Path(str(output) + ".quality.json")
        quality = {}
        if quality_path.exists():
            if quality_path.stat().st_size > 16384:
                raise Rejected("Invalid image preparation report.")
            quality = json.loads(quality_path.read_text())
            if not isinstance(quality, dict):
                raise Rejected("Invalid image preparation report.")
        angle = quality.get("orientation_applied", 0)
        if type(angle) is not int or angle not in (0, 90, 180, 270):
            raise Rejected("Invalid corrected page orientation.")
        if angle in (90, 270):
            width, height = height, width
        blocks = normalize(data["pages"][0], width, height, engine)
        self.last_page_size = (width, height)
        if blocks and quality.get("orientation_rejected"):
            blocks[0]["ocr_orientation_review"] = True
        return blocks
