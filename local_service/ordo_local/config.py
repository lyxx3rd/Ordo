import json
import os
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_path: str = "./models/Ordo-Qwen3.5-2B-Reviewed2-Final-BF16"
    model_python: str = "python"
    gpu: str = "5"
    model_port: int = Field(8010, ge=1, le=65535)
    model_name: str = "ordo-final-2b"
    gpu_memory_utilization: float = Field(0.45, gt=0, lt=1)
    max_model_len: int = Field(8192, ge=1024)
    model_url: str = "http://127.0.0.1:8010/v1"
    api_host: str = "127.0.0.1"
    auth_enabled: bool = True
    api_port: int = Field(8080, ge=1, le=65535)
    concurrency: int = Field(16, ge=1, le=64)
    max_documents: int = Field(4, ge=1, le=32)
    max_input_bytes: int = Field(2097152, ge=1024)
    max_lines: int = Field(20000, ge=1)
    request_timeout: float = Field(120, gt=0)
    document_timeout: float = Field(1800, gt=0)
    retries: int = Field(2, ge=0, le=5)
    runtime_dir: str = "./runtime"


def load(path=None):
    path = path or os.environ.get("ORDO_CONFIG")
    if not path:
        return Settings()
    path = Path(path).expanduser().resolve()
    cfg = Settings(**json.loads(path.read_text(encoding="utf-8")))
    for key in ("model_path", "runtime_dir"):
        value = Path(getattr(cfg, key)).expanduser()
        if not value.is_absolute():
            setattr(cfg, key, str((path.parent / value).resolve()))
    return cfg
