"""Bounded, non-executing inline LaTeX subset to editable Office Math (OMML).

Unsupported syntax is retained verbatim and reported; no external TeX engine runs.
"""

import re
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


class UnsupportedMath(ValueError):
    pass


SYMBOLS = dict(
    zip(
        "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi pi rho sigma tau upsilon phi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Phi Psi Omega".split(),
        "α β γ δ ε ζ η θ ι κ λ μ ν ξ π ρ σ τ υ φ χ ψ ω Γ Δ Θ Λ Ξ Π Σ Φ Ψ Ω".split(),
    )
)
SYMBOLS.update(
    times="×",
    cdot="·",
    pm="±",
    mp="∓",
    le="≤",
    leq="≤",
    ge="≥",
    geq="≥",
    ne="≠",
    neq="≠",
    approx="≈",
    infty="∞",
    partial="∂",
    nabla="∇",
    in_="∈",
    to="→",
    rightarrow="→",
    leftarrow="←",
    sum="∑",
    prod="∏",
    int="∫",
    ldots="…",
    cdots="⋯",
    langle="⟨",
    rangle="⟩",
)
SYMBOLS["in"] = SYMBOLS.pop("in_")


def node(name, children=()):
    value = OxmlElement("m:" + name)
    value.extend(children)
    return value


def literal(text):
    t = node("t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    return node("r", [t])


class Parser:
    def __init__(self, value):
        if not value or len(value) > 4096:
            raise UnsupportedMath("Formula size limit")
        self.tokens = re.findall(r"\\text\{[^{}]*\}|\\[a-zA-Z]+|\\.|[^\s]", value)
        self.index = 0
        self.depth = 0

    def take(self):
        if self.index >= len(self.tokens):
            raise UnsupportedMath("Missing formula argument")
        token = self.tokens[self.index]
        self.index += 1
        return token

    def peek(self):
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def sequence(self, end=None):
        self.depth += 1
        if self.depth > 32:
            raise UnsupportedMath("Formula nesting limit")
        values = []
        while self.peek() is not None and self.peek() != end:
            base = [] if not values and self.peek() in ("_", "^") else self.atom()
            scripts = {}
            while self.peek() in ("_", "^"):
                op = self.take()
                if op in scripts:
                    raise UnsupportedMath("Duplicate formula script")
                scripts[op] = self.atom()
            if scripts:
                tag = (
                    "sSubSup"
                    if len(scripts) == 2
                    else "sSub" if "_" in scripts else "sSup"
                )
                children = [node("e", base)]
                for op, name in (("_", "sub"), ("^", "sup")):
                    if op in scripts:
                        children.append(node(name, scripts[op]))
                base = [node(tag, children)]
            values.extend(base)
        if end is not None and self.take() != end:
            raise UnsupportedMath("Unbalanced formula")
        self.depth -= 1
        return values

    def atom(self):
        t = self.take()
        if t.startswith(r"\text{") and t.endswith("}"):
            run = literal(t[6:-1])
            props = node("rPr")
            style = node("sty")
            style.set(qn("m:val"), "p")
            props.append(style)
            run.insert(0, props)
            return [run]
        if t == "{":
            return self.sequence("}")
        if t in ("}", "_", "^", "$", "&", "#"):
            raise UnsupportedMath("Unsupported formula syntax")
        if not t.startswith("\\"):
            return [literal(t)]
        cmd = t[1:]
        if cmd in ("frac", "dfrac", "tfrac"):
            return [node("f", [node("num", self.atom()), node("den", self.atom())])]
        if cmd == "sqrt":
            degree = []
            if self.peek() == "[":
                self.take()
                degree = self.sequence("]")
            props = node("radPr")
            hidden = node("degHide")
            hidden.set(qn("m:val"), "0" if degree else "1")
            props.append(hidden)
            return [node("rad", [props, node("deg", degree), node("e", self.atom())])]
        if cmd in ("text", "mathrm", "operatorname", "mathbf", "mathit"):
            if self.peek() != "{":
                raise UnsupportedMath("Missing font group")
            values = self.atom()
            for value in values:
                runs = (
                    [value] if value.tag == qn("m:r") else list(value.iter(qn("m:r")))
                )
                for run in runs:
                    props = node("rPr")
                    style = node("sty")
                    style.set(
                        qn("m:val"),
                        "b" if cmd == "mathbf" else "i" if cmd == "mathit" else "p",
                    )
                    props.append(style)
                    run.insert(0, props)
            return values
        if cmd in ("left", "right"):
            delimiter = self.take()
            if delimiter == ".":
                return []
            if delimiter in (
                "(",
                ")",
                "[",
                "]",
                "|",
                r"\{",
                r"\}",
                r"\langle",
                r"\rangle",
            ):
                return [
                    literal(
                        SYMBOLS.get(delimiter[1:], delimiter[-1])
                        if delimiter.startswith("\\")
                        else delimiter
                    )
                ]
            raise UnsupportedMath("Unsupported delimiter")
        if cmd in SYMBOLS:
            return [literal(SYMBOLS[cmd])]
        if cmd in ("{", "}", "%", "_", "|"):
            return [literal(cmd)]
        if cmd in (",", ";", ":", "!"):
            return [literal(" ")]
        if cmd in ("sin", "cos", "tan", "log", "ln", "exp", "min", "max", "lim"):
            return [literal(cmd)]
        raise UnsupportedMath("Unsupported formula command")


def equation(value):
    parser = Parser(value)
    return node("oMath", parser.sequence())


DELIMITERS = re.compile(
    r"(?<!\\)\$\$([\s\S]+?)\$\$|(?<![\\$])\$([^$\n]+?)\$(?!\$)|\\\(([\s\S]+?)\\\)"
)


def segments(text):
    offset = 0
    for match in DELIMITERS.finditer(text):
        if match.start() > offset:
            yield text[offset : match.start()], None, False
        source = next(v for v in match.groups() if v is not None)
        try:
            # Do not reinterpret ordinary prose between currency signs as math.
            if not re.search(r"[\\_^=<>+*/]", source) and not re.fullmatch(
                r"[A-Za-z]|\d+(?:\.\d+)?", source.strip()
            ):
                raise UnsupportedMath("Ambiguous dollar-delimited text")
            yield match.group(), equation(source), False
        except (UnsupportedMath, RecursionError):
            yield match.group(), None, True
        offset = match.end()
    if offset < len(text):
        yield text[offset:], None, False


def unsupported(text):
    return any(failed for _, _, failed in segments(text))
