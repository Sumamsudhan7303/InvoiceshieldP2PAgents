"""
InvoiceShield P2P - FastAPI backend (PRODUCTION)
- Reads the uploaded PDF for real (pdfplumber, falls back to pypdf)
- Extracts invoice no, vendor, GSTIN, amount, PO, HSN, GST rate, date
- Runs 10 validation agents on the extracted data and returns a full report
Run:  python src/fastapi_server.py      (serves on http://127.0.0.1:8000)
Needs: pip install fastapi uvicorn python-multipart pdfplumber
"""
import hashlib
import io
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

app = FastAPI(title="InvoiceShield P2P")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_PDF_BYTES = 15 * 1024 * 1024

# ============================================================================
# MASTER DATA (replace with Google Sheets / SAP later)
# ============================================================================
VENDOR_MASTER: Dict[str, Dict[str, Any]] = {
    '27AABCT5055K1Z0': {'name': 'Priya Electrical', 'approved': True, 'blacklisted': False, 'contract_valid': True},
    '33AAFCT7891M1Z2': {'name': 'Techware Solutions', 'approved': True, 'blacklisted': False, 'contract_valid': True},
    '06AACPB8765R3Z1': {'name': 'Bangalore IT', 'approved': False, 'blacklisted': True, 'contract_valid': False},
    '28AACPM5678R1Z0': {'name': 'Metro Supplies', 'approved': True, 'blacklisted': False, 'contract_valid': True},
    '14AABCT1234K1Z0': {'name': 'Global Traders', 'approved': True, 'blacklisted': False, 'contract_valid': True},
    '29AAXPM9999R1Z0': {'name': 'Premium Components', 'approved': True, 'blacklisted': False, 'contract_valid': True},
    '15AABCT5555R1Z0': {'name': 'Quick Parts', 'approved': True, 'blacklisted': False, 'contract_valid': True},
}

# Our own (buyer) GSTINs - never treated as the vendor's GSTIN
BUYER_GSTINS: set = set()

HSN_GST_MAP = {
    "85023090": 18,
    "84733080": 18,
    "84714090": 18,
    "39269090": 5,
}

AUDIT_FINDINGS = {
    '27AABCT5055K1Z0': {"status": "CLEAN", "findings": []},
    '33AAFCT7891M1Z2': {"status": "CLEAN", "findings": []},
    '06AACPB8765R3Z1': {"status": "HIGH_RISK", "findings": ["Previous payment delays", "Quality issues"]},
    '28AACPM5678R1Z0': {"status": "CLEAN", "findings": []},
    '14AABCT1234K1Z0': {"status": "MEDIUM_RISK", "findings": ["One quality complaint in Aug 2026"]},
    '29AAXPM9999R1Z0': {"status": "CLEAN", "findings": []},
    '15AABCT5555R1Z0': {"status": "CLEAN", "findings": []},
}

# Used ONLY to fill a field the PDF text did not contain (flagged in the report)
KNOWN_SAMPLES = {
    "invoice_normal.pdf": {"vendor": "Priya Electrical", "gst": "27AABCT5055K1Z0", "amount": 42500, "po": "PO/2026/0001", "hsn": "85023090", "gst_rate": 18},
    "invoice_with_issues.pdf": {"vendor": "Techware Solutions", "gst": "33AAFCT7891M1Z2", "amount": 160000, "po": "PO/2026/0002", "hsn": "84733080", "gst_rate": 18},
    "invoice_blacklisted.pdf": {"vendor": "Bangalore IT", "gst": "06AACPB8765R3Z1", "amount": 75000, "po": "PO/2026/0003", "hsn": "84714090", "gst_rate": 18},
    "invoice_priya_again.pdf": {"vendor": "Priya Electrical", "gst": "27AABCT5055K1Z0", "amount": 51000, "po": "PO/2026/0004", "hsn": "85023090", "gst_rate": 18},
    "invoice_invalid_hsn.pdf": {"vendor": "Metro Supplies", "gst": "28AACPM5678R1Z0", "amount": 30000, "po": "PO/2026/0005", "hsn": "99999999", "gst_rate": 18},
    "invoice_duplicate_po.pdf": {"vendor": "Priya Electrical", "gst": "27AABCT5055K1Z0", "amount": 45000, "po": "PO/2026/0001", "hsn": "85023090", "gst_rate": 18},
    "invoice_wrong_gst.pdf": {"vendor": "Global Traders", "gst": "14AABCT1234K1Z0", "amount": 25000, "po": "PO/2026/0006", "hsn": "39269090", "gst_rate": 5},
    "invoice_high_value.pdf": {"vendor": "Premium Components", "gst": "29AAXPM9999R1Z0", "amount": 750000, "po": "PO/2026/0007", "hsn": "84733080", "gst_rate": 18},
    "invoice_expired_vendor.pdf": {"vendor": "Bangalore IT", "gst": "06AACPB8765R3Z1", "amount": 55000, "po": "PO/2026/0008", "hsn": "84714090", "gst_rate": 18},
    "invoice_missing_po.pdf": {"vendor": "Quick Parts", "gst": "15AABCT5555R1Z0", "amount": 20000, "po": None, "hsn": "85023090", "gst_rate": 18},
}

