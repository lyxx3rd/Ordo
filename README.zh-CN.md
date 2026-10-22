# Ordo 1.0

**把纯文本整理为可用的文档结构。**

[English / 英文主页](README.md) · 简体中文 · [模型下载](https://modelscope.cn/models/l424102993/Ordo_2B)

Ordo 识别文档标题、章节、正文、列表、表格、目录、附录、页眉和信息页，输出 **JSON／标签对齐 TXT／Markdown**，保留完整原文及原始行号。

适用于合同、体系文件、报告等长文档的结构整理，可用于构建章节目录，也可为后续检索和文档切片提供结构依据。

本地 **Qwen3.5-2B** 模型只需一次标记流程：不需要线上密钥、独立 Analyze 环节或额外加载 LoRA。也支持通过线上 API 使用 few-shot 方案。

## 看看实际效果

![原始 PDF、提取文本、Ordo 真实预测和 H1 分组](docs/assets/ordo-real-workflow.svg)

**原始 PDF → 纯文本 → Ordo 标签 → 按 H1 分组。** 来自 Bonterms 公开合同的真实节选，使用最终 2B 的实际预测结果。

[查看原始节选、标签与分组 JSON](examples/bonterms/README.md) · 来源 Bonterms，CC BY 4.0。

Ordo 接收 **UTF-8 纯文本**。PDF／Word 提取属于上游步骤；图中的 H1 分组是下游轻量示例，不是完整的 RAG 切片库。

## 能识别什么

| 标签 | 含义 |
| --- | --- |
| `TEXT` | 普通正文，包括带编号的正文 |
| `NEW_DOCUMENT` | 新文件的起始标题 |
| `H1` | 一级章节标题 |
| `H2` | 二级章节标题 |
| `H3` | 三级及更深层的章节标题 |
| `HN` | 无编号的局部小标题 |
| `POINT` | 明确的列举、列表或分点 |
| `TOC` | 原文件目录中的行 |
| `TABLE` | 表格中的行 |
| `APPENDIX` | 明确的附录标记或标题 |
| `HEADER` | 页眉、页脚或页码 |
| `INFO_PAGE` | 封面、信息页中的元数据 |

[查看完整标签说明](docs/LABELS.md)。Ordo 对已有文本进行标记，不恢复提取时丢失的表格，也不还原 PDF 原始版式。

## 效果如何

在相同的 **114 份文档／35,821 行**上，将保留的线上 few-shot 结果与最终本地模型进行比较：

| 方案 | 全标签准确率 | H1 F1 | H2 F1 | H3 F1 |
| --- | ---: | ---: | ---: | ---: |
| Qwen3.7-Plus，Analyze＋few-shot | 89.08% | 81.17% | 60.06% | 57.42% |
| Ordo 2B，单阶段 | **90.11%** | **90.68%** | **80.11%** | **88.75%** |

在完整的 **126 份文档／43,423 行**测试集上，Ordo 的全标签准确率为 **91.12%**；单张 RTX 3090、窗口并发 16，处理耗时 **539.5 秒**，不含模型启动。

[评估范围与详细指标](docs/BENCHMARKS.md)。

## 如何使用

### 选择运行方式

| 模式 | 适合场景 | 入口 |
| --- | --- | --- |
| API few-shot | 无本地 GPU，使用自己的线上密钥 | `scripts/run_online_structure.sh` |
| 本地一体式 | Python／Notebook 直接推理 | [Notebook](notebooks/local_inprocess.ipynb) |
| 本地解耦式 | 独立启动 vLLM，由客户端调用 | `scripts/serve_model.sh`＋`ordo-label` |
| 对外文本服务 | 供其他程序或内网用户调用 | [服务文档](docs/SERVICE.md) |

### 安装与下载

客户端／API 使用 Python 3.10+；GPU 推理建议使用独立的 Linux／NVIDIA＋Python 3.12 环境。

```bash
git clone https://github.com/lyxx3rd/Ordo.git
cd Ordo
python -m pip install -r requirements.txt

# 在 GPU 环境安装：
python -m pip install -r requirements-model.txt

# 如需 Notebook：
python -m pip install -r requirements-notebook.txt
```

从 [ModelScope](https://modelscope.cn/models/l424102993/Ordo_2B) 下载合并后的模型。也可安装 ModelScope SDK 后运行：

```python
from modelscope import snapshot_download
model_dir = snapshot_download("l424102993/Ordo_2B")
```

[模型与环境说明](docs/MODELS.md)。

### 1. API few-shot

```bash
cp ordo/config.example.yaml ordo/config.yaml
export ORDO_ONLINE_API_KEY='自己的密钥'
# 在配置中设置自己的渠道支持的模型和接口地址。
bash scripts/run_online_structure.sh examples/sample.txt outputs/online_example
```

先分析全文，再带示例逐批标记，保存标签、TXT、Markdown、目录及用量记录。密钥和私有配置不要提交 Git。

### 2. 本地一体式

运行 [Notebook](notebooks/local_inprocess.ipynb)，或直接在 Python 中调用：

```python
from ordo_local.offline import load_model, label_text
from ordo_local.client import save_result

llm = load_model("/path/to/Ordo-Qwen3.5-2B-Reviewed2-Final-BF16")
result = label_text(llm, "文件控制程序\n\n1. 目的\n\n本程序用于规范文件管理。")
save_result(result, "outputs/inprocess_example")
```

在导入 torch／vLLM 前通过 `CUDA_VISIBLE_DEVICES` 选择显卡。此模式不需要 HTTP 服务。

### 3. 本地解耦式

在 GPU 环境启动模型：

```bash
export ORDO_MODEL_PATH=/path/to/Ordo-Qwen3.5-2B-Reviewed2-Final-BF16
GPU=0 bash scripts/serve_model.sh
```

在客户端环境调用：

```bash
ordo-label examples/sample.txt --output outputs/local_example \
  --base-url http://127.0.0.1:8010/v1 --model ordo-final-2b --format json txt md
```

输出 `labels.json`、`labeled.txt`、`labeled.md`、`run.json`，不会覆盖已有文件。此模式不需要下方的业务 API。

### 4. 对外部署文本 API

```bash
cp local_service/config.example.json local_service/config.local.json
# 设置 model_path、model_python、GPU 和端口。
ordo-local init-token --config local_service/config.local.json
bash local_service/start.sh
```

管理器在后台启动模型和 API。不要同时在同一 GPU／端口上启动模式 3。

| 接口 | 用途 |
| --- | --- |
| `GET /health` | 检查 API 存活 |
| `GET /ready` | 检查模型就绪 |
| `POST /v1/label` | 提交 JSON 文本 |
| `POST /v1/label/file` | 上传 UTF-8 TXT |

```json
{"text":"文件标题\n\n1. 目的\n\n正文内容", "format":["json","txt","md"]}
```

响应中的 `files` 数组包含各文件的名称、媒体类型和文本内容。可选择一种或多种格式，不需要 ZIP 打包。

内网访问时，将 `api_host` 设置为 `0.0.0.0`，客户端使用服务器可达 IP。默认启用鉴权；明确设置 `auth_enabled: false` 后，所有网络可达者均可调用。

[完整 API 示例、后台运行与配置说明](docs/SERVICE.md)。

## 更多

- [模型下载与硬件说明](docs/MODELS.md)
- [标签规则](docs/LABELS.md)
- [详细评估](docs/BENCHMARKS.md)
- [更新记录](CHANGELOG.md)
- [Apache-2.0 代码许可](LICENSE)

代码与权重分别发布，不附带原始文档及训练数据。后续计划：结构化文档 → RAG 切片库。
