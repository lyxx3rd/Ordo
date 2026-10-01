#!/usr/bin/env python3
"""Apply conservative JOIN decisions from a scored line-break candidate file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Raw layout-extracted text")
    parser.add_argument("scored_candidates", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument(
        "--join-threshold",
        type=float,
        default=0.1,
        help="Join only when KEEP mean NLL - JOIN mean NLL exceeds this value.",
    )
    args = parser.parse_args()

    scored = json.loads(args.scored_candidates.read_text(encoding="utf-8"))
    score_by_boundary = {
        (item["left_line"], item["right_line"]): item
        for item in scored["candidates"]
    }

    # Physical LF line numbering matches the candidate JSON. strip() removes
    # layout indentation only; punctuation and all visible text are retained.
    physical_lines = args.source.read_text(encoding="utf-8").split("\n")
    rows = [
        (number, line.strip())
        for number, line in enumerate(physical_lines, start=1)
        if line.strip()
    ]
    if not rows:
        raise ValueError("Source contains no non-empty lines")

    pieces = [rows[0][1]]
    merged = []
    kept_scored = []
    direct_kept = 0

    for (left_no, left), (right_no, right) in zip(rows, rows[1:]):
        decision = score_by_boundary.get((left_no, right_no))
        if decision is None:
            pieces.extend(["\n\n", right])
            direct_kept += 1
            continue

        delta = decision["context_gain"]["delta_keep_minus_join"]
        if delta > args.join_threshold:
            pieces.append(right)
            merged.append(
                {
                    "candidate_id": decision["candidate_id"],
                    "left_line": left_no,
                    "right_line": right_no,
                    "delta_context_gain_keep_minus_join": delta,
                    "left_text": left,
                    "right_text": right,
                }
            )
        else:
            pieces.extend(["\n\n", right])
            kept_scored.append(
                {
                    "candidate_id": decision["candidate_id"],
                    "left_line": left_no,
                    "right_line": right_no,
                    "delta_context_gain_keep_minus_join": delta,
                }
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(pieces).strip() + "\n", encoding="utf-8")

    report = {
        "source": str(args.source),
        "scored_candidates": str(args.scored_candidates),
        "output": str(args.output),
        "policy": {
            "join_when": "KEEP mean NLL - JOIN mean NLL > threshold",
            "join_threshold": args.join_threshold,
            "otherwise": "KEEP as a paragraph boundary",
            "layout_whitespace": "leading/trailing whitespace on physical lines is removed",
        },
        "summary": {
            "physical_lines": len(physical_lines),
            "nonempty_lines": len(rows),
            "all_boundaries": len(rows) - 1,
            "scored_boundaries": len(score_by_boundary),
            "merged_boundaries": len(merged),
            "scored_but_kept": len(kept_scored),
            "direct_kept": direct_kept,
        },
        "merged_boundaries": merged,
        "scored_but_kept": kept_scored,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"cleaned: {args.output}")
    print(f"report: {args.report}")


if __name__ == "__main__":
    main()
