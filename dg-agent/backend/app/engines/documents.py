"""Document text extraction (PDF text layer -> OCR fallback, images via OCR) and SDS parsing.

Uploaded content is always handled as DATA. It is never interpreted as instructions;
text that looks like an attempt to instruct an AI system is flagged for the reviewer.
"""
from __future__ import annotations

import io
import re
import shutil
import subprocess

from . import textutil as tu

try:  # optional dependencies; reported honestly if unavailable
    import pytesseract
    from PIL import Image
except Exception:  # pragma: no cover
    pytesseract = None
    Image = None

ALLOWED_TYPES = {
    "application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
    "image/tiff": ".tif", "text/plain": ".txt",
}
MAGIC = {b"%PDF": "application/pdf", b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg",
         b"RIFF": "image/webp", b"II*\x00": "image/tiff", b"MM\x00*": "image/tiff"}

INJECTION_PATTERNS = [
    r"ignore (all|any|the)? ?(previous|prior|above) (instructions|rules)",
    r"disregard (the )?(system|previous) (prompt|instructions)",
    r"you are now", r"act as (an?|the) ", r"system prompt", r"mark (this|the) (shipment|cargo) as (approved|compliant|safe)",
    r"approve (this|the) (shipment|cargo|declaration)", r"تجاهل (جميع )?التعليمات",
]


def sniff_type(data: bytes, declared: str | None) -> str | None:
    for magic, ctype in MAGIC.items():
        if data.startswith(magic):
            return ctype
    if declared == "text/plain":
        try:
            data.decode("utf-8")
            return "text/plain"
        except UnicodeDecodeError:
            return None
    return None


def ocr_available() -> bool:
    return pytesseract is not None and shutil.which("tesseract") is not None


def _ocr_image(img, langs: str = "eng+ara") -> str:
    return pytesseract.image_to_string(img, lang=langs)


def extract_text(data: bytes, ctype: str, ocr: bool = True) -> dict:
    method, text, warnings = None, "", []
    if ctype == "text/plain":
        return {"text": data.decode("utf-8", "replace"), "method": "plain_text", "warnings": []}
    if ctype == "application/pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
            method = "pdf_text_layer"
        except Exception as e:
            warnings.append(f"PDF text extraction failed: {e.__class__.__name__}")
        if len(text.strip()) < 40 and shutil.which("pdftotext"):
            try:
                out = subprocess.run(["pdftotext", "-layout", "-", "-"], input=data, capture_output=True, timeout=60)
                if len(out.stdout.strip()) > len(text.strip()):
                    text, method = out.stdout.decode("utf-8", "replace"), "pdftotext"
            except Exception:
                pass
        if len(text.strip()) < 40:
            if ocr and ocr_available():
                try:
                    import pypdfium2 as pdfium
                    pdf = pdfium.PdfDocument(data)
                    pages = []
                    for i in range(min(len(pdf), 20)):
                        pages.append(_ocr_image(pdf[i].render(scale=2).to_pil()))
                    text, method = "\n".join(pages), "ocr"
                    warnings.append("Text obtained by OCR — values must be checked against the original document.")
                except Exception as e:
                    warnings.append(f"OCR failed: {e.__class__.__name__}")
            else:
                warnings.append("Scanned PDF and OCR unavailable — no text extracted.")
    elif ctype.startswith("image/"):
        if ocr and ocr_available():
            text = _ocr_image(Image.open(io.BytesIO(data)))
            method = "ocr"
            warnings.append("Text obtained by OCR — values must be checked against the original image.")
        else:
            warnings.append("OCR unavailable — image stored without text extraction.")
    return {"text": text, "method": method, "warnings": warnings}


def detect_injection(text: str) -> list[str]:
    found = []
    low = text.lower()
    for p in INJECTION_PATTERNS:
        m = re.search(p, low)
        if m:
            found.append(m.group(0))
    return found


# ------------------------------------------------------------------ SDS parsing
SECTION_RE = re.compile(r"(?im)^\s*(?:section|القسم)\s*(\d{1,2})\b|^\s*(\d{1,2})\s*[.:)]\s+[A-Z؀-ۿ]")
FIELD_PATTERNS = {
    "product_name": [r"(?im)^\s*(?:product name|trade name|product identifier|اسم المنتج)\s*[:\-]\s*(.+)$"],
    "manufacturer": [r"(?im)^\s*(?:manufacturer|supplier|company|المورد|الشركة المصنعة)\s*[:\-]\s*(.+)$"],
    "proper_shipping_name": [r"(?im)(?:un proper shipping name|proper shipping name|shipping name|الاسم الرسمي للشحن)\s*[:\-]\s*(.+)$"],
    "hazard_class": [r"(?im)(?:transport hazard class(?:\(es\))?|hazard class|class|رتبة الخطر|الفئة)\s*[:\-]\s*([0-9](?:\.[0-9])?(?:\s*\(\s*[0-9.,\s]+\))?)"],
    "packing_group": [r"(?im)(?:packing group|مجموعة التعبئة)\s*[:\-]\s*(I{1,3}|[123]|-|n/?a|none)\b"],
    "marine_pollutant": [r"(?im)(?:marine pollutant|environmental hazards?|ملوث بحري)\s*[:\-]\s*(yes|no|نعم|لا|[a-z ]+)"],
    "flash_point": [r"(?im)flash\s*point\s*[:\-]?\s*([<>]?\s*-?\d+(?:[.,]\d+)?\s*°?\s*[CF])"],
    "revision_date": [r"(?im)(?:revision date|date of revision|تاريخ المراجعة)\s*[:\-]\s*([0-9./\-]+)"],
}
UN_LABEL_RE = re.compile(r"(?im)(?:un\s*(?:number|no\.?)|id\s*no\.?|رقم الأمم المتحدة)\s*[:\-]?\s*((?:UN|ID)?\s*[0-9OIlS]{4})")
NOT_REGULATED_RE = re.compile(r"(?i)\bnot (?:regulated|classified) (?:as dangerous|for transport)|\bnot dangerous goods\b")


