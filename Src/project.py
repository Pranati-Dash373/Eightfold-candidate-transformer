"""
Projection layer: reads a runtime config and reshapes a CanonicalProfile into
the requested output JSON. Keeps a clean separation from the canonical model --
the canonical profile is never mutated here.
"""
import re
from normalize import normalize_phone_e164, normalize_skill

DEFAULT_CONFIG = {
    "fields": [
        {"path": "candidate_id", "from": "candidate_id", "type": "string", "required": True},
        {"path": "full_name", "from": "full_name", "type": "string"},
        {"path": "emails", "from": "emails", "type": "string[]"},
        {"path": "phones", "from": "phones", "type": "string[]", "normalize": "E164"},
        {"path": "headline", "from": "headline", "type": "string"},
        {"path": "years_experience", "from": "years_experience", "type": "number"},
        {"path": "skills", "from": "skills", "type": "object[]"},
        {"path": "experience", "from": "experience", "type": "object[]"},
        {"path": "education", "from": "education", "type": "object[]"},
        {"path": "overall_confidence", "from": "overall_confidence", "type": "number"},
    ],
    "include_confidence": True,
    "include_provenance": True,
    "on_missing": "null",
}


def _get_path(profile_dict, path_expr: str):
    """Small path resolver supporting 'a', 'a.b', 'a[0]', 'a[0].b', and the
    list-flatten form 'a[].b' (returns [item['b'] for item in a])."""
    flatten_match = re.match(r"^([^\.\[\]]+)\[\]\.(.+)$", path_expr)
    if flatten_match:
        list_field, sub_field = flatten_match.groups()
        items = profile_dict.get(list_field)
        if not isinstance(items, list):
            return None
        out = [it.get(sub_field) for it in items if isinstance(it, dict) and sub_field in it]
        return out or None

    tokens = re.findall(r"[^\.\[\]]+|\[\d+\]", path_expr)
    cur = profile_dict
    for tok in tokens:
        if tok.startswith("["):
            idx = int(tok[1:-1])
            if not isinstance(cur, list) or idx >= len(cur):
                return None
            cur = cur[idx]
        else:
            if not isinstance(cur, dict) or tok not in cur:
                return None
            cur = cur[tok]
    return cur


def _profile_to_dict(profile):
    """Flatten CanonicalProfile (with FieldValue wrappers) into a plain nested dict
    for path resolution, keeping confidence/provenance accessible via *_meta keys."""

    def fv(f):
        return None if f is None else f.value

    return {
        "candidate_id": profile.candidate_id,
        "full_name": fv(profile.full_name),
        "emails": fv(profile.emails) or [],
        "phones": fv(profile.phones) or [],
        "location": fv(profile.location),
        "links": fv(profile.links),
        "headline": fv(profile.headline),
        "years_experience": fv(profile.years_experience),
        "skills": profile.skills,
        "experience": [
            {k: v for k, v in e.items() if not k.startswith("_")} for e in profile.experience
        ],
        "education": profile.education,
        "overall_confidence": profile.overall_confidence,
        "_meta": {
            "full_name": profile.full_name,
            "emails": profile.emails,
            "phones": profile.phones,
        },
    }


def _apply_normalize(value, norm):
    if norm is None or value is None:
        return value
    if norm == "E164":
        if isinstance(value, list):
            return [normalize_phone_e164(v) or v for v in value]
        return normalize_phone_e164(value) or value
    if norm == "canonical":  # skills
        if isinstance(value, list):
            return [normalize_skill(v) or v for v in value]
        return normalize_skill(value) or value
    return value


def project(profile, config=None):
    config = config or DEFAULT_CONFIG
    on_missing = config.get("on_missing", "null")
    include_conf = config.get("include_confidence", True)
    include_prov = config.get("include_provenance", True)

    flat = _profile_to_dict(profile)
    out = {}
    missing_required = []

    for fdef in config.get("fields", []):
        out_path = fdef["path"]
        from_path = fdef.get("from", out_path)
        norm = fdef.get("normalize")
        required = fdef.get("required", False)

        value = _get_path(flat, from_path)
        value = _apply_normalize(value, norm)

        if value is None or value == [] or value == "":
            if required:
                missing_required.append(out_path)
            if on_missing == "omit":
                continue
            elif on_missing == "error" and required:
                continue  # handled via missing_required below
            else:
                out[out_path] = None
                continue

        out[out_path] = value

        meta_key = from_path.split(".")[0].split("[")[0]
        meta = flat.get("_meta", {}).get(meta_key)
        if meta is not None and (include_conf or include_prov):
            wrapper = {}
            if include_conf:
                wrapper["confidence"] = meta.confidence
            if include_prov:
                wrapper["provenance"] = meta.provenance
            out.setdefault("_field_meta", {})[out_path] = wrapper

    if on_missing == "error" and missing_required:
        raise ValueError(f"Required fields missing for {profile.candidate_id}: {missing_required}")

    return out


def validate(record: dict, config=None):
    """Validate a projected record against its config's required fields and basic types."""
    config = config or DEFAULT_CONFIG
    errors = []
    for fdef in config.get("fields", []):
        path = fdef["path"]
        required = fdef.get("required", False)
        on_missing = config.get("on_missing", "null")
        if path not in record:
            if required and on_missing != "omit":
                errors.append(f"missing required field: {path}")
            continue
        value = record[path]
        if required and (value is None) and on_missing != "omit":
            errors.append(f"required field is null: {path}")
        expected_type = fdef.get("type", "")
        if value is not None and expected_type.endswith("[]") and not isinstance(value, list):
            errors.append(f"field {path} expected list, got {type(value).__name__}")
    return errors