# ============================================================================
# IN-MEMORY STATE
# ============================================================================
PRICE_HISTORY: Dict[str, List[Dict[str, Any]]] = {}
USED_POS: set = set()
INVOICE_HISTORY: List[Dict[str, Any]] = []
SEEN_FILE_HASHES: set = set()
SEEN_INVOICE_KEYS: set = set()

# ============================================================================
# PDF TEXT EXTRACTION
# ============================================================================
def extract_pdf_text(data: bytes):
    """Return (text, page_count). Tries pdfplumber, then pypdf."""
    have_engine = False
    errors: List[str] = []

    try:
        import pdfplumber  # type: ignore
        have_engine = True
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = len(pdf.pages)
            text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        if text.strip():
            return text, pages
    except ImportError:
        pass
    except Exception as e:  # corrupt / encrypted
        errors.append(f"pdfplumber: {e}")

    try:
        from pypdf import PdfReader  # type: ignore
        have_engine = True
        reader = PdfReader(io.BytesIO(data))
        pages = len(reader.pages)
        text = "\n".join((pg.extract_text() or "") for pg in reader.pages)
        if text.strip():
            return text, pages
    except ImportError:
        pass
    except Exception as e:
        errors.append(f"pypdf: {e}")

    if not have_engine:
        raise RuntimeError("No PDF reader installed. Run:  pip install pdfplumber")
    if errors:
        raise ValueError("; ".join(errors))
    return "", 0


# ============================================================================
# INVOICE FIELD PARSER
# ============================================================================
NUM = r'(\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)'
GSTIN_RE = re.compile(r'\b(\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b')
GSTIN_FULL = re.compile(r'^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$')
VALID_RATES = {0, 0.25, 3, 5, 12, 18, 28}


def _num(s: str) -> float:
    return float(s.replace(',', ''))


def _clean_number(v: float):
    return int(v) if float(v).is_integer() else round(v, 2)


def find_amount(lines: List[str]):
    labels = ["grand total", "total amount", "invoice total", "invoice amount",
              "amount payable", "net payable", "net amount", "total"]
    for label in labels:
        for line in lines:
            low = line.lower()
            if label not in low:
                continue
            if label == "total" and any(x in low for x in ("sub", "tax", "gst", "qty", "quantity", "words")):
                continue
            m = re.search(re.escape(label) + r'[^\d\n]{0,30}' + NUM, line, re.I)
            if m:
                return _clean_number(_num(m.group(1)))
    return None


def find_gstin(text: str):
    found = [g for g in dict.fromkeys(GSTIN_RE.findall(text)) if g not in BUYER_GSTINS]
    for g in found:
        if g in VENDOR_MASTER:
            return g
    return found[0] if found else None


def find_invoice_number(text: str):
    for m in re.finditer(r'invoice\s*(?:no|number|num|#)\.?\s*[:#\-]?\s*([A-Z0-9][A-Z0-9/\-_.]{1,30})', text, re.I):
        v = m.group(1).rstrip('.-/')
        if re.search(r'\d', v):
            return v
    m = re.search(r'\b(INV(?:[-/_][A-Z0-9]|\d)[A-Z0-9/\-_]*)\b', text)
    return m.group(1) if m else None


