"""Batch label a UTF-8 text document and build a Markdown outline."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from openai import OpenAI

from qwen_probe import BASE_URL, DEFAULT_CONFIG, load_api_key, load_settings


ROOT = Path(__file__).resolve().parent
DEFAULT_LABELS = ROOT / "labels.md"
DEFAULT_EXAMPLE = ROOT / "label_example.md"
LABELS = {"TEXT", "NEW_DOCUMENT", "HEADER", "INFO_PAGE", "H1", "H2", "H3", "HN", "POINT", "TOC", "TABLE", "APPENDIX"}
LINE_PATTERN = re.compile(r"^(L\d+)\s+(TEXT|NEW_DOCUMENT|HEADER|INFO_PAGE|H1|H2|H3|HN|POINT|TOC|TABLE|APPENDIX)$")


@dataclass(frozen=True)
class Unit:
    line_number: int
    text: str

    @property
    def line_id(self) -> str:
        return f"L{self.line_number:04d}"


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[:limit]}……[TRUNCATED]"


def load_units(path: Path) -> list[Unit]:
    return [
        Unit(line_number=index, text=line)
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if line.strip()
    ]


def make_batches(
    units: list[Unit], *, maximum: int, visible_char_limit: int, char_limit: int
) -> list[list[Unit]]:
    batches: list[list[Unit]] = []
    current: list[Unit] = []
    current_chars = 0
    for unit in units:
        visible_length = min(len(unit.text), visible_char_limit)
        would_exceed = current and (
            len(current) >= maximum or current_chars + visible_length > char_limit
        )
        if would_exceed:
            batches.append(current)
            current, current_chars = [], 0
        current.append(unit)
        current_chars += visible_length
    if current:
        batches.append(current)
    return batches


def render_units(units: list[Unit], char_limit: int, labels: dict[str, str] | None = None) -> str:
    rendered: list[str] = []
    for unit in units:
        prefix = f"[{unit.line_id}] "
        if labels is not None:
            prefix += f"[{labels[unit.line_id]}] "
        rendered.append(f"{prefix}{truncate(unit.text, char_limit)}")
    return "\n".join(rendered) or "（无）"


def render_state(labels: dict[str, str], units: list[Unit]) -> str:
    titles: dict[str, str] = {"H1": "无", "H2": "无", "H3": "无"}
    region = "main"
    document_started = False
    for unit in units:
        label = labels.get(unit.line_id)
        if not label:
            continue
        if label == "HEADER":
            continue
        if label == "NEW_DOCUMENT":
            document_started = True
            titles = {"H1": "无", "H2": "无", "H3": "无"}
            region = "main"
        elif label == "APPENDIX":
            region = "appendix"
        elif label == "H1":
            titles["H1"] = truncate(unit.text, 80)
            titles["H2"] = "无"
            titles["H3"] = "无"
        elif label == "H2":
            titles["H2"] = truncate(unit.text, 80)
            titles["H3"] = "无"
        elif label == "H3":
            titles["H3"] = truncate(unit.text, 80)
    return "\n".join(
        [
            f"document_started: {'true' if document_started else 'false'}",
            f"region: {region}",
            f"H1: {titles['H1']}",
            f"H2: {titles['H2']}",
            f"H3: {titles['H3']}",
        ]
    )


def build_prompt(
    *,
    label_rules: str,
    example: str,
    global_structure: dict[str, Any],
    state: str,
    previous: list[Unit],
    all_labels: dict[str, str],
    current: list[Unit],
    following: list[Unit],
    current_char_limit: int,
    output_format: str,
) -> str:
    if output_format == "label_list":
        output_instruction = (
            f"输出格式严格为合法 JSON 字符串数组，数组长度必须恰好为 {len(current)}。"
            "数组第 n 项对应当前 batch 第 n 行。输出前必须核对数组恰好有指定数量的项目。只输出数组，不要 Markdown、解释或行号。"
            '例如：["NEW_DOCUMENT", "TEXT", "H1"]。'
        )
    else:
        output_instruction = "输出格式严格为：L0001 LABEL，每行一条。"
    return f"""你是文档行级结构标注器。只标注“当前 batch”中的行。

允许标签：TEXT、NEW_DOCUMENT、HEADER、INFO_PAGE、H1、H2、H3、HN、POINT、TOC、TABLE、APPENDIX。
每个当前行必须恰好输出一个标签。不要改写原文，也不要标注上一 batch 或下一 batch。
{output_instruction}

【标签规则】
{label_rules}

