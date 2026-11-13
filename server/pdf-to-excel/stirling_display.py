"""Small fail-closed formatter for vetted Stirling XLSX display formats.

Explicit formats reproduce the supported XLSX display subset. General returns
canonical value text, not a claim about width-dependent Excel display. Neither
mode establishes the original PDF semantics.
For example, source '(0.0)' may already have become numeric zero with a two-
section negative format upstream. Its lost parentheses cannot be recovered here.
Not a general Excel format engine: unsupported formats raise DisplayError.
"""

import datetime
import math
import re
from decimal import ROUND_HALF_UP, Context, Decimal, InvalidOperation, localcontext


class DisplayError(ValueError):
    """The supported subset cannot establish a faithful display string."""


DATE_FORMATS = {
    "mm\\/dd\\/yyyy": "%m/%d/%Y",
    "mm/dd/yyyy": "%m/%d/%Y",
    "dd/mm/yyyy": "%d/%m/%Y",
    "yyyy-mm-dd": "%Y-%m-%d",
}
NUMBER = re.compile(
    r'(?P<currency>"[$€£¥]"|\\[$€£¥])?(?P<integer>0|#,##0)(?P<decimal>\.0{1,10})?(?P<percent>%)?\Z'
)


def _decimal(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise DisplayError("Unsupported numeric type")
    if isinstance(value, float) and not math.isfinite(value):
        raise DisplayError("Non-finite number")
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise DisplayError("Non-finite number")
        if number and abs(number.adjusted()) > 20:
            raise DisplayError("Numeric exponent outside supported range")
        if len(number.as_tuple().digits) > 100:
            raise DisplayError("Numeric precision exceeds bounded input")
        with localcontext(Context(prec=100)):
            normalized = number.normalize()
        if len(normalized.as_tuple().digits) > 15 or number.copy_abs() >= Decimal(
            "1e15"
        ):
            raise DisplayError(
                "Numeric precision cannot be established; use source text"
            )
        if number and abs(number.adjusted()) > 20:
            raise DisplayError("Numeric exponent outside supported range")
        return number
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise DisplayError("Invalid or over-precision number") from exc


def _section(text):
    parentheses = text.startswith("(") and text.endswith(")")
    if parentheses:
        text = text[1:-1]
    minus = text.startswith("-")
    if minus:
        text = text[1:]
    if parentheses and minus:
        raise DisplayError("Ambiguous sign format")
    match = NUMBER.fullmatch(text)
    if not match or (match["currency"] and match["percent"]):
        raise DisplayError("Unsupported Excel number format")
    currency = match["currency"]
    return (
        currency[1] if currency else "",
        match["integer"] == "#,##0",
        len(match["decimal"]) - 1 if match["decimal"] else 0,
        bool(match["percent"]),
        parentheses,
        minus,
    )


def display_text(value, number_format="General"):
    """Return literal text for the strict supported XLSX display subset."""
    if not isinstance(number_format, str) or not 1 <= len(number_format) <= 128:
        raise DisplayError("Invalid number format")
    if isinstance(value, str):
        # Never parse a string ID, date or formula-looking string as a number.
        return value
    if isinstance(value, bool):
        if number_format != "General":
            raise DisplayError("Unsupported boolean format")
        return "TRUE" if value else "FALSE"
    if isinstance(value, (datetime.datetime, datetime.date)):
        if number_format not in DATE_FORMATS:
            raise DisplayError("Unsupported date format")
        if isinstance(value, datetime.datetime) and (
            value.tzinfo is not None or value.time() != datetime.time()
        ):
            raise DisplayError("Date format would hide time or timezone")
        if (value.year, value.month, value.day) < (1900, 3, 1):
            raise DisplayError(
                "Early Excel dates have ambiguous leap-day serialization"
            )
        return value.strftime(DATE_FORMATS[number_format])
    if value is None:
        raise DisplayError("Blank cells must be omitted by caller")
    number = _decimal(value)
    if number_format == "General":
        # General depends on precision/width and can switch to scientific form.
        # Return canonical value text for short integers, not a rendered-cell claim.
        if number != number.to_integral_value() or number.copy_abs() >= Decimal("1e10"):
            raise DisplayError("General value outside conservative canonical subset")
        return str(int(number))
    parts = number_format.split(";")
    if not 1 <= len(parts) <= 3 or any(not p for p in parts):
        raise DisplayError("Unsupported format sections")
    sections = [_section(p) for p in parts]  # Validate even currently unused sections.
    index = (
        2
        if number == 0 and len(parts) == 3
        else 1
        if number < 0 and len(parts) >= 2
        else 0
    )
    currency, grouping, places, percent, parens, minus = sections[index]
    if (parens or minus) and index != 1:
        raise DisplayError("Explicit signs only supported in negative section")
    with localcontext(Context(prec=40)):
        magnitude = abs(number) * (100 if percent else 1)
        rounded = magnitude.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
        if number != 0 and rounded == 0:
            raise DisplayError(
                "Nonzero value rounds to zero; display sign is ambiguous"
            )
        text = format(rounded, f",.{places}f" if grouping else f".{places}f")
    text = currency + text + ("%" if percent else "")
    if number < 0:
        if parens:
            text = "(" + text + ")"
        elif minus or len(parts) == 1:
            text = "-" + text
        # With two sections, a bare negative section intentionally hides sign.
    return text