def find_po(text: str):
    m = re.search(r'\b(PO/\d{2,4}/\d+)\b', text, re.I)
    if m:
        return m.group(1).upper()
    for m in re.finditer(r'(?:\bP\.?O\.?\b|purchase\s*order)\s*(?:no|number|num|#|ref(?:erence)?)?\.?\s*[:#\-]?\s*([A-Z0-9][A-Z0-9/\-_]{2,30})', text, re.I):
        v = m.group(1).rstrip('.-/')
        if re.search(r'\d', v):
            return v.upper()
    return None


def find_hsn(text: str) -> List[str]:
    found = re.findall(r'HSN(?:\s*/\s*SAC)?(?:\s*Code)?\s*[:\-]?\s*(\d{4,8})\b', text, re.I)
    if not found and re.search(r'\bHSN\b', text, re.I):
        found = re.findall(r'(?<![\d,.])(\d{8})(?![\d,.])', text)
    return list(dict.fromkeys(found))


def find_gst_rate(text: str):
    pat = r'{}[^\d\n]{{0,15}}(\d{{1,2}}(?:\.\d+)?)\s*%'
    m = re.search(pat.format('IGST'), text, re.I)
    if m:
        return _clean_number(float(m.group(1)))
    c = re.search(pat.format('CGST'), text, re.I)
    s = re.search(pat.format('SGST'), text, re.I)
    if c and s:
        return _clean_number(float(c.group(1)) + float(s.group(1)))
    m = re.search(pat.format('GST'), text, re.I)
    if m:
        return _clean_number(float(m.group(1)))
    for m in re.finditer(r'(\d{1,2}(?:\.\d+)?)\s*%', text):
        if float(m.group(1)) in VALID_RATES:
            return _clean_number(float(m.group(1)))
    return None


def find_date(text: str):
    m = re.search(r'date\s*[:\-]?\s*(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})', text, re.I)
    return m.group(1) if m else None


def find_vendor(text: str, lines: List[str], gst: Optional[str]):
    for line in lines:
        m = re.match(r'^(?:vendor|supplier|seller|sold\s*by|bill\s*from|from)(?:\s*name)?\s*[:\-]\s*(.+)$', line, re.I)
        if m:
            name = re.split(r'\s+GSTIN?\b|\s{2,}', m.group(1).strip())[0].strip(' ,;-')
            if 2 < len(name) <= 60:
                return name
    low = text.lower()
    for rec in VENDOR_MASTER.values():
        if rec['name'].lower() in low:
            return rec['name']
    if gst and gst in VENDOR_MASTER:
        return VENDOR_MASTER[gst]['name']
    for line in lines[:6]:
        if 2 < len(line) <= 60 and not re.search(r'invoice|date|gst|bill|page|\d{5,}', line, re.I):
            return line
    return None


def parse_invoice(text: str, filename: str) -> Dict[str, Any]:
    text = text.replace('\u20b9', ' Rs ').replace('\xa0', ' ')
    text = re.sub(r'[ \t]+', ' ', text)
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    gst = find_gstin(text)
    hsn_list = find_hsn(text)
    parsed: Dict[str, Any] = {
        "invoice_number": find_invoice_number(text),
        "vendor": find_vendor(text, lines, gst),
        "gst": gst,
        "amount": find_amount(lines),
        "po": find_po(text),
        "hsn": hsn_list[0] if hsn_list else None,
        "hsn_list": hsn_list,
        "gst_rate": find_gst_rate(text),
        "date": find_date(text),
    }

    # Fill only what the PDF text did not contain (and tell the user)
    fallback_fields: List[str] = []
    sample = KNOWN_SAMPLES.get((filename or "").lower())
    if sample:
        for key in ("vendor", "gst", "amount", "po", "hsn", "gst_rate"):
            if parsed.get(key) is None and sample.get(key) is not None:
                parsed[key] = sample[key]
                fallback_fields.append(key)
        if "hsn" in fallback_fields:
            parsed["hsn_list"] = [parsed["hsn"]]
    parsed["fallback_fields"] = fallback_fields
    return parsed


# ============================================================================
# 10 VALIDATION AGENTS
# ============================================================================
def _add(bucket: List[Dict[str, str]], type_: str, severity: str, message: str):
    bucket.append({"type": type_, "severity": severity, "message": message})