def split_sections(text: str) -> dict[int, str]:
    sections: dict[int, str] = {}
    marks = [(m.start(), int(m.group(1) or m.group(2))) for m in SECTION_RE.finditer(text)]
    marks = [(pos, n) for pos, n in marks if 1 <= n <= 16]
    for i, (pos, n) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        sections.setdefault(n, "")
        sections[n] += text[pos:end]
    return sections


def _first(patterns, text):
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1).strip()
    return None


def parse_sds(text: str) -> dict:
    sections = split_sections(text)
    s14 = sections.get(14, "")
    findings, warnings = [], []
    fields = {k: _first(v, s14 if k in ("proper_shipping_name", "hazard_class", "packing_group", "marine_pollutant")
                       else text) for k, v in FIELD_PATTERNS.items()}
    if not fields["product_name"]:
        fields["product_name"] = _first(FIELD_PATTERNS["product_name"], sections.get(1, text))
    un_vals = []
    for m in UN_LABEL_RE.finditer(s14 or text):
        un, notes = tu.normalize_un(m.group(1))
        if un:
            un_vals.append(un)
            warnings += notes
    for un, notes in tu.find_un_numbers(s14 or ""):
        if un not in un_vals:
            un_vals.append(un)
            warnings += notes
    distinct_un = sorted(set(un_vals))
    hclass = fields["hazard_class"]
    sub = []
    if hclass and "(" in hclass:
        sub = [s.strip() for s in re.findall(r"[0-9](?:\.[0-9])?", hclass.split("(", 1)[1])]
    cas = tu.find_cas_numbers(sections.get(3, text))
    hstat = sorted(set(re.findall(r"\bH[2-4]\d{2}\b", text)))
    not_reg = bool(NOT_REGULATED_RE.search(s14 or ""))

    if not sections:
        warnings.append("SDS section headings not recognised — document may not be a 16-section SDS or OCR quality is poor.")
    if 14 not in sections:
        findings.append({"severity": "high", "finding": "Section 14 (Transport information) not found."})
    if len(distinct_un) > 1:
        findings.append({"severity": "high", "finding": f"Contradictory UN numbers in Section 14: {distinct_un}. "
                         "May reflect different modes/variants or an error — verify."})
    if 14 in sections and not distinct_un and not not_reg:
        findings.append({"severity": "high", "finding": "Section 14 present but no UN number and no explicit "
                         "'not regulated' statement."})
    if not_reg and hstat:
        findings.append({"severity": "medium", "finding": "SDS states not regulated for transport while GHS hazard "
                         "statements are present. GHS and transport classifications differ — confirm the transport "
                         "classification basis."})
    if not_reg and distinct_un:
        findings.append({"severity": "high", "finding": "SDS both lists a UN number and states 'not regulated' — contradictory."})
    bad_cas = [c["cas"] for c in cas if not c["checksum_valid"]]
    if bad_cas:
        findings.append({"severity": "medium", "finding": f"CAS number(s) failing check digit (possible OCR/typing "
                         f"error): {bad_cas}."})
    if not fields["revision_date"]:
        findings.append({"severity": "low", "finding": "SDS revision date not found — currency of SDS cannot be confirmed."})
    if hclass and not re.fullmatch(r"[1-9](\.[1-6])?", tu.normalize_class(hclass) or ""):
        findings.append({"severity": "medium", "finding": f"Hazard class '{hclass}' is not a valid class/division."})

    return {
        "fields": {**fields, "un_numbers": distinct_un, "hazard_class": tu.normalize_class(hclass),
                   "subsidiary_hazards": sub, "packing_group": tu.normalize_pg(fields["packing_group"]),
                   "cas_numbers": cas, "h_statements": hstat, "states_not_regulated": not_reg},
        "sections_found": sorted(sections), "findings": findings, "warnings": warnings,
        "contains_arabic": bool(re.search(r"[؀-ۿ]", text)),
        "extraction_disclaimer": "Automatically extracted values are unverified evidence. Confirm each value "
                                 "against the original document.",
    }
