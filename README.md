# Ordo 1.0

**Turn plain text into document structure — locally or through a model API.**

English · [简体中文](README.zh-CN.md)

Ordo labels document titles, headings, body text, lists, tables, contents, appendices, headers and metadata. It exports **JSON, aligned TXT and Markdown** while retaining full nonempty source text and physical line IDs.

The recommended local backend is the **Dev-selected best Qwen3.5-2B merged BF16 model** (epoch 4, checkpoint-3296), not the last checkpoint. It needs no cloud API, Analyze stage, examples or runtime LoRA. The online few-shot route remains available separately.

> Input: UTF-8 plain text. PDF/Word extraction, OCR, accurate layout reconstruction and RAG chunk indexing are **not** part of the four standard 1.0 modes. Weights are available on [ModelScope](https://modelscope.cn/models/l424102993/Ordo_2B); see [Models](docs/MODELS.md).

## Choose a mode

| Mode | How it runs | Start here |
| --- | --- | --- |
| 1. Online few-shot | Provider Analyze → few-shot, sequential Label; requires your own key | `scripts/run_online_structure.sh` |
| 2. Local in-process | Load vLLM and call it in a Python process/notebook; no HTTP port | [Notebook](notebooks/local_inprocess.ipynb) |
| 3. Local decoupled | Model-only vLLM server + independent lightweight Python/CLI client | `scripts/serve_model.sh` + `ordo-label` |
| 4. Text service | Background model + business API for text/TXT uploads and selectable outputs | [Service guide](docs/SERVICE.md) |

Modes 2–4 share the same frozen local prompt and renderer: 18 current nonempty lines, up to 18 preceding/following raw lines, visible limits 50/200/50 **characters**. No prediction feedback or Analyze is added. The full original text, not the visible truncated text, is exported.

## Install

Python 3.10+ for the API/client; Python 3.12 in a separate Linux/NVIDIA GPU environment is recommended for vLLM. Run installation commands from the repository root.

```bash
# API/client + online route; does not install GPU torch/vLLM
python -m pip install -r requirements.txt

# In a separate GPU environment; tested engine version: vLLM 0.31.0
python -m pip install -r requirements-model.txt

# Optional: notebook kernel and UI, in the GPU environment
python -m pip install -r requirements-notebook.txt
```

No service starts during installation/import. Do not install a GPU runtime into an existing environment without checking its CUDA/torch compatibility. [Dependency notes](docs/MODELS.md).

## 1 · Online few-shot

```bash
cp ordo/config.example.yaml ordo/config.yaml
export ORDO_ONLINE_API_KEY='YOUR_PROVIDER_KEY'
# Optional: ORDO_ONLINE_BASE_URL / ORDO_ONLINE_MODEL
bash scripts/run_online_structure.sh examples/sample.txt outputs/online_example
```

Set a model identifier supported by **your endpoint** in the private config or `ORDO_ONLINE_MODEL`. Historical Flash/Plus/Max names in the benchmark are not a promise about any provider's current catalogue. This route assumes a Qwen-compatible OpenAI chat endpoint supporting JSON-object output and the thinking switch.

The route reads the whole text for Analyze, then labels windows with `ordo/labels.md` and `ordo/label_example.md`. It saves analysis, labels, TXT/Markdown, outline and time/token records. A label checkpoint can resume only when its input/prompt/model signature matches. The wrapper reruns Analyze, so a changed analysis may invalidate a previous Label checkpoint; reuse an existing analysis with the Python entrypoint when strict resume is needed.

## 2 · Local in-process

Download the **final merged model**, set `ORDO_MODEL_PATH`, select an idle GPU, then open [local_inprocess.ipynb](notebooks/local_inprocess.ipynb). It calls `vllm.LLM.chat` directly and exports files; no model server or business API is launched.

```python
from ordo_local.offline import load_model, label_text
from ordo_local.client import save_result

llm = load_model("/path/to/Ordo-Qwen3.5-2B-Reviewed2-Final-BF16")
result = label_text(llm, "Document title\n\n1. Scope\n\nBody text.")
save_result(result, "outputs/inprocess_example")
```

Set `CUDA_VISIBLE_DEVICES` **before** importing torch/vLLM. Restart the notebook kernel to release GPU workers. The notebook is shipped unexecuted; offline API flow is mock-tested, not newly GPU-benchmarked for this release.

## 3 · Local decoupled

```bash
export ORDO_MODEL_PATH=/path/to/Ordo-Qwen3.5-2B-Reviewed2-Final-BF16
# Use the GPU environment's Python here.
GPU=0 bash scripts/serve_model.sh
```

For background operation, redirect logs with `nohup`:

```bash
mkdir -p outputs
nohup env GPU=0 bash scripts/serve_model.sh > outputs/model.log 2>&1 < /dev/null &
# From the API/client environment:
ordo-label examples/sample.txt --output outputs/local_example \
  --base-url http://127.0.0.1:8010/v1 --model ordo-final-2b --format json txt md
```

The model binds to loopback. The client sends windows with bounded concurrency (default 16), validates every label and saves `labels.json`, `labeled.txt`, `labeled.md` and `run.json`. Existing output files are not overwritten. This mode does **not** require the business API from Mode 4.

## 4 · Deploy a text API

```bash
cp local_service/config.example.json local_service/config.local.json
# Edit model_path, model_python, GPU and ports; paths are relative to this config.
ordo-local init-token --config local_service/config.local.json
bash local_service/start.sh
```

The manager starts both services in the background: internal vLLM on `127.0.0.1:8010`, business API on port `8080`. Use an API-environment Python or set `ORDO_API_PYTHON`. Do not start Mode 3 on the same GPU/port at the same time.

```text
GET  /health          API liveness
GET  /ready           Target model readiness
POST /v1/label        JSON {"text":"...", "format":["json","txt","md"]}
POST /v1/label/file   UTF-8 TXT multipart upload
```

Selecting one or several formats always returns **one JSON response containing a `files` array**, with each filename, media type and text content — no ZIP, Base64, temporary link or automatic multi-download. [Request/response examples, LAN access and errors](docs/SERVICE.md).

Defaults: 8192 context per window, 16 global model requests, four active documents, 2 MiB text, 20,000 physical lines. GPU budget 0.45 was validated on a 24GB RTX 3090 with this 2B model; other hardware requires a startup/load test. It is a budget, not a guarantee of 16 simultaneously resident long sequences.

To expose the API on a LAN, set `api_host` to `0.0.0.0`; use the server's routable IP from clients. Default deployment requires a token for external binding. Explicit `auth_enabled: false` allows **every network-reachable caller**; keep input/concurrency limits and network controls. The model port stays private. No firewall rules, boot autostart or auto-restart are installed.

## Historical results — context, not a leaderboard

On the **same 114-document / 35,821-line historical Test subset**, final 2B outperformed preserved Plus few-shot outputs against the same reviewed labels:

| Method | Accuracy | H1 F1 | H2 F1 | H3 F1 |
| --- | ---: | ---: | ---: | ---: |
| Qwen3.7-Plus, Analyze + few-shot | 89.08% | 81.17% | 60.06% | 57.42% |
| Final local 2B, single stage | 90.11% | 90.68% | 80.11% | 88.75% |

This retrospective overlap excludes 12 open-source documents without complete Plus predictions from both methods. Teacher-origin gold and historical prompt differences limit causal conclusions. Timing records are not matched, so no speedup ratio is claimed. [Scope, source breakdown and metrics](docs/BENCHMARKS.md#c-matched-historical-plus-versus-final-2b).

These are existing development records, **not a new controlled benchmark**. The online rows use 12 QMS calibration documents (1,912 scored lines); the local model uses a different mixed Test set (126 documents, 43,423 lines). **Do not rank models across these sets.**

| Route | Evaluation set | Accuracy | H1 F1 | H2 F1 | H3 F1 | Recorded wall time |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Qwen3.7-Flash few-shot | 12 QMS calibration | 88.08% | 98.65% | 83.67% | 85.71% | 106.1 s |
| Qwen3.7-Plus few-shot | same 12 | 97.02% | 98.67% | 91.43% | 90.20% | 197.6 s |
| Qwen3.7-Max few-shot | same 12 | 96.55% | 99.34% | 89.72% | 85.39% | 163.1 s |
| Local final 2B, no Analyze | 126 mixed Test | 91.12% | 89.71% | 77.09% | 82.09% | 539.5 s¹ |

¹ Historical base+best-LoRA evaluation, one 3090, 16 window requests, excluding server startup. Online timings include each route's Analyze+Label with its historical scheduling. Merged-model API acceptance later submitted 126 documents in **417.3 s**: 124 succeeded initially; two format failures passed after deploying structured retries, in a separate **43.2 s** retest. This is not a fresh zero-failure full-set timing. [Benchmark details and sanitized aggregates](docs/BENCHMARKS.md).

Why 2B: low deployment cost and single-stage throughput. A 9B NF4 + generated-Analyze variant reached 92.34% on the mixed Test but took about 40.6 minutes across its two stages; GRPO did not yield stable overall gains in the tested setup. Neither is the 1.0 delivery model.

## Labels and limitations

`TEXT`, `NEW_DOCUMENT`, `HEADER`, `INFO_PAGE`, `H1`, `H2`, `H3`, `HN`, `POINT`, `TOC`, `TABLE`, `APPENDIX`.

See [English label summary](docs/LABELS.md), [local frozen rules](local_service/ordo_local/assets/labels.md), and online examples in `ordo/`. H3 caps real headings deeper than three; HN is an unnumbered local heading, not an extra numbered level. Numbered body text is not automatically a heading/list. Headers, tables and metadata lost during extraction cannot reliably be reconstructed from absent information.

Train/Dev combine teacher labels and partial human review. Historical Test sets were used during development and are not untouched blind benchmarks. Exact/whitespace duplicate checks do not establish complete template/source isolation. Private QMS/contracts, source documents, credentials, training optimizer states and model weights are **not distributed in this code repository**.

## Tests, models and license

```bash
python -m unittest discover -s local_service/tests -v
python -m unittest discover -s tests -v
```

Tests use mocked model responses and do not allocate a GPU or call a cloud endpoint. Frozen prompt parity is checked when original development artifacts exist; portable checkouts skip that data-dependent test. See [CHANGELOG](CHANGELOG.md), [Models / downloads](docs/MODELS.md), and [Apache-2.0 code license](LICENSE). Weight and dataset licenses must be checked separately. No GitHub release/tag is created by these scripts.

Legacy optional line-break experiments remain under `ordo/cleaning` and `scripts/run_full_pipeline.sh`; they require a separately compatible scoring model and are not the default 1.0 text API. Future work: structured-document → RAG chunk indexing.
