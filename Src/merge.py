"""
Merge RawRecords into CanonicalProfiles.

Match key: normalized email if present; else (normalized name + company) fallback.
Field-level winner: structured sources (recruiter_csv, ats_json) outrank
unstructured (resume, recruiter_notes). Within a tier, last-seen wins.
List fields (emails, phones, skills) are unioned, not overwritten.
"""
from collections import defaultdict
from schema import CanonicalProfile, FieldValue
from normalize import (
    normalize_phone_e164, normalize_skill, normalize_email,
)

SOURCE_TIER = {
    "recruiter_csv": 2, "ats_json": 2,   # structured = higher trust
    "resume": 1, "recruiter_notes": 1, "github": 1, "linkedin": 1,
}


def _group_key(rec):
    if rec.match_email:
        return ("email", rec.match_email)
    name = (rec.match_name or "").strip().lower()
    company = (rec.match_company or "").strip().lower()
    if name:
        return ("name_company", name, company)
    return ("unmatched", id(rec))


def group_records(raw_records):
    groups = defaultdict(list)
    for rec in raw_records:
        groups[_group_key(rec)].append(rec)
    return list(groups.values())


def _pick_scalar(values_with_meta):
    """values_with_meta: list of (value, source, method). Returns (value, confidence, provenance, conflicted)."""
    if not values_with_meta:
        return None, 0.0, [], False
    distinct = {v for v, _, _ in values_with_meta}
    provenance = [{"source": s, "method": m} for _, s, m in values_with_meta]
    if len(distinct) == 1:
        confidence = 0.9 if len(values_with_meta) > 1 else (
            0.7 if SOURCE_TIER.get(values_with_meta[0][1], 1) == 2 else 0.5
        )
        return values_with_meta[0][0], confidence, provenance, False
    # conflict: prefer highest tier, then last-seen
    best = max(values_with_meta, key=lambda t: SOURCE_TIER.get(t[1], 1))
    return best[0], 0.5, provenance, True


def merge_group(records, candidate_id):
    profile = CanonicalProfile(candidate_id=candidate_id)

    name_votes, email_set, phone_set = [], {}, {}
    company_votes, title_votes = [], []
    skill_map = defaultdict(set)  # canonical_skill -> set of sources

    for rec in records:
        rf = rec.raw_fields
        if "full_name" in rf:
            rv = rf["full_name"]
            name_votes.append((rv.value, rv.source, rv.method))
        for rv in rf.get("emails", []):
            e = normalize_email(rv.value) or rv.value
            email_set.setdefault(e, []).append((rv.source, rv.method))
        for rv in rf.get("phones", []):
            p = normalize_phone_e164(rv.value) or rv.value
            phone_set.setdefault(p, []).append((rv.source, rv.method))
        for rv in rf.get("skills", []):
            s = normalize_skill(rv.value)
            if s:
                skill_map[s].add((rv.source, rv.method))
        if "experience_current" in rf:
            rv = rf["experience_current"]
            company_votes.append((rv.value.get("company"), rv.source, rv.method))
            title_votes.append((rv.value.get("title"), rv.source, rv.method))

    # full_name
    if name_votes:
        val, conf, prov, _ = _pick_scalar(name_votes)
        profile.full_name = FieldValue(value=val, confidence=conf, provenance=prov)

    # emails / phones: unioned lists, confidence = max(per-value confidence)
    if email_set:
        emails_sorted = sorted(email_set.keys())
        prov = [{"source": s, "method": m} for srcs in email_set.values() for s, m in srcs]
        conf = 0.9 if any(len(v) > 1 for v in email_set.values()) else 0.7
        profile.emails = FieldValue(value=emails_sorted, confidence=conf, provenance=prov)
    if phone_set:
        phones_sorted = sorted(phone_set.keys())
        prov = [{"source": s, "method": m} for srcs in phone_set.values() for s, m in srcs]
        conf = 0.9 if any(len(v) > 1 for v in phone_set.values()) else 0.6
        profile.phones = FieldValue(value=phones_sorted, confidence=conf, provenance=prov)

    # current experience (company/title) -> folded into experience[] as one entry
    if company_votes or title_votes:
        company, c_conf, c_prov, _ = _pick_scalar([v for v in company_votes if v[0]])
        title, t_conf, t_prov, _ = _pick_scalar([v for v in title_votes if v[0]])
        if company or title:
            profile.experience.append({
                "company": company, "title": title, "start": None, "end": "present",
                "summary": None,
                "_confidence": round((c_conf + t_conf) / 2, 2) if (company and title) else max(c_conf, t_conf),
                "_provenance": c_prov + t_prov,
            })

    # skills
    for skill, srcs in sorted(skill_map.items()):
        conf = 0.9 if len(srcs) > 1 else (0.7 if any(SOURCE_TIER.get(s, 1) == 2 for s, _ in srcs) else 0.5)
        profile.skills.append({
            "name": skill, "confidence": conf,
            "sources": sorted({s for s, _ in srcs}),
        })

    # overall confidence: mean of populated top-level field confidences
    confs = [f.confidence for f in [profile.full_name, profile.emails, profile.phones] if f]
    confs += [s["confidence"] for s in profile.skills]
    profile.overall_confidence = round(sum(confs) / len(confs), 2) if confs else 0.0

    return profile


def merge_all(raw_records, id_prefix="cand"):
    groups = group_records(raw_records)
    profiles = []
    for i, group in enumerate(groups, start=1):
        candidate_id = f"{id_prefix}_{i:04d}"
        profiles.append(merge_group(group, candidate_id))
    return profiles
