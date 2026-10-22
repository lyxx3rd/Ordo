# Historical measurements and experiment notes

[English](../README.md) · [中文](../README.zh-CN.md) · [Sanitized machine-readable records](benchmarks.json)

These are existing development measurements, not a freshly run publication benchmark. No raw contracts, QMS documents, personal text or credentials are bundled. The JSON includes original artifact SHA256 values for provenance; development artifacts themselves are not shipped.

## A. Online few-shot calibration

Same12 QMS documents, 1912 scored lines after3 uncertain lines were excluded. Gold was an earlier reviewed baseline plus an explicit15-line adjudication overlay. Each model ran its own **Analyze + few-shot Label**, not an isolated Label-only test. These examples were used during prompt calibration, not an untouched blind test.

| Historical model ID | Accuracy | H1 F1 | H2 F1 | H3 F1 | Wall seconds | Input / output tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| qwen3.7-flash | 88.08% | 98.65% | 83.67% | 85.71% | 106.139 | 544067 / 23065 |
| qwen3.7-plus | 97.02% | 98.67% | 91.43% | 90.20% | 197.598 | 542588 / 22112 |
| qwen3.7-max | 96.55% | 99.34% | 89.72% | 85.39% | 163.104 | 542528 / 22573 |

Configured IDs depend on the provider route used at the time; availability and pricing are not asserted. Network latency, scheduling, prompt revision and document size affect wall time. Summed individual call times are larger because calls may overlap; do not sum them as elapsed wall time. No dollar-price comparison is estimated from current provider tariffs.

The 1.0 online pipeline is derived from the later development V2 code/prompts. It is a usable few-shot route, not a guarantee that calling today's endpoint reproduces these exact old predictions.

## B. Final 2B local Test

Different data: **126 mixed documents, 43,423 labeled lines, 2472 windows**. Dev selected epoch4 / checkpoint-3296 using `0.4 H1_F1 + 0.25 H2_F1 + 0.25 H3_F1 + 0.1 accuracy`.

| Accuracy | H1 F1 | H2 F1 | H3 F1 | Macro-F1 |
| ---: | ---: | ---: | ---: | ---: |
| 91.12% | 89.71% | 77.09% | 82.09% | 84.58% |

Historical inference: base+best-LoRA, one RTX3090,16 concurrent window requests, no Analyze, **539.518 seconds** excluding server startup. JSON-valid rate99.919%. This metric run is not a new complete merged-weight rerun.

**Do not rank these numbers against table A.** The test populations, annotation revisions, task protocols and scheduling differ. Train/Dev contain teacher labels and partial reviews; the Test was repeatedly inspected during development. No multi-seed confidence interval or complete near-template/source isolation was established.

## C. Matched historical Plus versus final 2B

Re-scored preserved `qwen3.7-plus` few-shot outputs and final 2B predictions against the **same frozen reviewed2 Test labels**. The overlap is **114 documents / 35,821 lines**: 43 QMS, 58 Chinese contracts, 8 English contracts and 5 French contracts. All line IDs and full source text were checked for equality; local evaluation gold was also checked against the frozen dataset. Invalid local responses remain errors, not default TEXT.

The other **12 open-source Test documents / 7,602 lines** have algorithmically converted source labels but no complete historical Plus run; they are excluded from **both** rows below. These are subset scores, not the full 126-document scores in section B.

| Method | Accuracy | H1 F1 | H2 F1 | H3 F1 | Macro-F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Historical Qwen3.7-Plus, Analyze + few-shot Label | 89.08% | 81.17% | 60.06% | 57.42% | 74.47% |
| Final local 2B, no Analyze / examples / feedback | 90.11% | 90.68% | 80.11% | 88.75% | 79.56% |

The local gain is **+1.03 accuracy points**, with H1/H2/H3 F1 gains of **+9.51 / +20.05 / +31.33 points**. This is not a universal superiority claim: frozen gold was created by reviewing teacher outputs, historical prompts/scheduling differ, and the data were inspected during development. Local predictions are from the original base+best-LoRA Test run, not a fresh merged-weight evaluation. No cloud requests were made for this retrospective scoring.