def validate_invoice(filename: str, file_hash: str, p: Dict[str, Any]) -> Dict[str, Any]:
    issues: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []
    agents: List[Dict[str, Any]] = []

    vendor = p.get("vendor") or "Unknown"
    gst = p.get("gst")
    amount = p.get("amount")
    po = p.get("po")
    hsn = p.get("hsn")
    hsn_list = p.get("hsn_list") or ([hsn] if hsn else [])
    rate = p.get("gst_rate")
    inv_no = p.get("invoice_number")
    rec = VENDOR_MASTER.get(gst) if gst else None

    def agent(idx: int, name: str, status: str, message: str):
        agents.append({"id": idx, "name": name, "status": status, "message": message})

    # 1. Vendor verification
    if not gst:
        _add(issues, "GSTIN_MISSING", "HIGH", "Vendor GSTIN not found in invoice")
        agent(1, "Vendor Verification", "FAIL", "GSTIN not found - vendor cannot be verified")
    elif rec is None:
        _add(issues, "VENDOR_NOT_IN_MASTER", "HIGH", f"Vendor {vendor} ({gst}) is not in vendor master")
        agent(1, "Vendor Verification", "FAIL", "Vendor not in master")
    elif rec["blacklisted"]:
        _add(issues, "VENDOR_BLACKLISTED", "CRITICAL", f"Vendor {rec['name']} is blacklisted")
        agent(1, "Vendor Verification", "FAIL", "Vendor is blacklisted")
    elif not rec["contract_valid"]:
        _add(issues, "VENDOR_EXPIRED", "CRITICAL", f"Vendor {rec['name']} contract expired")
        agent(1, "Vendor Verification", "FAIL", "Vendor contract expired")
    elif not rec["approved"]:
        _add(issues, "VENDOR_NOT_APPROVED", "HIGH", f"Vendor {rec['name']} is not approved")
        agent(1, "Vendor Verification", "FAIL", "Vendor not approved")
    elif rec["name"].lower() not in (p.get("_text_lower") or rec["name"].lower()):
        _add(warnings, "VENDOR_NAME_MISMATCH", "MEDIUM", f"GSTIN belongs to '{rec['name']}' but invoice shows '{vendor}'")
        agent(1, "Vendor Verification", "WARN", "GSTIN and vendor name do not match")
    else:
        agent(1, "Vendor Verification", "PASS", f"{rec['name']} is approved with a valid contract")

    # 2. GST validation
    if not gst:
        agent(2, "GST Validation", "FAIL", "No GSTIN to validate")
    elif not GSTIN_FULL.match(gst) or not (1 <= int(gst[:2]) <= 38):
        _add(issues, "GST_INVALID", "HIGH", f"GSTIN {gst} has an invalid format or state code")
        agent(2, "GST Validation", "FAIL", "Invalid GSTIN format / state code")
    else:
        agent(2, "GST Validation", "PASS", f"GSTIN {gst} format and state code {gst[:2]} are valid")

    # 3. Amount check
    if amount is None:
        _add(issues, "AMOUNT_MISSING", "HIGH", "Invoice total amount not found")
        agent(3, "Amount Check", "FAIL", "Total amount not found")
    elif amount <= 0:
        _add(issues, "AMOUNT_INVALID", "HIGH", "Amount must be positive")
        agent(3, "Amount Check", "FAIL", "Amount must be positive")
    elif amount > 10_000_000:
        _add(warnings, "AMOUNT_SUSPICIOUS", "HIGH", "Amount exceeds Rs 1 Cr limit")
        agent(3, "Amount Check", "WARN", "Amount exceeds Rs 1 Cr limit")
    else:
        agent(3, "Amount Check", "PASS", f"Amount Rs {amount:,} is within limits")

    # 4. PO verification
    if not po:
        _add(warnings, "PO_MISSING", "HIGH", "PO reference missing")
        agent(4, "PO Verification", "WARN", "PO reference missing")
    elif po in USED_POS:
        _add(issues, "PO_DUPLICATE", "CRITICAL", f"PO {po} already used")
        agent(4, "PO Verification", "FAIL", f"PO {po} already used on an earlier invoice")
    else:
        agent(4, "PO Verification", "PASS", f"PO {po} is unused")

    # 5. HSN validation
    if not hsn_list:
        _add(warnings, "HSN_MISSING", "HIGH", "HSN code not found in invoice")
        agent(5, "HSN Validation", "WARN", "HSN code not found")
    else:
        bad = [h for h in hsn_list if len(h) not in (4, 6, 8) or len(set(h)) == 1]
        unknown = [h for h in hsn_list if h not in HSN_GST_MAP and h not in bad]
        if bad:
            _add(issues, "HSN_INVALID", "HIGH", f"Invalid/dummy HSN code: {', '.join(bad)}")
            agent(5, "HSN Validation", "FAIL", f"Invalid HSN {', '.join(bad)}")
        elif unknown:
            _add(warnings, "HSN_WARNING", "MEDIUM", f"HSN {', '.join(unknown)} not in standard catalog")
            agent(5, "HSN Validation", "WARN", f"HSN {', '.join(unknown)} not in catalog")
        else:
            agent(5, "HSN Validation", "PASS", f"HSN {', '.join(hsn_list)} found in catalog")

    # 6. GST rate check
    if rate is None:
        _add(warnings, "GST_RATE_NOT_FOUND", "LOW", "GST rate not found on invoice")
        agent(6, "GST Rate Check", "WARN", "GST rate not found on invoice")
    else:
        wrong = [(h, HSN_GST_MAP[h]) for h in hsn_list if h in HSN_GST_MAP and abs(HSN_GST_MAP[h] - rate) > 0.01]
        if wrong:
            for h, exp in wrong:
                _add(warnings, "GST_RATE_MISMATCH", "MEDIUM", f"HSN {h}: expected {exp}% but invoice shows {rate}%")
            agent(6, "GST Rate Check", "WARN", f"Rate {rate}% does not match HSN reference")
        else:
            agent(6, "GST Rate Check", "PASS", f"GST rate {rate}% is consistent")

    # 7. ITC eligibility
    itc_eligible = False
    itc_amount = 0
    if rec and rec["approved"] and not rec["blacklisted"] and amount and amount >= 500:
        itc_eligible = True
        used_rate = rate if rate is not None else 18
        itc_amount = round(amount * used_rate / 100, 2)
        agent(7, "ITC Eligibility", "PASS", f"Eligible - estimated ITC Rs {itc_amount:,.2f} at {used_rate}%")
    else:
        reason = "vendor not approved / unknown" if not (rec and rec["approved"] and not rec["blacklisted"]) else "amount below ITC threshold"
        agent(7, "ITC Eligibility", "WARN", f"Not eligible - {reason}")

    # 8. Duplicate check
    dup_msgs: List[str] = []
    if file_hash in SEEN_FILE_HASHES:
        dup_msgs.append("Same PDF file was already uploaded")
    if inv_no and gst and f"{gst}|{inv_no}" in SEEN_INVOICE_KEYS:
        dup_msgs.append(f"Invoice {inv_no} from this vendor already processed")
    if po and amount is not None:
        for h in INVOICE_HISTORY:
            if h.get("vendor") == vendor and h.get("amount") == amount and h.get("po") == po:
                dup_msgs.append("Exact duplicate (vendor + amount + PO) found")
                break
    if dup_msgs:
        for msg in dup_msgs:
            _add(issues, "INVOICE_DUPLICATE", "CRITICAL", msg)
        agent(8, "Duplicate Check", "FAIL", dup_msgs[0])
    else:
        agent(8, "Duplicate Check", "PASS", "No duplicate invoice found")

    # 9. Vendor audit trail
    audit = AUDIT_FINDINGS.get(gst or "", {"status": "UNKNOWN", "findings": []})
    if audit["status"] == "HIGH_RISK":
        for f in audit["findings"]:
            _add(issues, "AUDIT_HIGH_RISK", "HIGH", f"Audit: {f}")
        agent(9, "Audit Trail", "FAIL", "High risk - " + "; ".join(audit["findings"]))
    elif audit["status"] == "MEDIUM_RISK":
        for f in audit["findings"]:
            _add(warnings, "AUDIT_MEDIUM_RISK", "MEDIUM", f"Audit: {f}")
        agent(9, "Audit Trail", "WARN", "Medium risk - " + "; ".join(audit["findings"]))
    elif audit["status"] == "UNKNOWN":
        agent(9, "Audit Trail", "WARN", "No audit record for this vendor")
    else:
        agent(9, "Audit Trail", "PASS", "Clean audit record")

    # 10. Price cop
    cost_warnings: List[Dict[str, Any]] = []
    price_key = f"{vendor}|{hsn}"
    prior = [x["price"] for x in PRICE_HISTORY.get(price_key, [])]
    if prior and amount:
        avg = sum(prior) / len(prior)
        var = (amount - avg) / avg * 100 if avg else 0
        base = {"previous_avg": round(avg), "current": amount, "variance": f"{var:.1f}%"}
        if var > 20:
            cost_warnings.append({"type": "PRICE_CRITICAL", "severity": "HIGH", "message": f"Price spike detected: {var:.1f}% increase", **base})
        elif var > 10:
            cost_warnings.append({"type": "PRICE_WARNING", "severity": "MEDIUM", "message": f"Price {var:.1f}% higher than average", **base})
        elif var < -10:
            cost_warnings.append({"type": "PRICE_DECREASE", "severity": "LOW", "message": f"Price {abs(var):.1f}% lower than average", **base})
    if cost_warnings:
        top = cost_warnings[0]
        agent(10, "Price Cop Alert", "WARN" if top["severity"] != "LOW" else "PASS", top["message"])
    else:
        agent(10, "Price Cop Alert", "PASS", "No price deviation" if prior else "First invoice for this vendor/HSN - baseline set")

    # ------------------------------------------------------------------ decision
    amt = amount or 0
    critical = any(i["severity"] == "CRITICAL" for i in issues)
    flagged = (
        bool(issues)
        or any(w["severity"] != "LOW" for w in warnings)
        or any(c["severity"] in ("HIGH", "MEDIUM") for c in cost_warnings)
    )
    if critical:
        decision, level = "AUTO_REJECT", "SYSTEM"
    elif amt > 500_000:
        decision, level = "HUMAN_REVIEW", "PLANT_HEAD"
    elif amt >= 100_000:
        decision, level = "HUMAN_REVIEW", "PROCUREMENT_HEAD"
    elif amt >= 50_000 or flagged:
        decision, level = "HUMAN_REVIEW", "FINANCE_MANAGER"
    else:
        decision, level = "AUTO_APPROVE", "SYSTEM"

    # register state (rejected invoices do not consume PO / pollute price baseline)
    if decision != "AUTO_REJECT":
        if po:
            USED_POS.add(po)
        if amount:
            PRICE_HISTORY.setdefault(price_key, []).append(
                {"price": amount, "invoice": inv_no or filename, "date": datetime.now().isoformat()}
            )
        if inv_no and gst:
            SEEN_INVOICE_KEYS.add(f"{gst}|{inv_no}")
    SEEN_FILE_HASHES.add(file_hash)

    confidence = 0.97 - 0.10 * len(issues) - 0.03 * len(warnings) - (0.10 if p.get("fallback_fields") else 0)
    confidence = round(max(0.40, min(0.99, confidence)), 2)

    return {
        "decision": decision,
        "approval_level": level,
        "issues_found": issues,
        "warnings": warnings,
        "cost_warnings": cost_warnings,
        "agent_results": agents,
        "confidence_score": confidence,
        "agents_executed": len(agents),
        "vendor_audit": audit["status"],
        "itc_eligible": itc_eligible,
        "itc_amount": itc_amount,
    }


