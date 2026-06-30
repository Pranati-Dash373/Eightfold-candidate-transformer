# Multi-Source Candidate Data Transformer

Eightfold Engineering Intern Assignment (Jul-Dec 2026) — Pranati Dash

Turns messy multi-source candidate data (recruiter CSV, ATS JSON, resumes, recruiter
notes) into one canonical, deduplicated profile with provenance and confidence per
field, projected into a configurable output schema.

## Pipeline

`detect → extract → normalize → merge → score_confidence → project → validate`

See `PranatiDash_pranatidash727@gmail.com_Eightfold.pdf` for the full design rationale
(merge policy, confidence rules, config handling, edge cases).

## Sources implemented

- **Structured:** Recruiter CSV export, ATS JSON blob (own field names)
- **Unstructured:** Resume file (.txt/.pdf/.docx), Recruiter notes (.txt)

(GitHub/LinkedIn extractors are structurally supported by the same RawRecord model
but were not built out for this submission — see "Descoped" below.)

## How to run

```bash
cd src
pip install -r ../requirements.txt

# Default schema
python3 run.py \
  --csv ../sample_inputs/recruiter.csv \
  --ats ../sample_inputs/ats.json \
  --resume ../sample_inputs/resume_rohan.txt \
  --resume ../sample_inputs/resume_corrupt.pdf \
  --notes ../sample_inputs/notes_priya.txt \
  --notes ../sample_inputs/notes_empty.txt \
  --out ../output/default_output.json

# Custom runtime config (subset of fields, renamed, E.164/skill normalization)
python3 run.py \
  --csv ../sample_inputs/recruiter.csv \
  --ats ../sample_inputs/ats.json \
  --resume ../sample_inputs/resume_rohan.txt \
  --notes ../sample_inputs/notes_priya.txt \
  --config ../sample_inputs/config_custom.json \
  --out ../output/custom_output.json
```

Output JSON is written to the `--out` path and also printed as a summary to stdout,
including any validation issues per candidate.

## Tests

```bash
cd tests
python3 test_pipeline.py
```

10 tests covering: phone/date/skill/country normalization, missing-file robustness,
corrupt-file robustness, empty-source skipping, conflict-resolution-as-union on
merge, and config `on_missing` (`omit`)/`required` validation behavior.

## Project layout

```
src/
  schema.py       canonical data model (RawRecord, CanonicalProfile, FieldValue)
  normalize.py    pure normalization functions (phone, date, country, skill)
  extractors.py   one extractor per source type, all degrade gracefully
  merge.py        match-key grouping, conflict resolution, confidence scoring
  project.py      runtime-config-driven projection + validation
  run.py          CLI entrypoint
sample_inputs/    CSV, ATS JSON, resume, notes, a corrupt file, an empty file, a custom config
tests/            unit tests
output/           generated output (gitignored contents regenerated on run)
```

## Key design decisions (see design PDF for full detail)

- **Match key:** normalized email if available on 2+ sources, else
  `name + current_company` as a fallback. Unmatched records become their own profile
  rather than risking an incorrect merge.
- **Conflict resolution:** structured sources (CSV, ATS) outrank unstructured ones for
  scalar fields; list fields (emails, phones, skills) are **unioned**, never overwritten.
- **Confidence:** multi-source agreement scores higher than single-source; conflicting
  values are capped at 0.5 so they're flagged for review rather than presented as
  confident.
- **Config/projection:** the canonical profile is never mutated for output. A separate
  projector walks config-specified field paths (including a `field[].subfield`
  list-flatten form, matching the assignment's example config) and applies
  per-field normalization + `on_missing` (`null` / `omit` / `error`) independently.

## Descoped under time pressure

- GitHub/LinkedIn live extractors (network-dependent; the RawRecord/merge model
  already supports adding them without changing merge or projection code).
- True fuzzy/ML name-matching for dedup — only exact-email and name+company fallback
  matching are implemented.
- A UI — only a CLI, per the assignment's stated lower priority on this surface.
- Full education/years_experience parsing from resume prose (regex-only signal
  extraction was prioritized for skills/contact fields, which were judged higher value
  for the sample inputs).
