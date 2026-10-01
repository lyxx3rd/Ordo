# Ordo

Turn documents into structure.

Ordo is a document-structuring pipeline for semi-structured business and technical files. It turns extracted text into a clean, navigable Markdown outline while preserving the source order.

## What it does

- Cleans likely accidental line breaks in extracted PDF text.
- Identifies document boundaries in concatenated files.
- Labels document elements, including titles, headings, tables, table of contents, appendices, bullets, page headers, and information pages.
- Reconstructs a Markdown representation and a machine-readable outline.

The initial release uses an online Qwen Flash model for reliable structure analysis and batch labeling. A local small-model / LoRA backend is planned as an offline alternative.

## Labels

| Label | Meaning |
| --- | --- |
| `TEXT` | Ordinary body text; default. |
| `NEW_DOCUMENT` | Title starting a new document. |
| `H1` / `H2` / `H3` | Body heading. |
| `TOC` | A line belonging to the source table of contents. |
| `TABLE` | A line belonging to a table. |
| `APPENDIX` | Explicit appendix marker. |
| `POINT` | A formal parallel bullet or numbered item. |
| `HEADER` | Repeated page header, outside the body. |
| `INFO_PAGE` | Cover, version, approval, or other document metadata. |

## Pipeline

```text
source file
  -> text extraction
  -> conservative line-break cleanup
  -> global structure analysis
  -> batch labeling with context
  -> outline JSON + Markdown
```

## Quick start

This repository expects a UTF-8 text file already extracted from the source document. PDF extraction/OCR is deliberately outside the first release.

```bash
python -m pip install -r requirements.txt
cp ordo/config.example.yaml ordo/config.yaml
# Edit api_keys_path to point at a JSON file holding the Qwen_deli key.
```

For an already cleaned text file, reproduce the current online structural pipeline:

```bash
bash scripts/run_online_structure.sh input.txt outputs/example
```

This writes the global analysis, row labels, Markdown outline, reconstructed Markdown, and token/time metrics to `outputs/example`.

To include conservative line-break cleanup first, start a local OpenAI-compatible Qwen service (development default: `http://127.0.0.1:8010/v1/completions`) and run:

```bash
bash scripts/run_full_pipeline.sh input.txt outputs/example
```

`LINEBREAK_API_URL`, `LINEBREAK_MODEL`, and `ORDO_PYTHON` may be overridden through environment variables. The online model and API-key location are configured in the local, Git-ignored `ordo/config.yaml`.

## Reproducibility

The scripts, prompts, model selection, batch parameters, and cleanup thresholds reproduce the current pipeline. The online Flash endpoint is generative: repeated calls may yield different valid labels even with `temperature=0`. Keep generated labels and metrics when an exact run needs to be preserved.

## Status

`v0.1.0` is an initial, incomplete release of the online Qwen pipeline. It is suitable for reproducing the current text-cleaning and document-structure experiments, not yet a complete document-processing product.

## Roadmap

1. Train and integrate a local model backend for global analysis and structural labeling.
2. Convert structured documents into a RAG-ready chunk library, preserving headings, document boundaries, and source traceability.

## Principles

- Be conservative when changing source text.
- Keep labels small and portable across document types.
- Separate text cleanup, structural analysis, and rendering.
- Preserve traceability from every output item back to its source text.

## License

License to be selected before the first public release.
