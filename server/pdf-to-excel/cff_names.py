"""Bounded CFF1 custom charset reader, isolated research prototype.

Adobe Technical Note 5176, INDEX and Charset formats 0/1/2:
https://adobe-type-tools.github.io/font-tech-notes/pdfs/5176.CFF.pdf
Only glyph names are read. No charstring program is executed or changed.
"""

from pdfminer.pdffont import CFFFont


def top_dictionary(data):
    result, stack = {}, []
    pos = 0
    while pos < len(data):
        byte = data[pos]
        pos += 1
        if byte <= 21:
            operator = byte
            if byte == 12:
                operator = (12, data[pos])
                pos += 1
            if operator in result:
                raise ValueError("Duplicate CFF dictionary operator")
            result[operator] = stack
            stack = []
            continue
        if 32 <= byte <= 246:
            value = byte - 139
        elif 247 <= byte <= 254:
            value = (
                (byte - 247) * 256 + data[pos] + 108
                if byte <= 250
                else -(byte - 251) * 256 - data[pos] - 108
            )
            pos += 1
        elif byte in (28, 29):
            size = 2 if byte == 28 else 4
            if pos + size > len(data):
                raise ValueError("Truncated CFF integer")
            value = int.from_bytes(data[pos : pos + size], "big", signed=True)
            pos += size
        elif byte == 30:
            # Non-integer fields are not used as offsets. Validate their
            # bounded terminator without evaluating floating-point expressions.
            terminated = False
            for _ in range(32):
                pair = data[pos]
                pos += 1
                for nibble in (pair >> 4, pair & 15):
                    if nibble == 15:
                        terminated = True
                        break
                    if nibble == 13:
                        raise ValueError("Reserved CFF real nibble")
                if terminated:
                    break
            if not terminated:
                raise ValueError("Unterminated CFF real")
            value = None
        else:
            raise ValueError("Reserved CFF operand")
        stack.append(value)
        if len(stack) > 48:
            raise ValueError("CFF operand budget exceeded")
    if stack:
        raise ValueError("Unused CFF operands")
    return result


def glyph_names(raw):
    if not isinstance(raw, bytes) or not 4 <= len(raw) <= 2_000_000:
        return None
    if (
        raw[0] != 1
        or raw[1] != 0
        or not 4 <= raw[2] <= len(raw)
        or not 1 <= raw[3] <= 4
    ):
        return None

    def number(pos, size):
        if type(pos) is not int or pos < 0 or pos + size > len(raw):
            raise ValueError("CFF field outside file")
        return int.from_bytes(raw[pos : pos + size], "big")

    def index(pos, limit):
        count = number(pos, 2)
        if count == 0:
            return [], pos + 2
        if count > limit:
            raise ValueError("CFF index budget exceeded")
        width = number(pos + 2, 1)
        if not 1 <= width <= 4:
            raise ValueError("Invalid CFF offset width")
        base = pos + 3 + width * (count + 1)
        offsets = [number(pos + 3 + i * width, width) for i in range(count + 1)]
        if (
            offsets[0] != 1
            or any(b < a for a, b in zip(offsets, offsets[1:]))
            or base + offsets[-1] - 1 > len(raw)
        ):
            raise ValueError("Invalid CFF index offsets")
        return [
            raw[base + a - 1 : base + b - 1] for a, b in zip(offsets, offsets[1:])
        ], base + offsets[-1] - 1

    try:
        names, pos = index(raw[2], 1)
        dicts, pos = index(pos, 1)
        strings, pos = index(pos, 2048)
        if len(names) != 1 or len(dicts) != 1 or not 1 <= len(dicts[0]) <= 4096:
            return None
        top = top_dictionary(dicts[0])
        if (12, 30) in top:
            return None  # CID-keyed font: charset entries are not glyph SIDs.
        charset = top.get(15, [0])
        chars = top.get(17, [0])
        if (
            len(charset) != 1
            or len(chars) != 1
            or type(charset[0]) is not int
            or type(chars[0]) is not int
        ):
            return None
        if charset[0] <= 2 or chars[0] <= 4:
            return None  # Predefined charsets remain outside this repair.
        programs, _ = index(chars[0], 1024)
        if not 1 <= len(programs) <= 1024:
            return None
        format = number(charset[0], 1)
        if format not in (0, 1, 2):
            return None
        remaining = len(programs) - 1
        cursor = charset[0] + 1
        sids = []
        while len(sids) < remaining:
            first = number(cursor, 2)
            cursor += 2
            left = number(cursor, format) if format else 0
            cursor += format
            if len(sids) + left + 1 > remaining or first + left > 65535:
                return None
            sids.extend(range(first, first + left + 1))
        if len(set(sids)) != len(sids) or 0 in sids:
            return None
        result = set()
        for sid in sids:
            if sid < len(CFFFont.STANDARD_STRINGS):
                name = CFFFont.STANDARD_STRINGS[sid]
            else:
                custom_index = sid - len(CFFFont.STANDARD_STRINGS)
                if (
                    not 0 <= custom_index < len(strings)
                    or not 1 <= len(strings[custom_index]) <= 127
                ):
                    return None
                name = strings[custom_index].decode("ascii")
            if not name or name in result:
                return None
            result.add(name)
        return result
    except (ValueError, TypeError, IndexError, KeyError, OverflowError, AssertionError):
        return None
