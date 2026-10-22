# Mode 4 — Text API deployment

[English](../README.md) · [中文快速说明](../README.zh-CN.md)

## Configure and start

```bash
cp local_service/config.example.json local_service/config.local.json
# Edit model_path, model_python (GPU environment), GPU and ports.
ordo-local init-token --config local_service/config.local.json
bash local_service/start.sh
```

The script's Python must be the API environment. Override it using `ORDO_API_PYTHON=/path/to/api-env/bin/python` if needed. Model inference uses the separately configured `model_python`. Model paths and runtime_dir are resolved relative to the JSON config file. The example model path `../models/...` therefore refers to the root `models/` directory.

Only Mode 4 starts **both** background processes: vLLM on `127.0.0.1:8010`, API on configured host/8080. The API may start before the model finishes loading: `/health=200` and `/ready=503` is expected during warmup. No existing service is automatically replaced. Inspect `local_service/runtime/model.log` and `api.log`, which receive unbuffered output.

```bash
tail -f local_service/runtime/api.log
ordo-local status --config local_service/config.local.json
ordo-local restart-api --config local_service/config.local.json  # model stays loaded
bash local_service/stop.sh
```

`status` checks recorded process identity, not model readiness. `stop` only targets matching recorded process groups and preserves files. This manager uses Linux `/proc`/signals. It detaches from the terminal, but does not install boot startup, automatic crash restart, log rotation or a reverse proxy. Model-file/GPU-memory/engine failures are visible in logs; readiness stays unavailable.

## LAN and authentication

Set `api_host` to `0.0.0.0`, and clients use `http://YOUR_SERVER_IP:8080`. Their network must route to that IP and permit TCP8080. `0.0.0.0` is a bind address, not a client URL. The scripts do not open firewall rules.

By default, `auth_enabled` is true. `init-token` creates an owner-only `runtime/api_token.txt`; the manager reads it automatically. `ORDO_API_TOKEN` overrides the file. For external binding, missing credentials prevent startup. Loopback-only deployment without credentials allows local requests. Share the token securely, not in Git or screenshots.

For deliberately anonymous access, set **`"auth_enabled": false`**. Any network-reachable caller can then submit work, including public callers if a public mapping exists. No per-user quota or IP allowlist is built in. Keep limits and trusted-network boundaries. Use HTTPS/reverse-proxy controls for untrusted networks; do not expose the raw vLLM port. `ORDO_MODEL_API_KEY` optionally authenticates the API's connection to an independently protected model endpoint.

All examples below use `YOUR_SERVER_IP`, not a developer machine address. When authentication is disabled, omit Authorization. `/health` and `/ready` are always unauthenticated basic probes.

## Requests

```bash
curl http://YOUR_SERVER_IP:8080/ready

curl http://YOUR_SERVER_IP:8080/v1/label \
  -H "Authorization: Bearer $ORDO_API_TOKEN" -H 'Content-Type: application/json' \
  -d '{"text":"Document title\n\n1. Scope\n\nBody text.","format":["json","txt","md"]}'

curl http://YOUR_SERVER_IP:8080/v1/label/file \
  -H "Authorization: Bearer $ORDO_API_TOKEN" \
  -F 'file=@sample.txt;type=text/plain' -F 'format=["json","txt","md"]'
```

- JSON mode uses a string `text` and an array `format` (default `["json"]`).
- File mode uses multipart `file` and a **form string containing a JSON array** for `format`.
- Accepted formats: json/txt/md, nonempty and unique; one or several always use the same response shape.
- Files must be UTF-8 `.txt`; a UTF-8 BOM is accepted. No Base64, PDF/Word parsing, OCR, NLL cleaning or source rewriting.
- Blank source lines have no labels; original line IDs retain gaps. An old structured paragraph containing internal newlines becomes multiple physical lines when supplied as plain TXT.

## Response

```json
{
  "request_id": "...",
  "files": [
    {"filename":"labels.json","media_type":"application/json","content":"[{...}]\n"},
    {"filename":"labeled.txt","media_type":"text/plain","content":"[H1]            1. Scope\n"},
    {"filename":"labeled.md","media_type":"text/markdown","content":"# 1. Scope\n"}
  ],
  "meta":{"model":"ordo-final-2b","nonempty_lines":4,"windows":1,"elapsed_seconds":1.2}
}
```

The JSON file's `content` is also a **string**, not an embedded rows object. Parse it if desired, or save directly. JSON rows contain `line_id`, `line_number`, `text`, `label`. No ZIP, server-side permanent result storage or temporary download URL is used.

Python example (install `httpx` in the caller environment):

```python
import os
from pathlib import Path
import httpx

headers = {"Authorization": "Bearer " + os.environ["ORDO_API_TOKEN"]}  # use {} for anonymous deployment
with httpx.Client(timeout=1900, trust_env=False) as client:
    r = client.post("http://YOUR_SERVER_IP:8080/v1/label", headers=headers,
        json={"text":Path("sample.txt").read_text(encoding="utf-8-sig"), "format":["json","txt","md"]})
r.raise_for_status()
out = Path("output"); out.mkdir(exist_ok=True)
for item in r.json()["files"]:
    (out / Path(item["filename"]).name).write_text(item["content"], encoding="utf-8")
```

## Limits and failure handling

Default: single API worker, 16 **global** model requests across at most four active documents; excess documents return503. Do not multiply uvicorn workers without replacing this process-local concurrency mechanism.
Default input limits: 2MiB decoded UTF-8 and20,000 physical lines; model request timeout120s, document timeout1800s. Total request bytes are bounded before body parsing; actual decoded text/file limits are checked again. Multipart may spool temporary uploads, which are closed after handling.

Initial inference follows the original unconstrained decoding. Invalid output retries use JSON Schema with the exact current keys and allowed label enums. Missing IDs, duplicate keys, invalid labels, truncation and malformed JSON are never silently replaced with TEXT. After finite retries, the entire document fails rather than returning partial success. This constrains format, not semantic correctness.

| HTTP | Meaning |
| --- | --- |
| 400 | Invalid request/format/encoding or empty text |
| 401 | Missing/incorrect Bearer token when enabled |
| 413 | Input bytes/lines exceed limits |
| 415 | Unsupported file or binary control characters |
| 503 | Active-document limit, model unavailable or upstream busy |
| 504 | Model/document timeout |
| 502 | Invalid model output or model HTTP failure |
| 500 | Unexpected API error |

Errors return `error`, human-readable `message` and `request_id`; X-Request-ID is also sent. Full upstream bodies, server paths and stack traces are not exposed. Logs record request ID, progress and timings, not source text. Uploaded content may contain unsafe HTML; sanitize before rendering Markdown. `/docs` and `/openapi.json` are also protected when a token is configured; do not expect an unauthenticated browser Swagger page to bypass the guard.
