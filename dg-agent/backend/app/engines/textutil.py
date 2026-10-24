"""Normalisation helpers: UN numbers, CAS numbers, Proper Shipping Names, OCR repair."""
from __future__ import annotations

import re
import unicodedata

UN_RE = re.compile(r"\b(UN|ID)\s*[-:]?\s*([0-9OIlS]{4})\b", re.IGNORECASE)
CAS_RE = re.compile(r"\b(\d{2,7})-(\d{2})-(\d)\b")
ROMAN_PG = {"I": "I", "II": "II", "III": "III", "1": "I", "2": "II", "3": "III"}
# Common OCR confusions inside numeric fields.
_OCR_DIGIT_MAP = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "S": "5"})
_SPELLING_VARIANTS = [("SULFUR", "SULPHUR"), ("ALUMINUM", "ALUMINIUM"), ("CESIUM", "CAESIUM")]


def normalize_un(value: str | None) -> tuple[str | None, list[str]]:
    """Return ('UN1203', notes). Notes record any OCR-style correction so a human can confirm it."""
    notes: list[str] = []
    if not value:
        return None, notes
    raw = value.strip()
    m = re.fullmatch(r"(?i)(UN|ID)?\s*[-:]?\s*([0-9OIlS]{4})", raw)
    if not m:
        return None, [f"'{raw}' is not a valid UN/ID number format (expected e.g. UN1203)."]
    prefix = (m.group(1) or "UN").upper()
    digits = m.group(2)
    fixed = digits.translate(_OCR_DIGIT_MAP)
    if fixed != digits:
        notes.append(f"Possible OCR/typing error corrected: '{digits}' read as '{fixed}'. Confirm against the document.")
    if not fixed.isdigit():
        return None, notes + [f"'{raw}' contains non-numeric characters."]
    return f"{prefix}{fixed}", notes


def find_un_numbers(text: str) -> list[tuple[str, list[str]]]:
    out, seen = [], set()
    for m in UN_RE.finditer(text or ""):
        un, notes = normalize_un(m.group(0))
        if un and un not in seen:
            seen.add(un)
            out.append((un, notes))
    return out


def cas_checksum_ok(cas: str) -> bool:
    m = CAS_RE.fullmatch(cas.strip())
    if not m:
        return False
    digits = (m.group(1) + m.group(2))[::-1]
    total = sum((i + 1) * int(d) for i, d in enumerate(digits))
    return total % 10 == int(m.group(3))


def find_cas_numbers(text: str) -> list[dict]:
    out, seen = [], set()
    for m in CAS_RE.finditer(text or ""):
        cas = m.group(0)
        if cas in seen:
            continue
        seen.add(cas)
        out.append({"cas": cas, "checksum_valid": cas_checksum_ok(cas)})
    return out


def normalize_pg(value: str | None) -> str | None:
    if value is None:
        return None
    v = str(value).strip().upper().replace("PG", "").replace("PACKING GROUP", "").strip()
    if v in ("", "-", "N/A", "NA", "NONE"):
        return None
    return ROMAN_PG.get(v)


def normalize_class(value: str | None) -> str | None:
    if value is None:
        return None
    v = str(value).strip().upper().replace("CLASS", "").replace("DIVISION", "").strip()
    v = v.split("(")[0].strip()
    return v or None


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").upper()
    s = re.sub(r"[^\w%.,()\- ]+", " ", s)
    s = re.sub(r"\s*,\s*", ", ", s)
    return re.sub(r"\s+", " ", s).strip(" ,")


def canonical_spelling(s: str) -> str:
    s = norm_text(s)
    for a, b in _SPELLING_VARIANTS:
        s = s.replace(a, b)
    return s


def _is_upper_word(w: str) -> bool:
    letters = [c for c in w if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def psn_alternatives(psn: str) -> list[str]:
    """Split a DGL name into its authorised name cores.

    The upper-case part is the Proper Shipping Name; lower-case text is qualifying
    description. Alternatives are separated by a lower-case ' or '.
    """
    cores = []
    for seg in re.split(r"\s+or\s+", psn):
        words, core = seg.split(), []
        for w in words:
            if _is_upper_word(w) or (not any(c.isalpha() for c in w) and core):
                core.append(w)
            else:
                break
        if core:
            cores.append(norm_text(" ".join(core)))
    return cores or [norm_text(psn)]


def strip_technical_name(declared: str) -> tuple[str, str | None]:
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", declared.strip())
    if m:
        return m.group(1), m.group(2)
    return declared, None
