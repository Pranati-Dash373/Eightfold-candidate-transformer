#!/usr/bin/env python3
"""
CLI: feed source files + an optional runtime config, get back schema-valid JSON.

Usage:
  python run.py --csv sample_inputs/recruiter.csv --ats sample_inputs/ats.json \
                 --resume sample_inputs/resume1.pdf --notes sample_inputs/notes.txt \
                 --config sample_inputs/config_custom.json \
                 --out output/result.json
"""
import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from extractors import extract_csv, extract_ats_json, extract_resume, extract_notes
from merge import merge_all
from project import project, validate, DEFAULT_CONFIG


def run_pipeline(csv_path=None, ats_path=None, resume_paths=None, notes_paths=None, config=None):
    raw_records = []
    raw_records += extract_csv(csv_path) if csv_path else []
    raw_records += extract_ats_json(ats_path) if ats_path else []
    for rp in (resume_paths or []):
        raw_records += extract_resume(rp)
    for np_ in (notes_paths or []):
        raw_records += extract_notes(np_)

    profiles = merge_all(raw_records)

    config = config or DEFAULT_CONFIG
    results = []
    errors_by_candidate = {}
    for p in profiles:
        try:
            projected = project(p, config)
        except ValueError as e:
            errors_by_candidate[p.candidate_id] = str(e)
            continue
        errs = validate(projected, config)
        if errs:
            errors_by_candidate[p.candidate_id] = errs
        results.append(projected)

    return results, errors_by_candidate


def main():
    ap = argparse.ArgumentParser(description="Multi-source candidate data transformer")
    ap.add_argument("--csv", help="Recruiter CSV export path")
    ap.add_argument("--ats", help="ATS JSON blob path")
    ap.add_argument("--resume", action="append", default=[], help="Resume file path (repeatable)")
    ap.add_argument("--notes", action="append", default=[], help="Recruiter notes .txt path (repeatable)")
    ap.add_argument("--config", help="Runtime output config JSON path (defaults to built-in default schema)")
    ap.add_argument("--out", default="output/result.json", help="Where to write output JSON")
    args = ap.parse_args()

    config = None
    if args.config:
        with open(args.config) as f:
            config = json.load(f)

    results, errors = run_pipeline(
        csv_path=args.csv, ats_path=args.ats,
        resume_paths=args.resume, notes_paths=args.notes,
        config=config,
    )

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Wrote {len(results)} profile(s) to {args.out}")
    if errors:
        print("Validation issues:")
        for cid, e in errors.items():
            print(f"  {cid}: {e}")


if __name__ == "__main__":
    main()