| Source | Documents | Lines | Plus accuracy | 2B accuracy |
| --- | ---: | ---: | ---: | ---: |
| BJ QMS | 8 | 3,175 | 94.30% | 91.02% |
| MB_02 QMS | 35 | 5,716 | 88.72% | 89.57% |
| Chinese public contract templates | 58 | 9,875 | 85.33% | 87.51% |
| Common Paper | 2 | 125 | 93.60% | 92.80% |
| Bonterms | 1 | 341 | 80.06% | 93.26% |
| CUAD | 5 | 1,555 | 86.37% | 83.99% |
| French ResourceContracts | 5 | 15,034 | 91.03% | 92.36% |

Plus Label-only accounting totals **9,716,343 input / 365,427 output tokens** and **8,515.289 summed document seconds**. That sum spans separate historical runs, excludes Analyze, and is **not** a wall-time throughput measurement. The 2B 539.518-second wall time in section B covers all 126 documents under different scheduling; no matched speedup ratio can be inferred. [Sanitized aggregate metrics](plus_matched_test.json) contain class-level TP/FP/FN and source-level results, but no document text, private paths or credentials.

## D. Merged model business-API acceptance

Same126 source documents were reconstructed as TXT and sent through the real text API, generating **JSON+TXT+MD**, at four-document /16-window concurrency. On a3090,0.45 GPU memory budget used approximately9620MiB.

- First pass: **417.283s**,124 successful documents and2 explicit502 errors from invalid model output.
- Remediation: keep initial decoding, but constrain invalid-output retries to the exact line IDs and12 labels using JSON Schema; no silent TEXT filling or prompt change.
- Retest only the two failed documents: both successful, **43.224s** parallel wall time.
- Execution-time sum460.507s excludes startup, readiness waiting, smoke warmup and the intervening implementation/restart interval. **This is not one fresh zero-failure full-set run after the fix.**

One historical ARXIV record contained a code block with internal newlines. As pure TXT it creates four additional nonempty physical lines (43,427 returned rows overall), so it was retained in timing but excluded from strict source-aligned label scoring. On the remaining125 documents /43,361 lines, using the two retest outputs, accuracy was91.22% and H1/H2/H3 F1 were89.82/77.10/82.38%. Do not replace table B with this subset score.

The inference engine, API and upload paths were actually run during development. The release notebook/offline wrapper is mock-tested rather than separately GPU-benchmarked. The code/tests do not require access to the private evaluation documents.

## E. Why other experiments were not delivered

| Experiment | Observed result / decision |
| --- | --- |
| Frozen2B window+paragraph embeddings with an MLP | Early12-document accuracy77.97%, H1/H2/H3 F1:64.60/45.34/13.19%; insufficient. Different early data, not a same-set ablation of table B. |
| Reference/oracle Analyze | Can improve labeling, but uses target-derived information unavailable in deployment; not a deployable score. |
| Generated Analyze + mixed-task SFT | Did not reliably recover the oracle gain; task interference versus model capacity was not conclusively separated. |
|9B NF4 + generated Analyze |126-document Test accuracy92.34%, H1/H2/H3 F1:90.64/79.89/85.14%; two stages took2433.8s. A modest precision benefit for higher cost, not the1.0 default. |
| Document-level GRPO on that9B |0.5/1.0/1.5-epoch Test accuracy92.25/92.13/92.19%, no stable overall gain over92.34% SFT. Stopped, retaining the0.5 checkpoint and records in development. This does not disprove GRPO generally. |
| NLL line-break repair | Some false joins combined headers and body text; retained as a separate legacy experiment, not required before labeling. |

The1.0 choice favors single-stage2B practicality, not a claim of state-of-the-art document-layout understanding. Future evaluations should use a newly isolated test set, targeted error categories and matched protocols before asserting algorithmic superiority.