【标注示例】
{example}

【本文件全局结构分析】
{json.dumps(global_structure, ensure_ascii=False)}

【当前层级状态：由已确认标签计算】
{state}

【上一 batch 已确认结果】
{render_units(previous, 50, all_labels)}

【当前 batch：需要标注】
{render_units(current, current_char_limit)}

【下一 batch 预览：不要标注】
{render_units(following, 50)}
"""


def parse_labels(content: str, expected_ids: list[str], output_format: str) -> dict[str, str]:
    candidate = content.strip()
    fence = chr(96) * 3
    if candidate.startswith(fence):
        candidate = candidate.split("\n", 1)[1].rsplit(fence, 1)[0].strip()
    if output_format == "label_list":
        values = json.loads(candidate)
        if not isinstance(values, list) or len(values) != len(expected_ids):
            raise ValueError(f"expected {len(expected_ids)} labels, got {values!r}")
        if not all(isinstance(label, str) and label in LABELS for label in values):
            raise ValueError(f"invalid label list: {values!r}")
        return dict(zip(expected_ids, values))

    parsed: dict[str, str] = {}
    for line in candidate.splitlines():
        match = LINE_PATTERN.match(line.strip())
        if not match:
            raise ValueError(f"invalid model output line: {line!r}")
        line_id, label = match.groups()
        if line_id in parsed:
            raise ValueError(f"duplicate label for {line_id}")
        parsed[line_id] = label
    if set(parsed) != set(expected_ids):
        raise ValueError(f"model returned {sorted(parsed)}, expected {expected_ids}")
    return parsed


def usage_values(usage: Any) -> tuple[int, int]:
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    if prompt is None:
        prompt = getattr(usage, "input_tokens", 0)
    if completion is None:
        completion = getattr(usage, "output_tokens", 0)
    return int(prompt or 0), int(completion or 0)


def build_outline(units: list[Unit], labels: dict[str, str]) -> str:
    output: list[str] = ["# 目录"]
    current_document = "未命名文档"
    appendix_active = False
    for unit in units:
        label = labels[unit.line_id]
        if label == "HEADER":
            continue
        if label == "NEW_DOCUMENT":
            current_document = unit.text
            output.extend(["", f"## {current_document}"])
            appendix_active = False
        elif label == "APPENDIX":
            output.append(f"- {unit.text}")
            appendix_active = True
        elif label in {"H1", "H2", "H3"}:
            level = int(label[1])
            indent = "  " * (level - 1 + int(appendix_active))
            output.append(f"{indent}- {unit.text}")
    return "\n".join(output).rstrip() + "\n"


def build_markdown(source_lines: list[str], labels: dict[str, str]) -> str:
    """Restore the full source text with Markdown structure inferred from labels."""
    output: list[str] = []
    toc_active = False
    appendix_active = False
    for line_number, text in enumerate(source_lines, start=1):
        if not text.strip():
            if output and output[-1] != "": 
                output.append("")
            continue
        label = labels[f"L{line_number:04d}"]
        if label == "HEADER":
            continue
        if label == "NEW_DOCUMENT":
            if output and output[-1] != "": 
                output.append("")
            output.append(f"# {text}")
            toc_active = appendix_active = False
        elif label == "APPENDIX":
            if output and output[-1] != "": 
                output.append("")
            output.append(f"## {text}")
            appendix_active = True
            toc_active = False
        elif label == "TOC":
            if not toc_active:
                if output and output[-1] != "": 
                    output.append("")
                output.append("## 目录")
                toc_active = True
            if text.strip() not in {"目录", "目 录"}:
                output.append(f"- {text}")
        elif label in {"H1", "H2", "H3"}:
            level = int(label[1]) + 1 + int(appendix_active)
            if output and output[-1] != "": 
                output.append("")
            output.append(f"{'#' * level} {text}")
            toc_active = False
        elif label == "HN":
            if output and output[-1] != "":
                output.append("")
            output.append(f"**{text}**")
            toc_active = False
        elif label == "POINT":
            output.append(f"- {text}")
            toc_active = False
        else:
            output.append(text)
            toc_active = False
    return "\n".join(output).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Label a text document and build its outline")
    parser.add_argument("input", type=Path)
    parser.add_argument("--global-structure", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--model", help="Override configured model name")
    parser.add_argument("--base-url", default=BASE_URL, help="OpenAI-compatible API base URL")
    parser.add_argument("--chat-template-disable-thinking", action="store_true", help="Pass chat_template_kwargs.enable_thinking=false for compatible local servers")
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--example", type=Path, default=DEFAULT_EXAMPLE)
    parser.add_argument("--batch-size", type=int, default=18, help="Maximum nonempty lines per model call")
    parser.add_argument("--current-char-limit", type=int, default=200, help="Visible characters per current line")
    parser.add_argument("--batch-char-limit", type=int, default=3600, help="Maximum visible current-batch characters")
    parser.add_argument("--output-format", choices=("line_ids", "label_list"), default="line_ids")
    args = parser.parse_args()

    if args.batch_size < 1 or args.current_char_limit < 1 or args.batch_char_limit < 1:
        parser.error("batch and character limits must be positive")
    started_at = perf_counter()
    source_lines = args.input.read_text(encoding="utf-8").splitlines()
    units = load_units(args.input)
    batches = make_batches(
        units,
        maximum=args.batch_size,
        visible_char_limit=args.current_char_limit,
        char_limit=args.batch_char_limit,
    )
    global_structure = json.loads(args.global_structure.read_text(encoding="utf-8"))
    label_rules = args.labels.read_text(encoding="utf-8")
    example = args.example.read_text(encoding="utf-8")
    configured_model, key_path = load_settings(args.config)
    model = args.model or configured_model
    client = OpenAI(api_key=load_api_key(key_path), base_url=args.base_url, timeout=90.0, max_retries=0)

    labels: dict[str, str] = {}
    batch_records: list[dict[str, Any]] = []
    input_tokens = output_tokens = 0
    offset = 0
    for batch_index, current in enumerate(batches, start=1):
        previous = batches[batch_index - 2] if batch_index > 1 else []
        following = units[offset + len(current) : offset + len(current) + 3]
        prompt = build_prompt(
            label_rules=label_rules,
            example=example,
            global_structure=global_structure,
            state=render_state(labels, units),
            previous=previous,
            all_labels=labels,
            current=current,
            following=following,
            current_char_limit=args.current_char_limit,
            output_format=args.output_format,
        )
        batch_input_tokens = batch_output_tokens = 0
        batch_elapsed = 0.0
        attempts = 0
        while True:
            extra_body = {"enable_thinking": False}
            if args.chat_template_disable_thinking:
                extra_body = {"chat_template_kwargs": {"enable_thinking": False}}
            call_started = perf_counter()
            completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_completion_tokens=300,
                extra_body=extra_body,
            )
            batch_elapsed += perf_counter() - call_started
            prompt_count, completion_count = usage_values(completion.usage)
            batch_input_tokens += prompt_count
            batch_output_tokens += completion_count
            content = completion.choices[0].message.content or ""
            try:
                result = parse_labels(content, [unit.line_id for unit in current], args.output_format)
                break
            except ValueError:
                if attempts >= 1:
                    raise
                attempts += 1
                prompt += (
                    f"\n【格式修正】上一输出未通过格式校验。当前 batch 有 {len(current)} 行，"
                    "请重新只输出一个恰好同长度的合法 JSON 标签数组。"
                )

        labels.update(result)
        input_tokens += batch_input_tokens
        output_tokens += batch_output_tokens
        batch_records.append(
            {
                "batch": batch_index,
                "line_ids": [unit.line_id for unit in current],
                "elapsed_seconds": round(batch_elapsed, 3),
                "input_tokens": batch_input_tokens,
                "output_tokens": batch_output_tokens,
                "format_retries": attempts,
                "labels": result,
            }
        )
        offset += len(current)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.input.stem
    label_rows = [
        {"line_id": unit.line_id, "line_number": unit.line_number, "label": labels[unit.line_id], "text": unit.text}
        for unit in units
    ]
    metrics = {
        "model": model,
        "source": str(args.input),
        "nonempty_lines": len(units),
        "batches": len(batches),
        "batch_size_limit": args.batch_size,
        "current_char_limit": args.current_char_limit,
        "output_format": args.output_format,
        "elapsed_seconds": round(perf_counter() - started_at, 3),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "batch_records": batch_records,
    }
    (args.output_dir / f"{stem}_labels.json").write_text(json.dumps(label_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / f"{stem}_outline.md").write_text(build_outline(units, labels), encoding="utf-8")
    (args.output_dir / f"{stem}_reconstructed.md").write_text(
        build_markdown(source_lines, labels), encoding="utf-8"
    )
    (args.output_dir / f"{stem}_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: metrics[key] for key in metrics if key != "batch_records"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
