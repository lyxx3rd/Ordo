"""Analyze one complete text file and produce a small global structure plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from openai import OpenAI

from qwen_probe import BASE_URL, DEFAULT_CONFIG, load_api_key, load_settings


ROOT = Path(__file__).resolve().parent
DEFAULT_PROMPT = ROOT / "prompts" / "global_structure.md"


def parse_json_response(content: str) -> dict[str, object]:
    candidate = content.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[1]
        candidate = candidate.rsplit("```", 1)[0].strip()
    result = json.loads(candidate)
    if not isinstance(result, dict):
        raise ValueError("global structure must be a JSON object")
    required = {
        "has_multiple_documents",
        "has_document_title",
        "document_title",
        "has_page_header",
        "page_header_style",
        "has_information_pages",
        "has_toc",
        "has_table",
        "has_appendix",
        "has_h1",
        "h1_titles",
        "h1_pattern",
    }
    if set(result) != required:
        raise ValueError(f"unexpected JSON keys: {sorted(result)}")
    if not all(isinstance(result[key], bool) for key in required if key.startswith("has_")):
        raise ValueError("has_* fields must be boolean")
    if not isinstance(result["document_title"], str):
        raise ValueError("document_title must be a string")
    if not isinstance(result["page_header_style"], str):
        raise ValueError("page_header_style must be a string")
    if not isinstance(result["h1_titles"], list) or not all(
        isinstance(item, str) and item.strip() for item in result["h1_titles"]
    ):
        raise ValueError("h1_titles must be an array of nonempty strings")
    if not result["has_h1"] and result["h1_titles"]:
        raise ValueError("h1_titles must be empty when has_h1 is false")
    if not isinstance(result["h1_pattern"], str):
        raise ValueError("h1_pattern must be a string")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run global structure analysis on one text file")
    parser.add_argument("input", type=Path, help="UTF-8 text file to analyze")
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--model", help="Override configured model without changing the default config")
    parser.add_argument("--raw-response", type=Path, help="Save the complete provider response, including usage")
    parser.add_argument("--output", type=Path, help="Optional path for the parsed JSON result")
    parser.add_argument("--metrics", type=Path, help="Optional usage and timing JSON")
    args = parser.parse_args()

    document = args.input.read_text(encoding="utf-8")
    prompt = args.prompt.read_text(encoding="utf-8")
    model, key_path = load_settings(args.config)
    model = args.model or model
    client = OpenAI(api_key=load_api_key(key_path), base_url=BASE_URL, timeout=90.0, max_retries=0)
    started = perf_counter()
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"【完整文本】\n{document}"},
        ],
        temperature=0,
        response_format={"type": "json_object"},
        max_completion_tokens=2048,
        extra_body={"enable_thinking": False},
    )
    content = completion.choices[0].message.content or ""
    elapsed = perf_counter() - started
    finish_reason = completion.choices[0].finish_reason
    if args.raw_response:
        args.raw_response.parent.mkdir(parents=True, exist_ok=True)
        args.raw_response.write_text(completion.model_dump_json(indent=2) + "\n", encoding="utf-8")
    if args.metrics:
        usage = completion.usage
        metrics = {
            "model": model,
            "response_format": {"type": "json_object"},
            "max_completion_tokens": 2048,
            "finish_reason": finish_reason,
            "source": str(args.input),
            "elapsed_seconds": round(elapsed, 3),
            "input_tokens": getattr(usage, "prompt_tokens", None),
            "output_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }
        args.metrics.parent.mkdir(parents=True, exist_ok=True)
        args.metrics.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if finish_reason == "length":
        raise ValueError("Analyze output reached the 2048-token limit; H1 list may be incomplete. Label was not started.")
    if finish_reason != "stop":
        raise ValueError(f"Analyze did not finish normally: {finish_reason}")
    result = parse_json_response(content)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
