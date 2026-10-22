# Real workflow example: Bonterms Software License Terms

Source: **Bonterms, Inc. (2025), Bonterms Software License Terms, Version 1.0**.
Original publication: https://bonterms.com/download-center/software-license-terms

The original PDF footer explicitly states: “© 2025 Bonterms, Inc. Free to use under CC BY 4.0”.
License: [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
This excerpt, screenshot crop and adaptations retain that attribution. No endorsement by Bonterms is implied.

## What is real, and what was changed?

- PDF panel: actual crop of page 1, sections 2–3; no reconstructed or AI-generated PDF image.
- Text panel: existing native-PDF text extraction, matching a new `pdftotext -layout` extraction after whitespace normalization.
- Labels: actual predictions from final Dev-best 2B checkpoint-3296, preserved from the base+LoRA Test run. They are **not** substituted human labels or a fresh merged-model inference.
- Groups: deterministic splitting at predicted H1 lines; heading and subsequent rows stay together until the next H1. This demonstrates postprocessing, not a complete RAG chunking system.
- The SVG shortens text and compacts whitespace for readability. Explicit omission markers are display-only. Full rows for the contiguous excerpt are retained in the accompanying files.
- This is a selected illustrative excerpt, not evidence that the complete document has no labeling errors.

## Files

| File | Content |
| --- | --- |
| `input.txt` | Unlabeled contiguous excerpt from the existing extracted text |
| `labels.json` | Same full source lines with stable original line IDs and actual predicted labels |
| `labeled.txt` | Readable label-aligned version |
| `chunks.json` | Two H1-based groups; no body lines silently dropped |
| `provenance.json` | Original PDF hash, page/crop coordinates, source line IDs and modification record |

The full PDF is not bundled. Upstream extraction and downstream grouping are outside the Ordo labeling model. This example intentionally does **not** claim OCR repair or header filtering.

## 中文

这是来自 Bonterms 公开合同的真实片段，不是虚构样例。授权为 CC BY 4.0，原 PDF 页脚有明确声明。图中使用原始页面裁剪、原生提取文本、最终 2B 的历史真实预测，再根据预测的 H1 分成两个段落组。只在图上压缩空白、省略部分内容；随附 JSON/TXT 保留完整节选。没有用人工标签替换模型输出，也不代表整篇合同没有识别错误。