# ============================================================================
# ROUTES
# ============================================================================
@app.get("/health")
async def health_check():
    return {
        "status": "RUNNING",
        "backend": "FastAPI",
        "agents": 10,
        "invoices_processed": len(INVOICE_HISTORY),
    }


@app.get("/system-stats")
async def system_stats():
    n = len(INVOICE_HISTORY)
    approved = sum(1 for h in INVOICE_HISTORY if h["decision"] == "AUTO_APPROVE")
    review = sum(1 for h in INVOICE_HISTORY if h["decision"] == "HUMAN_REVIEW")
    rejected = sum(1 for h in INVOICE_HISTORY if h["decision"] == "AUTO_REJECT")
    vendors: Dict[str, Dict[str, Any]] = {}
    for h in INVOICE_HISTORY:
        v = vendors.setdefault(h["vendor"] or "Unknown", {"name": h["vendor"] or "Unknown", "invoices": 0, "amount": 0})
        v["invoices"] += 1
        v["amount"] += h["amount"] or 0
    top = sorted(vendors.values(), key=lambda x: x["amount"], reverse=True)[:3]
    return {
        "invoices_processed": n,
        "unique_pos": len(USED_POS),
        "price_tracking_entries": len(PRICE_HISTORY),
        "auto_approved": approved,
        "human_review": review,
        "auto_rejected": rejected,
        "total_value": sum(h["amount"] or 0 for h in INVOICE_HISTORY),
        "avg_processing_ms": round(sum(h["processing_ms"] for h in INVOICE_HISTORY) / n) if n else 0,
        "success_rate": round((approved + review) / n * 100, 1) if n else 0,
        "top_vendors": top,
        "status": "RUNNING",
    }


