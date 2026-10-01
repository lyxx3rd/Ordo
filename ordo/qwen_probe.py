"""Minimal Qwen connectivity check using the chat_v06 key and endpoint conventions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml
from openai import OpenAI


BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_CONFIG = Path(__file__).resolve().parent / "config.yaml"


def load_settings(config_path: Path) -> tuple[str, Path]:
    config_path = config_path.resolve()
    with config_path.open(encoding="utf-8") as file:
        config = yaml.safe_load(file)
    if not isinstance(config, dict):
        raise ValueError("config.yaml must contain a mapping")

    model = config.get("model_name")
    key_location = config.get("api_keys_path")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("config.yaml is missing model_name")
    if not isinstance(key_location, str) or not key_location.strip():
        raise ValueError("config.yaml is missing api_keys_path")

    key_path = Path(key_location).expanduser()
    if not key_path.is_absolute():
        key_path = config_path.parent / key_path
    return model, key_path.resolve()


def load_api_key(key_path: Path) -> str:
    with key_path.open(encoding="utf-8") as file:
        keys = json.load(file)
    key = keys.get("Qwen_deli") if isinstance(keys, dict) else None
    if not isinstance(key, str) or not key.strip():
        raise ValueError(f"Qwen_deli is missing from {key_path}")
    return key


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Qwen connectivity with one short request")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--model", help="Override model_name from config.yaml")
    parser.add_argument("--api-keys", type=Path, help="Override api_keys_path from config.yaml")
    args = parser.parse_args()

    configured_model, configured_key_path = load_settings(args.config)
    model = args.model or configured_model
    key_path = args.api_keys or configured_key_path
    client = OpenAI(api_key=load_api_key(key_path), base_url=BASE_URL, timeout=30.0, max_retries=0)
    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "请只回复：连通成功"}],
        temperature=0,
        max_completion_tokens=32,
        extra_body={"enable_thinking": False},
    )
    answer = completion.choices[0].message.content or ""
    print(f"model={model}")
    print(f"response={answer.strip()}")


if __name__ == "__main__":
    main()
