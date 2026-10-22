# Models, downloads and environments

[English](../README.md) · [中文](../README.zh-CN.md)

## Final artifact

| Field | Value |
| --- | --- |
| Artifact name | `Ordo-Qwen3.5-2B-Reviewed2-Final-BF16` |
| Model | Qwen3.5-2B, merged BF16 |
| Selected adapter before merging | epoch 4 / checkpoint-3296 (Dev best, not last) |
| Runtime LoRA | Not needed for this merged artifact |
| Analyze / few-shot / feedback | None for the local model |
| Model download URL | [ModelScope: l424102993/Ordo_2B](https://modelscope.cn/models/l424102993/Ordo_2B) |
| Download checksum manifest | `checksums.json` in the model repository |
| Dataset download | Not provided in 1.0 |

**Modes 2–4 require the final trained weights; the upstream base alone is not equivalent.** Mode 1 can be used with a compatible provider and your own credentials.

```python
from modelscope import snapshot_download
model_dir = snapshot_download('l424102993/Ordo_2B')
```

Install `modelscope` in the download environment if needed. The published repository includes the merged weights, tokenizer/configuration, frozen labeling prompt and SHA-256 checksums; no training documents or optimizer states are included.

After obtaining the weights, copy the complete folder, not only its safetensors: config, tokenizer, generation/preprocessing configs and all shards are needed. Suggested location is `models/Ordo-Qwen3.5-2B-Reviewed2-Final-BF16` under the repository root. The example service config points to `../models/...` relative to `local_service/config.local.json`.

The original base and best adapter were retained in development. The standalone merge was reloaded and checked with two short CPU forward probes; BF16 rounding differences exist. Historical complete-Test metrics refer to the unmerged base+LoRA; merged-API acceptance is reported separately in [BENCHMARKS](BENCHMARKS.md).

## Dependencies

- API/client: Python 3.10+, `requirements.txt`; no GPU torch/vLLM required for this environment.
- Model engine: separate Python 3.12 Linux/NVIDIA environment, `requirements-model.txt` pins the tested `vllm==0.31.0`.
- Notebook: `requirements-notebook.txt`; select that GPU environment as the notebook kernel.
- Development inference environment reported vLLM 0.31.0, torch 2.13.0 and Transformers 5.17.0. These are provenance, not a promise that mixing them into an existing environment is safe. vLLM must resolve a supported torch/CUDA combination for your installation.
- API dependencies use bounded compatibility ranges, not a complete reproducible environment lock. GPU driver/CUDA and optional kernels remain machine-specific.

On the tested RTX 3090 24GB: model+runtime used about 9620 MiB with a 0.45 budget, max context8192 and sequence limit16. GPU utilization settings are not weight sizes; do not assume a 0.2 budget works because the model is 2B. Do not share an occupied GPU without explicit memory planning.

Default startup scripts keep CUDA Graph behavior and enable prefix caching. They do not force eager mode or install packages automatically. A cold engine startup includes weight load/compilation/graph warmup and is excluded from the historical inference timings.

## Licensing and publication

Repository code is Apache-2.0; upstream weights and any future trained-weight distribution have their own applicable terms. Review the actual model's license before redistributing it. No private training documents, old Deli contracts, keys, internal addresses or optimizer checkpoints should be uploaded with a release. The notebook has no saved model outputs.
