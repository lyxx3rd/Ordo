#!/usr/bin/env python3
"""Prescreen newline boundaries that may be erroneous line wraps."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SENTENCE_ENDINGS = tuple("。！？；：.!?;:")
HEADING_RE = re.compile(
    r"^(?:"
    r"第[一二三四五六七八九十百]+[章节条篇卷]"
    r"|[一二三四五六七八九十百]+[、.]"
    r"|\d+(?:\.\d+)*(?:[ .、]|$)"
    r")"
)


def prescreen(text: str, context_chars: int) -> dict:
    # Split only on LF so embedded form-feed characters do not change physical
    # line numbers. Whitespace-only lines remain part of the raw separator.
    physical_lines = text.split("\n")
    nonempty = [
        (number, line.strip())
        for number, line in enumerate(physical_lines, start=1)
        if line.strip()
    ]

    candidates = []
    rejected = {"short_left": 0, "sentence_ending": 0, "numbered_heading": 0}

    for (left_no, left), (right_no, right) in zip(nonempty, nonempty[1:]):
        # Every adjacent pair of nonempty physical lines has a separator that
        # contains at least one newline. Its exact whitespace is diagnostic
        # only and never used as a document-specific filtering feature.
        separator_parts = [physical_lines[left_no - 1][len(physical_lines[left_no - 1].rstrip()):]]
        separator_parts.extend(physical_lines[left_no:right_no - 1])
        leading = physical_lines[right_no - 1][:-len(physical_lines[right_no - 1].lstrip())]
        separator_parts.append(leading)
        raw_separator = "\n".join(separator_parts)

        if len(left) < 15:
            rejected["short_left"] += 1
            continue
        if left.endswith(SENTENCE_ENDINGS):
            rejected["sentence_ending"] += 1
            continue
        if HEADING_RE.match(right):
            rejected["numbered_heading"] += 1
            continue

        candidates.append(
            {
                "candidate_id": f"B{len(candidates) + 1:04d}",
                "left_line": left_no,
                "right_line": right_no,
                "newline_count": raw_separator.count("\n"),
                "separator_repr": repr(raw_separator),
                "left_text": left,
                "right_text": right,
                "left_context": left[-context_chars:],
                "right_context": right[:context_chars],
                "join_candidate": left[-context_chars:] + right[:context_chars],
                "keep_candidate": left[-context_chars:] + "\n\n" + right[:context_chars],
            }
        )

    return {
        "summary": {
            "physical_lines": len(physical_lines),
            "nonempty_lines": len(nonempty),
            "adjacent_nonempty_boundaries": max(0, len(nonempty) - 1),
            "model_candidates": len(candidates),
            "candidate_ratio": round(
                len(candidates) / max(1, len(nonempty) - 1), 4
            ),
            "rejected": rejected,
        },
        "rules": {
            "minimum_left_characters": 15,
            "direct_keep_sentence_endings": "。！？；：.!?;:",
            "exclude_explicit_numbered_heading_on_right": True,
            "context_characters_each_side": context_chars,
            "horizontal_space_filter": False,
            "newline_policy": "one or more newlines are treated as one boundary",
        },
        "candidates": candidates,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--context-chars", type=int, default=30)
    args = parser.parse_args()

    result = prescreen(args.input.read_text(encoding="utf-8"), args.context_chars)
    result["source"] = str(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"saved: {args.output}")


if __name__ == "__main__":
    main()
