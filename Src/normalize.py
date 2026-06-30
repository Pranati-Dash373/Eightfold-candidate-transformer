"""Pure, testable normalization functions. Never invent data: unparseable -> None."""
import re

COUNTRY_ALIASES = {
    "united states": "US", "usa": "US", "u.s.a.": "US", "us": "US", "united states of america": "US",
    "india": "IN", "bharat": "IN",
    "united kingdom": "GB", "uk": "GB", "england": "GB",
    "canada": "CA", "germany": "DE", "france": "FR", "australia": "AU",
    "singapore": "SG", "japan": "JP", "china": "CN", "brazil": "BR",
}

SKILL_ALIASES = {
    "js": "javascript", "javascript": "javascript", "node": "node.js", "nodejs": "node.js",
    "node.js": "node.js", "py": "python", "python3": "python", "python": "python",
    "reactjs": "react", "react.js": "react", "react": "react",
    "golang": "go", "go": "go",
    "ml": "machine learning", "machine learning": "machine learning",
    "k8s": "kubernetes", "kubernetes": "kubernetes",
    "postgres": "postgresql", "postgresql": "postgresql",
    "tf": "tensorflow", "tensorflow": "tensorflow",
}

MONTHS = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "sept": "09", "oct": "10", "nov": "11", "dec": "12",
}


def normalize_country(raw: str):
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    if len(raw) == 2 and raw.isalpha():
        return raw.upper()
    return COUNTRY_ALIASES.get(raw.lower())


def normalize_phone_e164(raw: str, default_region_cc: str = "1"):
    """Best-effort E.164 normalization. Returns None if not confidently parseable."""
    if not raw or not isinstance(raw, str):
        return None
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("+"):
        core = re.sub(r"\D", "", digits)
        if 8 <= len(core) <= 15:
            return "+" + core
        return None
    core = re.sub(r"\D", "", digits)
    if len(core) == 10:
        return f"+{default_region_cc}{core}"
    if len(core) == 11 and core.startswith("1") and default_region_cc == "1":
        return f"+{core}"
    if 8 <= len(core) <= 15:
        # ambiguous without country context; refuse to guess a leading country code
        return None
    return None


def normalize_date_yyyymm(raw):
    """Parse free-form dates/ranges into YYYY-MM. Returns None (not a guess) if unparseable."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    s = raw.strip().lower()
    if s in ("present", "current", "now", "ongoing", ""):
        return "present" if s != "" else None

    m = re.match(r"^(\d{4})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    m = re.match(r"^([a-zA-Z]{3,9})\.?\s+(\d{4})$", s)
    if m:
        mon = m.group(1)[:3].lower()
        if mon in MONTHS:
            return f"{m.group(2)}-{MONTHS[mon]}"

    m = re.match(r"^(\d{1,2})[/-](\d{4})$", s)
    if m:
        mm = int(m.group(1))
        if 1 <= mm <= 12:
            return f"{m.group(2)}-{mm:02d}"

    m = re.match(r"^(\d{4})$", s)
    if m:
        return None  # year-only is too ambiguous to call a month -> leave null, don't guess

    return None


def normalize_skill(raw: str):
    if not raw or not isinstance(raw, str):
        return None
    key = raw.strip().lower()
    return SKILL_ALIASES.get(key, key)


def normalize_email(raw: str):
    if not raw or not isinstance(raw, str):
        return None
    e = raw.strip().lower()
    if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e):
        return e
    return None