@app.post("/reset-system")
async def reset_system():
    PRICE_HISTORY.clear()
    USED_POS.clear()
    INVOICE_HISTORY.clear()
    SEEN_FILE_HASHES.clear()
    SEEN_INVOICE_KEYS.clear()
    return {"status": "SYSTEM RESET", "timestamp": datetime.now().isoformat()}


@app.post("/upload-invoice")
async def upload_invoice(file: UploadFile = File(...)):
    t0 = time.perf_counter()
    filename = file.filename or "invoice.pdf"
    try:
        if not filename.lower().endswith(".pdf"):
            return JSONResponse(status_code=400, content={"error": "Only PDF files are supported"})

        data = await file.read()
        if not data:
            return JSONResponse(status_code=400, content={"error": "Uploaded file is empty"})
        if len(data) > MAX_PDF_BYTES:
            return JSONResponse(status_code=413, content={"error": "PDF is larger than 15 MB"})
        if b"%PDF" not in data[:1024]:
            return JSONResponse(status_code=400, content={"error": "File is not a valid PDF"})

        try:
            text, pages = await run_in_threadpool(extract_pdf_text, data)
        except RuntimeError as e:
            return JSONResponse(status_code=500, content={"error": str(e)})
        except Exception as e:
            return JSONResponse(status_code=400, content={"error": f"Could not read PDF: {e}"})

        if len(text.strip()) < 15:
            return JSONResponse(status_code=422, content={
                "error": "No readable text in this PDF (looks like a scanned image). Upload a text-based invoice PDF."
            })

        file_hash = hashlib.sha256(data).hexdigest()
        parsed = parse_invoice(text, filename)
        parsed["_text_lower"] = text.lower()
        result = validate_invoice(filename, file_hash, parsed)

        processing_ms = round((time.perf_counter() - t0) * 1000)
        uploaded_at = datetime.now().isoformat()
        invoice_number = parsed.get("invoice_number") or filename.rsplit(".", 1)[0].upper()

        INVOICE_HISTORY.append({
            "filename": filename,
            "invoice_number": invoice_number,
            "vendor": parsed.get("vendor"),
            "amount": parsed.get("amount"),
            "po": parsed.get("po"),
            "gst": parsed.get("gst"),
            "hsn": parsed.get("hsn"),
            "decision": result["decision"],
            "approval_level": result["approval_level"],
            "uploaded_at": uploaded_at,
            "processing_ms": processing_ms,
        })

        result.update({
            "invoice_number": invoice_number,
            "vendor": parsed.get("vendor"),
            "amount": parsed.get("amount"),
            "po": parsed.get("po"),
            "gst": parsed.get("gst"),
            "hsn": parsed.get("hsn"),
            "gst_rate": parsed.get("gst_rate"),
            "date": parsed.get("date"),
            "fallback_fields": parsed.get("fallback_fields", []),
            "pages": pages,
            "pdf_text_preview": text[:1500],
            "processing_ms": processing_ms,
            "uploaded_at": uploaded_at,
        })
        return JSONResponse(status_code=200, content=result)

    except Exception as e:  # never crash the server
        return JSONResponse(status_code=500, content={"error": f"Server error: {e}"})


@app.get("/invoice-history")
async def get_history():
    """Always a LIST, newest first."""
    return list(reversed(INVOICE_HISTORY))


@app.get("/price-history")
async def get_price_history():
    return {"total_tracked": len(PRICE_HISTORY), "history": PRICE_HISTORY}


if __name__ == "__main__":
    import uvicorn

    print("InvoiceShield backend -> http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")