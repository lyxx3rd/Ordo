import asyncio
from contextlib import asynccontextmanager
import hmac
import json
import logging
import os
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.exceptions import HTTPException

from .config import load
from . import __version__
from .core import ServiceError, artifacts, label_response_format, messages, parse_labels, units

log = logging.getLogger("uvicorn.error")


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    format: list[Literal["json", "md", "txt"]] = Field(default_factory=lambda: ["json"], min_length=1, max_length=3)

    @field_validator("format")
    @classmethod
    def distinct(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("format不能包含重复项")
        return value


def error(request_id, status, code, message):
    return JSONResponse(status_code=status, content={"error": code, "message": message, "request_id": request_id},
                        headers={"X-Request-ID": request_id})


class Guard:
    """Bound total request bytes before JSON/multipart parsing; authenticate early."""
    def __init__(self, app, limit, token):
        self.app, self.limit, self.token = app, limit, token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        scope.setdefault("state", {})["request_id"] = request_id = uuid4().hex
        headers = dict(scope["headers"])
        if scope["path"] not in ("/health", "/ready") and self.token:
            value = headers.get(b"authorization", b"").decode("latin1")
            if not hmac.compare_digest(value.encode(), ("Bearer " + self.token).encode()):
                return await error(request_id, 401, "unauthorized", "缺少或错误的Bearer token。") (scope, receive, send)
        body = bytearray()
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            body.extend(event.get("body", b""))
            if len(body) > self.limit:
                return await error(request_id, 413, "input_too_large", "请求体超过服务大小限制。") (scope, receive, send)
            if not event.get("more_body", False):
                break
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        async def send_headers(event):
            if event["type"] == "http.response.start":
                event["headers"].append((b"x-request-id", request_id.encode()))
            await send(event)

        await self.app(scope, replay, send_headers)


def create_app(settings=None, transport=None):
    cfg = settings or load()
    token = os.environ.get("ORDO_API_TOKEN", "") if cfg.auth_enabled else ""

    @asynccontextmanager
    async def lifespan(app):
        if cfg.auth_enabled and cfg.api_host not in ("127.0.0.1", "localhost", "::1") and not token:
            raise RuntimeError("对外监听必须设置ORDO_API_TOKEN")
        upstream_token = os.environ.get("ORDO_MODEL_API_KEY")
        headers = {"Authorization": "Bearer " + upstream_token} if upstream_token else {}
        async with httpx.AsyncClient(timeout=cfg.request_timeout, transport=transport, headers=headers,
                                     trust_env=False, limits=httpx.Limits(max_connections=cfg.concurrency + 4)) as client:
            app.state.client = client
            app.state.slots = asyncio.Semaphore(cfg.concurrency)
            app.state.active_documents = 0
            yield

    app = FastAPI(title="Ordo Local Text Label API", version=__version__, lifespan=lifespan)
    # JSON escaping may expand a UTF-8 payload. Actual decoded text/file limit is checked separately.
    app.add_middleware(Guard, limit=cfg.max_input_bytes * 6 + 65536, token=token)

    @app.exception_handler(ServiceError)
    async def service_error(request, exc):
        log.warning("request=%s code=%s", request.state.request_id, exc.code)
        return error(request.state.request_id, exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not expose the supplied document, internal paths, or raw exception objects.
        fields = ", ".join(".".join(map(str, e["loc"])) for e in exc.errors())
        return error(request.state.request_id, 400, "invalid_request", "请求字段或JSON格式错误：" + fields)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(request.state.request_id, exc.status_code, "http_error", "请求路径、方法或表单格式不正确。")

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        log.exception("request=%s internal error", request.state.request_id)
        return error(request.state.request_id, 500, "internal_error", "服务内部错误，请凭request_id联系管理员。")

    async def ready():
        try:
            response = await app.state.client.get(cfg.model_url.rstrip("/") + "/models", timeout=5)
            response.raise_for_status()
            models = response.json()["data"]
            if not isinstance(models, list) or not any(isinstance(m, dict) and m.get("id") == cfg.model_name for m in models):
                raise ValueError("missing model")
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise ServiceError(503, "model_unavailable", "模型服务未就绪或目标模型未注册。") from None

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": __version__}

    @app.get("/ready")
    async def readiness():
        await ready()
        return {"status": "ready", "model": cfg.model_name}

    async def call_window(rows, offset):
        ids = [r["line_id"] for r in rows[offset:offset + 18]]
        payload = {"model": cfg.model_name, "messages": messages(rows, offset), "temperature": 0,
                   "max_tokens": 512, "chat_template_kwargs": {"enable_thinking": False}}
        for attempt in range(cfg.retries + 1):
            try:
                async with app.state.slots:
                    response = await app.state.client.post(cfg.model_url.rstrip("/") + "/chat/completions", json=payload)
                    if response.status_code >= 400:
                        status = response.status_code
                        raise ServiceError(503 if status in (429, 503) else 502, "model_http_error",
                                           f"模型服务返回HTTP {status}；请联系管理员查看日志。")
                    try:
                        obj = response.json()
                        choice = obj["choices"][0]
                        if choice.get("finish_reason") == "length":
                            raise ServiceError(502, "invalid_model_output", "模型输出达到长度上限，未完整返回。")
                        return parse_labels(choice["message"]["content"], ids)
                    except (ValueError, KeyError, IndexError, TypeError):
                        raise ServiceError(502, "invalid_model_output", "模型服务响应格式错误。") from None
            except httpx.TimeoutException:
                failure = ServiceError(504, "model_timeout", "模型推理超时。")
            except httpx.RequestError:
                failure = ServiceError(503, "model_unavailable", "无法连接模型服务。")
            except ServiceError as exc:
                failure = exc
            if attempt == cfg.retries:
                raise failure
            if failure.code == "invalid_model_output":
                # Same frozen prompt, deterministic decode constrained only on
                # retry. Never invent labels or silently repair missing rows.
                payload["response_format"] = label_response_format(ids)
                log.warning("STRUCTURED_RETRY offset=%s attempt=%s", offset, attempt + 2)
            await asyncio.sleep(min(2 ** attempt, 4))

    async def process(inp, request_id):
        start = perf_counter()
        try:
            data = inp.text.encode("utf-8")
        except UnicodeEncodeError:
            raise ServiceError(400, "invalid_encoding", "文本包含无效的Unicode字符。") from None
        if len(data) > cfg.max_input_bytes:
            raise ServiceError(413, "input_too_large", "文本超过字节大小限制。")
        text = inp.text.removeprefix("\ufeff")
        if "\x00" in text or any(ord(c) < 32 and c not in "\t\r\n" for c in text):
            raise ServiceError(415, "invalid_text", "只接受纯文本，不接受含二进制控制字符的文件。")
        if len(text.splitlines()) > cfg.max_lines:
            raise ServiceError(413, "too_many_lines", "文本行数超过限制。")
        rows = units(text)
        if not rows:
            raise ServiceError(400, "empty_text", "文本没有可标记的非空行。")
        # No await between check and increment: atomic in this single event loop.
        if app.state.active_documents >= cfg.max_documents:
            raise ServiceError(503, "server_busy", "处理中文档已达上限，请稍后重试。")
        app.state.active_documents += 1
        tasks = []
        try:
            async def run():
                await ready()
                offsets = iter(range(0, len(rows), 18))
                predictions = {}
                completed = 0
                total = (len(rows) + 17) // 18
                log.info("request=%s BEGIN lines=%s windows=%s", request_id, len(rows), total)

                async def worker():
                    nonlocal completed
                    for offset in offsets:
                        predictions.update(await call_window(rows, offset))
                        completed += 1
                        if completed % 16 == 0 or completed == total:
                            log.info("request=%s PROGRESS %s/%s elapsed=%.1fs", request_id, completed, total, perf_counter() - start)

                tasks.extend(asyncio.create_task(worker()) for _ in range(min(cfg.concurrency, (len(rows) + 17) // 18)))
                try:
                    await asyncio.gather(*tasks)
                finally:
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                for row in rows:
                    row["label"] = predictions[row["line_id"]]
                return {"request_id": request_id, "files": artifacts(rows, inp.format),
                        "meta": {"model": cfg.model_name, "nonempty_lines": len(rows),
                                 "windows": (len(rows) + 17) // 18, "elapsed_seconds": round(perf_counter() - start, 3)}}

            try:
                result = await asyncio.wait_for(run(), timeout=cfg.document_timeout)
            except asyncio.TimeoutError:
                raise ServiceError(504, "document_timeout", "文档处理超时。") from None
            log.info("request=%s lines=%s seconds=%.3f", request_id, len(rows), perf_counter() - start)
            return result
        finally:
            app.state.active_documents -= 1

    @app.post("/v1/label")
    async def label(inp: Input, request: Request):
        return await process(inp, request.state.request_id)

    @app.post("/v1/label/file")
    async def label_file(request: Request, file: UploadFile = File(...), format: str = Form('["json"]')):
        try:
            if Path(file.filename or "").suffix.lower() != ".txt":
                raise ServiceError(415, "unsupported_file", "只接受.txt纯文本文件，不接受PDF或Word。")
            content = await file.read(cfg.max_input_bytes + 1)
            if len(content) > cfg.max_input_bytes:
                raise ServiceError(413, "input_too_large", "文件超过字节大小限制。")
            try:
                text = content.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise ServiceError(400, "invalid_encoding", "文件不是有效的UTF-8文本，请转换编码后重试。") from None
            try:
                inp = Input(text=text, format=json.loads(format))
            except (ValueError, TypeError):
                raise ServiceError(400, "invalid_format", 'format必须为不重复的数组，如["json","txt"]。') from None
            return await process(inp, request.state.request_id)
        finally:
            await file.close()

    return app
