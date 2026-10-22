# Ordo local service · 1.0.0

[English project README](../README.md) · [中文主页](../README.zh-CN.md) · [Full deployment/API guide](../docs/SERVICE.md)

Portable local inference for the final merged Reviewed2 Qwen3.5-2B model. No cloud key or training directory is required. The model weights are not included; download links are [pending](../docs/MODELS.md).

## Three local entrypoints

- **In-process:** `ordo_local.offline.load_model()` and `label_text()`, demonstrated in the [unexecuted notebook](../notebooks/local_inprocess.ipynb). Imports do not load a GPU model; an explicit load call does.
- **Model-only endpoint:** `ordo-label input.txt --output outputs/run --base-url http://127.0.0.1:8010/v1`, using an independently running vLLM. No business API is needed.
- **Managed text API:** `start.sh` starts the model and an API server as background processes; `stop.sh` only stops matching recorded process groups.

Install from the repository root with `python -m pip install -r requirements.txt`, prepare a separate GPU vLLM environment, then copy `config.example.json` to `config.local.json`. Edit model_path, model_python, GPU and ports. Relative paths are resolved against the config file, not the caller's working directory.

```bash
ordo-local init-token --config local_service/config.local.json
bash local_service/start.sh
ordo-local status --config local_service/config.local.json
ordo-local restart-api --config local_service/config.local.json
bash local_service/stop.sh
```

Set `ORDO_API_PYTHON` if the shell's Python is not the API environment. The GPU environment is selected by config.model_python. Log paths are runtime/api.log and runtime/model.log (unbuffered). `status` reports process liveness; `/ready` reports whether the model is actually ready. No boot startup or crash supervisor is installed.

## Interface

`POST /v1/label`: `{"text":"...", "format":["json","txt","md"]}`.

`POST /v1/label/file`: multipart UTF-8 TXT `file`, plus a `format` form string such as `["json","txt"]`.

Both always return one JSON object with `files: [{"filename":"...", "media_type":"...", "content":"..."}]`, request_id and meta. Even the JSON artifact's content is a string. No ZIP or Base64. Only selected formats are rendered.

`GET /health` checks API liveness; `GET /ready` checks the model endpoint. The API has input-size/line-count limits, a maximum active document count, a global model request semaphore, finite retries, and explicit errors. Inference begins unconstrained; invalid-output retries use exact-key/label-enum JSON Schema. No silent TEXT fallback or partial success is returned.

## Network and security

Default API binding is loopback. To allow LAN calls, bind to 0.0.0.0 and use a routable server IP; the raw model stays on loopback. External binding requires a token by default. `init-token` creates runtime/api_token.txt with0600 permissions; the manager reads it automatically, and ORDO_API_TOKEN overrides it.

Explicit `auth_enabled: false` allows every network-reachable caller. This is a deliberate option, not the publication default. Use a trusted network or HTTPS/proxy access controls. No automatic firewall changes, per-user quotas or broad CORS allowance are added. Markdown must be rendered safely by callers.

Never commit config.local.json, runtime, tokens, models or user data. API/client and model dependencies are intentionally separate. Detailed examples, errors, limits and timing caveats are in [SERVICE](../docs/SERVICE.md) and [BENCHMARKS](../docs/BENCHMARKS.md).

## Tests

```bash
python -m unittest discover -s local_service/tests -v
python -m unittest discover -s tests -v
```

Tests mock model responses; no server/GPU/cloud calls are started. The data-dependent frozen-prompt parity check is skipped in a portable checkout without original training artifacts.
