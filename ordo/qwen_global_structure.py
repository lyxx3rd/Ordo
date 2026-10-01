"""Analyze one complete text file and produce a small global structure plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

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
        "h1_examples",
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
    if not isinstance(result["h1_examples"], list) or not all(
        isinstance(item, str) for item in result["h1_examples"]
    ):
        raise ValueError("h1_examples must be a string array")
    if not isinstance(result["h1_pattern"], str):
        raise ValueError("h1_pattern must be a string")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run global structure analysis on one text file")
    parser.add_argument("input", type=Path, help="UTF-8 text file to analyze")
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, help="Optional path for the parsed JSON result")
    args = parser.parse_args()

    document = args.input.read_text(encoding="utf-8")
    prompt = args.prompt.read_text(encoding="utf-8")
    model, key_path = load_settings(args.config)
    client = OpenAI(api_key=load_api_key(key_path), base_url=BASE_URL, timeout=90.0, max_retries=0)
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"【完整文本】\n{document}"},
        ],
        temperature=0,
        max_completion_tokens=600,
        extra_body={"enable_thinking": False},
    )
    content = completion.choices[0].message.content or ""
    result = parse_json_response(content)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
