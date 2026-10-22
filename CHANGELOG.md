# Changelog

## 1.0.0 — 2026-10-22

- English-first README and Chinese README with reciprocal navigation.
- Four explicit modes: online few-shot, in-process vLLM notebook, model-only server/client, and managed text-upload API.
- Local inference targets the Dev-best final merged Qwen3.5-2B BF16 model; no runtime Analyze, examples, LoRA or label feedback.
- Shared frozen local prompt/renderer, JSON/TXT/Markdown exports, bounded requests and strict label validation.
- Background lifecycle tools, readiness/health, optional explicit anonymous deployment, upload limits and format-constrained retries.
- Portable configuration/dependency groups and verified ModelScope download links for the final merged weights.
- Sanitized historical benchmark aggregates; different datasets/timing scopes clearly identified.
- Matched historical Plus-versus-2B evaluation on 114 Test documents, with source breakdown and explicit limitations.
- Online Analyze/Label prompts updated from the development V2 path; JSON-map output and signed Label resume retained.
- Notebook ships without outputs. Original private datasets and GPU services are not accessed by the mock test suite.

Final merged weights are published separately at https://modelscope.cn/models/l424102993/Ordo_2B. Runtime scripts do not publish code or weights automatically.

## 0.1.0

Initial online Flash pipeline and optional NLL line-break-cleaning experiments. The latter remain optional legacy tools, not the default 1.0 service.
