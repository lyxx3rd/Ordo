#!/usr/bin/env python3
"""Experimental JOIN score: does left context make right text predictable?"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
from pathlib import Path


def call(api_url: str, model: str, prompts: list[str]) -> tuple[list, float, dict]:
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompts,
            "max_tokens": 1,
            "temperature": 0,
            "prompt_logprobs": 0,
        },
        ensure_ascii=False,
    ).encode()
    request = urllib.request.Request(
        api_url, data=payload, headers={"Content-Type": "application/json"}
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.load(response)
    choices = sorted(result["choices"], key=lambda item: item["index"])
    return [item["prompt_logprobs"] for item in choices], time.perf_counter() - started, result["usage"]


def observed_tokens(prompt: str, items: list[dict | None]) -> list[tuple[int, int, str, float]]:
    values = []
    for item in items:
        if item:
            value = next(iter(item.values()))
            values.append((value["decoded_token"], float(value["logprob"])))
    tail = "".join(token for token, _ in values)
    if not prompt.endswith(tail):
        raise ValueError("vLLM token decoding did not align with submitted prompt")
    offset = len(prompt) - len(tail)  # first prompt token has no logprob
    output = []
    for token, logprob in values:
        start = offset
        offset += len(token)
        output.append((start, offset, token, logprob))
    return output


def mean_nll_for_span(prompt: str, items: list[dict | None], start_at: int) -> dict:
    selected = [item for item in observed_tokens(prompt, items) if item[1] > start_at]
    if not selected:
        raise ValueError("No scored tokens in target span")
    nll = -sum(item[3] for item in selected)
    return {
        "mean_nll": nll / len(selected),
        "total_nll": nll,
        "token_count": len(selected),
        "tokens": [item[2] for item in selected],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--left-chars", type=int, default=10)
    parser.add_argument("--right-chars", type=int, default=5)
    parser.add_argument("--api-url", default="http://127.0.0.1:8010/v1/completions")
    parser.add_argument("--model", default="qwen3.5-2b-local")
    args = parser.parse_args()

    source = json.loads(args.input.read_text(encoding="utf-8"))
    candidates = source["candidates"]
    prompts = []
    specs = []
    for item in candidates:
        left = item["left_text"][-args.left_chars:]
        right = item["right_text"][:args.right_chars]
        # No original separator is retained in either candidate.
        prompts.extend([left + right, right])
        specs.extend([(left, right, "JOIN"), (left, right, "KEEP")])

    call(args.api_url, args.model, ["预热文本。"])
    logprobs, elapsed, usage = call(args.api_url, args.model, prompts)
    scored = []
    for index, item in enumerate(candidates):
        left, right, _ = specs[index * 2]
        join = mean_nll_for_span(left + right, logprobs[index * 2], len(left))
        # Standalone right text: score every token vLLM can score. The first
        # token is unscored by causal LM convention and is excluded.
        keep = mean_nll_for_span(right, logprobs[index * 2 + 1], 0)
        delta = keep["mean_nll"] - join["mean_nll"]
        scored.append(
            {
                **item,
                "context_gain": {
                    "left_context": left,
                    "right_context": right,
                    "join": join,
                    "keep": keep,
                    "delta_keep_minus_join": round(delta, 6),
                    "preference_without_threshold": "JOIN" if delta > 0 else "KEEP",
                },
            }
        )

    preferences = {"JOIN": 0, "KEEP": 0}
    for item in scored:
        preferences[item["context_gain"]["preference_without_threshold"]] += 1
    output = {
        "source": str(args.input),
        "method": {
            "join": f"mean NLL(right {args.right_chars} | left {args.left_chars})",
            "keep": f"mean NLL(right {args.right_chars})",
            "separator_policy": "all original boundary symbols are removed",
            "left_chars": args.left_chars,
            "right_chars": args.right_chars,
        },
        "model": args.model,
        "elapsed_seconds": round(elapsed, 6),
        "usage": usage,
        "preferences_without_threshold": preferences,
        "candidates": scored,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: output[k] for k in ["method", "elapsed_seconds", "usage", "preferences_without_threshold"]}, ensure_ascii=False, indent=2))
    print(f"saved: {args.output}")


if __name__ == "__main__":
    main()
