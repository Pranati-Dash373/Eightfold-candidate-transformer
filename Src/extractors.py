"""
Extractors: each takes a raw source file/blob and returns a list[RawRecord].
Robust by design: missing/garbage files never crash the run, they just yield [].
"""
import csv
import json
import re
import os
from schema import RawRecord, RawValue
from normalize import normalize_email


def _rv(value, source, method):
    return RawValue(value=value, source=source, method=method)


def extract_csv(path: str):
    """Recruiter CSV export: name, email, phone, current_company, title."""
    records = []
    if not path or not os.path.exists(path):
        return records
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
                name = row.get("name") or row.get("full_name")
                email = row.get("email")
                phone = row.get("phone")
                company = row.get("current_company") or row.get("company")
                title = row.get("title")
                if not any([name, email, phone, company, title]):
                    continue  # skip fully empty rows rather than producing a junk record
                rf = {}
                if name:
                    rf["full_name"] = _rv(name, "recruiter_csv", "direct_field")
                if email:
                    rf["emails"] = [_rv(email, "recruiter_csv", "direct_field")]
                if phone:
                    rf["phones"] = [_rv(phone, "recruiter_csv", "direct_field")]
                if company or title:
                    rf["experience_current"] = _rv(
                        {"company": company or None, "title": title or None},
                        "recruiter_csv", "direct_field",
                    )
                records.append(RawRecord(
                    source="recruiter_csv", raw_fields=rf,
                    match_email=normalize_email(email) if email else None,
                    match_name=name or None, match_company=company or None,
                ))
    except Exception:
        return records  # malformed CSV -> degrade gracefully, no crash
    return records


def extract_ats_json(path: str):
    """ATS JSON blob with its own field names (does not match canonical names)."""
    records = []
    if not path or not os.path.exists(path):
        return records
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return records

    candidates = data if isinstance(data, list) else data.get("candidates", [data])
    for c in candidates:
        if not isinstance(c, dict):
            continue
        name = c.get("candidate_name") or c.get("name")
        email = c.get("contact_email") or c.get("email")
        phone = c.get("contact_phone") or c.get("phone")
        company = c.get("employer") or c.get("company")
        title = c.get("job_title") or c.get("title")
        skills = c.get("skill_tags") or c.get("skills") or []
        if not any([name, email, phone, company, title, skills]):
            continue
        rf = {}
        if name:
            rf["full_name"] = _rv(name, "ats_json", "direct_field")
        if email:
            rf["emails"] = [_rv(email, "ats_json", "direct_field")]
        if phone:
            rf["phones"] = [_rv(phone, "ats_json", "direct_field")]
        if company or title:
            rf["experience_current"] = _rv(
                {"company": company, "title": title}, "ats_json", "direct_field"
            )
        if skills:
            rf["skills"] = [_rv(s, "ats_json", "direct_field") for s in skills if s]
        records.append(RawRecord(
            source="ats_json", raw_fields=rf,
            match_email=normalize_email(email) if email else None,
            match_name=name or None, match_company=company or None,
        ))
    return records


_EMAIL_RE = re.compile(r"[\w\.\-+]+@[\w\-]+\.[\w\.\-]+")
_PHONE_RE = re.compile(r"(\+?\d[\d\-\s\(\)]{7,}\d)")


def _read_resume_text(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".pdf":
            import pdfplumber
            text = []
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    text.append(page.extract_text() or "")
            return "\n".join(text)
        elif ext == ".docx":
            import docx
            d = docx.Document(path)
            return "\n".join(p.text for p in d.paragraphs)
        elif ext == ".txt":
            with open(path, encoding="utf-8", errors="ignore") as f:
                return f.read()
    except Exception:
        return ""
    return ""


def extract_resume(path: str):
    """Resume PDF/DOCX prose: best-effort regex/section extraction."""
    records = []
    if not path or not os.path.exists(path):
        return records
    text = _read_resume_text(path)
    if not text.strip():
        return records  # unreadable/garbage file -> no record, no crash

    rf = {}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    name = lines[0] if lines and len(lines[0].split()) <= 5 and not _EMAIL_RE.search(lines[0]) else None
    if name:
        rf["full_name"] = _rv(name, "resume", "first_line_heuristic")

    emails = sorted(set(_EMAIL_RE.findall(text)))
    if emails:
        rf["emails"] = [_rv(e, "resume", "regex_extract") for e in emails]

    phones = sorted(set(m.strip() for m in _PHONE_RE.findall(text)))
    if phones:
        rf["phones"] = [_rv(p, "resume", "regex_extract") for p in phones]

    section_headers = {"summary", "skills", "experience", "education", "projects",
                        "certifications", "work history", "objective"}
    lines_lower = [l.lower().rstrip(":").strip() for l in lines]
    if "skills" in lines_lower:
        start = lines_lower.index("skills") + 1
        end = len(lines)
        for j in range(start, len(lines)):
            if lines_lower[j] in section_headers:
                end = j
                break
        chunk = " ".join(lines[start:end])
        parts = re.split(r"[,•·]", chunk)
        skills = [p.strip() for p in parts if p.strip() and len(p.strip()) < 40]
        if skills:
            rf["skills"] = [_rv(s, "resume", "section_parse") for s in skills]

    records.append(RawRecord(
        source="resume", raw_fields=rf,
        match_email=normalize_email(emails[0]) if emails else None,
        match_name=name,
    ))
    return records


def extract_notes(path: str):
    """Recruiter notes .txt: free text, low-confidence signal extraction only."""
    records = []
    if not path or not os.path.exists(path):
        return records
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        return records
    if not text.strip():
        return records

    rf = {}
    emails = sorted(set(_EMAIL_RE.findall(text)))
    if emails:
        rf["emails"] = [_rv(e, "recruiter_notes", "regex_extract") for e in emails]
    phones = sorted(set(m.strip() for m in _PHONE_RE.findall(text)))
    if phones:
        rf["phones"] = [_rv(p, "recruiter_notes", "regex_extract") for p in phones]

    name_match = re.search(r"(?:candidate|name)\s*[:\-]\s*(.+)", text, re.IGNORECASE)
    name = name_match.group(1).strip() if name_match else None
    if name:
        rf["full_name"] = _rv(name, "recruiter_notes", "regex_extract")

    if not rf:
        return records  # no extractable signal -> skip rather than emit an empty record

    records.append(RawRecord(
        source="recruiter_notes", raw_fields=rf,
        match_email=normalize_email(emails[0]) if emails else None,
        match_name=name,
    ))
    return records
