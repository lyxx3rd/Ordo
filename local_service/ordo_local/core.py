"""Frozen 18/18/18 prompt protocol; no model dependencies."""
import json
import re
from importlib.resources import files

LABELS = {"TEXT", "NEW_DOCUMENT", "HEADER", "INFO_PAGE", "H1", "H2", "H3", "HN", "POINT", "TOC", "TABLE", "APPENDIX"}


class ServiceError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def units(text):
    return [{"line_id": f"L{i:04d}", "line_number": i, "text": t}
            for i, t in enumerate(text.splitlines(), 1) if t.strip()]


def visible(text, limit):
    return text if len(text) <= limit else text[:limit] + "……[TRUNCATED]"


def render(rows, limit):
    return "\n".join(f'[{r["line_id"]}] {visible(r["text"], limit)}' for r in rows) or "（无）"


def messages(rows, offset):
    current = rows[offset:offset + 18]
    template = files("ordo_local").joinpath("assets/system.txt").read_text(encoding="utf-8").rstrip("\n")
    # Only this batch's count changes; all other system bytes are frozen.
    system = template.replace("__ORDO_CURRENT_COUNT__", str(len(current)))
    user = ("【上一 batch 原文：不要标注】\n" + render(rows[max(0, offset - 18):offset], 50)
            + "\n\n【当前 batch：需要标注】\n" + render(current, 200)
            + "\n\n【下一 batch 预览：不要标注】\n" + render(rows[offset + 18:offset + 36], 50))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_labels(raw, ids):
    def unique(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                raise ValueError("duplicate key")
            d[k] = v
        return d
    try:
        obj = json.loads(re.sub(r"^\s*<think>\s*</think>\s*", "", raw, count=1), object_pairs_hook=unique)
        if not isinstance(obj, dict) or set(obj) != set(ids):
            raise ValueError("line ID mismatch")
        if not all(isinstance(v, str) and v in LABELS for v in obj.values()):
            raise ValueError("invalid label")
        return obj
    except (ValueError, TypeError):
        raise ServiceError(502, "invalid_model_output", "模型输出不是完整、合法的行号与标签JSON。") from None


def label_response_format(ids):
    return {"type": "json_schema", "json_schema": {"name": "ordo_labels", "strict": True,
            "schema": {"type": "object", "properties": {key: {"type": "string", "enum": sorted(LABELS)} for key in ids},
                       "required": list(ids), "additionalProperties": False}}}


def markdown(rows):
    out = []
    table = []

    def flush():
        if table:
            # Preserve actual text, never invent missing table columns.
            longest = max([len(s) for t in table for s in re.findall(r"`+", t)] or [0])
            fence = "`" * max(3, longest + 1)
            out.extend([fence + "text", *table, fence, ""])
            table.clear()

    for r in rows:
        label, text = r["label"], r["text"]
        if label == "TABLE":
            table.append(text)
            continue
        flush()
        if label in ("H1", "H2", "H3", "HN"):
            text = "#" * (4 if label == "HN" else int(label[1])) + " " + text
        elif label in ("NEW_DOCUMENT", "APPENDIX"):
            text = "**" + text + "**"
        elif label in ("POINT", "TOC"):
            text = "- " + text
        elif label in ("HEADER", "INFO_PAGE"):
            text = f"> [{label}] " + text
        out.extend([text, ""])
    flush()
    return "\n".join(out).rstrip() + "\n"


def artifacts(rows, formats):
    results = []
    for fmt in formats:
        if fmt == "json":
            content, name, media = json.dumps(rows, ensure_ascii=False, indent=2) + "\n", "labels.json", "application/json"
        elif fmt == "txt":
            width = max(len(f"[{x}]") for x in LABELS)
            content = "".join(f'[{r["label"]}]'.ljust(width) + "  " + r["text"] + "\n" for r in rows)
            name, media = "labeled.txt", "text/plain"
        else:
            content, name, media = markdown(rows), "labeled.md", "text/markdown"
        results.append({"filename": name, "media_type": media, "content": content})
    return results
