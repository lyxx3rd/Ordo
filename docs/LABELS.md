# Label reference

One label per nonempty physical input line. Original text is retained; blank lines do not receive labels.

| Label | Meaning |
| --- | --- |
| TEXT | Body content, including numbered obligations, definitions, explanations and continuation lines. Default. |
| NEW_DOCUMENT | Title starting an independent document. |
| HEADER | Repeated headers/footers or explicit standalone page numbers. |
| INFO_PAGE | Cover, revision, author, approval, version and other metadata. |
| H1 | Standalone first-level section heading, not mixed with substantive body text. |
| H2 | Standalone second-level section heading. |
| H3 | Standalone third-level or deeper heading; deeper levels are capped here. |
| HN | Unnumbered standalone local heading; not a fallback for numbered body text. |
| POINT | A genuinely enumerated/list item with a clear list marker; can contain full explanatory sentences. |
| TOC | A line from the original table of contents. |
| TABLE | An actual table row; not merely a paragraph inside a page border. |
| APPENDIX | Explicit appendix entry marker; subsequent text keeps its own content/heading labels. |

Numbering, length, colons, periods, bold appearance and indentation are not sufficient on their own to determine a class. Decide heading versus content first, then depth; real headings inside an appendix retain their real levels.

Local frozen rules: [labels.md](../local_service/ordo_local/assets/labels.md). Online few-shot rules/examples: [labels](../ordo/labels.md), [examples](../ordo/label_example.md). Chinese task prompts are kept unchanged to match the final model; English documentation does not imply translating the training prompts at inference time.

## Output views

- JSON: full ordered rows, line IDs, physical line numbers, labels and original text.
- TXT: aligned `[LABEL]` column followed by full text.
- Markdown: H1/H2/H3/HN map to `#`/`##`/`###`/`####`; document titles/appendix markers are bold, lists get bullet markers, headers/metadata become quoted annotations, tables are fenced text. It is not lossless Word/PDF layout restoration.

Markdown may contain input HTML/links. Disable raw HTML or sanitize at rendering time; do not treat arbitrary uploaded text as trusted HTML.
