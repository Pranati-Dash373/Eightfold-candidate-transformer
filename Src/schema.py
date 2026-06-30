"""
Canonical data model for the candidate profile transformer.

RawRecord  -- one per (candidate, source). Loosely typed, extractor output.
CanonicalProfile -- the merged, internal record (never directly serialized).
"""
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class RawValue:
    """A single field value plus where it came from."""
    value: Any
    source: str          # e.g. "recruiter_csv", "ats_json", "resume_pdf", "recruiter_notes"
    method: str           # e.g. "direct_field", "regex_extract", "section_parse"


@dataclass
class RawRecord:
    """Output of an extractor for one source file/blob, one candidate."""
    source: str
    raw_fields: dict = field(default_factory=dict)  # field_name -> RawValue (or list[RawValue] for list fields)
    match_email: Optional[str] = None
    match_name: Optional[str] = None
    match_company: Optional[str] = None


@dataclass
class FieldValue:
    """A merged field on the canonical profile, with confidence + provenance."""
    value: Any
    confidence: float
    provenance: list  # list of {"source":..., "method":...}


@dataclass
class CanonicalProfile:
    candidate_id: str
    full_name: Optional[FieldValue] = None
    emails: Optional[FieldValue] = None          # value = list[str]
    phones: Optional[FieldValue] = None          # value = list[str]
    location: Optional[FieldValue] = None        # value = {city, region, country}
    links: Optional[FieldValue] = None           # value = {linkedin, github, portfolio, other[]}
    headline: Optional[FieldValue] = None
    years_experience: Optional[FieldValue] = None
    skills: list = field(default_factory=list)   # list of {name, confidence, sources[]}
    experience: list = field(default_factory=list)
    education: list = field(default_factory=list)
    overall_confidence: float = 0.0
