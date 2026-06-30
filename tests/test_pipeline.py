import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from normalize import normalize_phone_e164, normalize_date_yyyymm, normalize_skill, normalize_country
from extractors import extract_csv, extract_ats_json, extract_resume, extract_notes
from merge import merge_all
from project import project, validate, DEFAULT_CONFIG

SAMPLES = os.path.join(os.path.dirname(__file__), "..", "sample_inputs")


def test_phone_normalization():
    assert normalize_phone_e164("9876543210") == "+19876543210"
    assert normalize_phone_e164("+91-9876500000") == "+919876500000"
    assert normalize_phone_e164("not a phone") is None
    assert normalize_phone_e164(None) is None


def test_date_normalization():
    assert normalize_date_yyyymm("Jan 2022") == "2022-01"
    assert normalize_date_yyyymm("2022-01-15") == "2022-01"
    assert normalize_date_yyyymm("Present") == "present"
    assert normalize_date_yyyymm("2022") is None  # year-only -> too ambiguous, no guess
    assert normalize_date_yyyymm("garbage") is None


def test_skill_canonicalization():
    assert normalize_skill("JS") == "javascript"
    assert normalize_skill("python3") == "python"
    assert normalize_skill("Some Unmapped Tool") == "some unmapped tool"  # passthrough, not dropped


def test_country_normalization():
    assert normalize_country("United States") == "US"
    assert normalize_country("in") == "IN"
    assert normalize_country("Wakanda") is None


def test_missing_source_file_does_not_crash():
    assert extract_csv("/no/such/file.csv") == []
    assert extract_ats_json("/no/such/file.json") == []
    assert extract_resume("/no/such/resume.pdf") == []
    assert extract_notes("/no/such/notes.txt") == []


def test_corrupt_resume_does_not_crash():
    corrupt = os.path.join(SAMPLES, "resume_corrupt.pdf")
    # should not raise, should just return [] or a record with no fields
    result = extract_resume(corrupt)
    assert isinstance(result, list)


def test_empty_notes_skipped():
    empty = os.path.join(SAMPLES, "notes_empty.txt")
    assert extract_notes(empty) == []


def test_merge_resolves_conflicting_phones_as_union():
    csv_recs = extract_csv(os.path.join(SAMPLES, "recruiter.csv"))
    ats_recs = extract_ats_json(os.path.join(SAMPLES, "ats.json"))
    profiles = merge_all(csv_recs + ats_recs)
    asha = next(p for p in profiles if p.full_name and p.full_name.value == "Asha Mehta")
    # CSV and ATS gave different phone numbers for Asha -> both should be kept (union), not silently dropped
    assert len(asha.phones.value) == 2
    # conflicting scalar-ish situation should not produce an over-confident single value
    assert asha.phones.confidence <= 0.9


def test_projection_respects_on_missing_omit():
    csv_recs = extract_csv(os.path.join(SAMPLES, "recruiter.csv"))
    profiles = merge_all(csv_recs)
    cfg = dict(DEFAULT_CONFIG)
    cfg["fields"] = [{"path": "headline", "from": "headline", "type": "string"}]
    cfg["on_missing"] = "omit"
    out = project(profiles[0], cfg)
    assert "headline" not in out  # omitted, not null


def test_validate_flags_missing_required_field():
    csv_recs = extract_csv(os.path.join(SAMPLES, "recruiter.csv"))
    profiles = merge_all(csv_recs)
    cfg = {"fields": [{"path": "headline", "from": "headline", "type": "string", "required": True}],
           "on_missing": "null", "include_confidence": False, "include_provenance": False}
    out = project(profiles[0], cfg)
    errs = validate(out, cfg)
    assert any("headline" in e for e in errs)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {e}")
    print(f"\n{len(tests)-failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
