# Ordo 1.0

**把纯文本整理为可用的文档结构。**

[English / 英文主页](README.md) · 简体中文

Ordo识别文档标题、章节、正文、列表、表格、目录、附录、页眉和信息页，输出 **JSON／标签对齐TXT／Markdown**，保留完整非空行原文及原始行号。

推荐本地模型是 **Qwen3.5-2B最终Best合并BF16模型**：第4轮checkpoint-3296，由Dev选出，不是Last。部署不需要额外加载LoRA，不调用Analyze、不回填标签，也不需要线上密钥。API few-shot方案作为独立模式保留。

> 输入仅限UTF-8纯文本。PDF/Word提取、OCR、精确版面复原和RAG切片库不属于1.0的四种标准模式。模型已发布至[ModelScope](https://modelscope.cn/models/l424102993/Ordo_2B)，见[模型说明](docs/MODELS.md)，代码仓库不包含权重。

## 四种使用模式

| 模式 | 运行方式 | 入口 |
| --- | --- | --- |
| 1. API few-shot | 线上模型Analyze→带示例的逐批Label，需要自己的API key | `scripts/run_online_structure.sh` |
| 2. 本地一体式 | 在Notebook/Python中加载vLLM直接推理，不开HTTP端口 | [Notebook](notebooks/local_inprocess.ipynb) |
| 3. 本地解耦式 | 单独运行模型服务，独立Python/CLI客户端调用 | `scripts/serve_model.sh`、`ordo-label` |
| 4. 对外文本服务 | 后台模型＋文本/TXT业务API，供其他程序或内网调用 | [服务说明](docs/SERVICE.md) |

模式2–4共用冻结的本地提示词和渲染：每批当前18个非空行，前后最多各18行原文，分别截断50/200/50**字符**，不是token。模型输入截断不影响最终导出的完整正文。

## 安装

从仓库根目录执行。API/客户端需要Python3.10+；GPU模型环境推荐Linux/NVIDIA＋Python3.12，与轻量API环境分开。

```bash
# 线上API、业务API及轻量客户端，不安装GPU模型运行时
python -m pip install -r requirements.txt

# 在独立GPU环境安装；本机验证过vLLM 0.31.0
python -m pip install -r requirements-model.txt

# 如需Notebook，在GPU环境中额外安装
python -m pip install -r requirements-notebook.txt
```

安装和import不会自动启动服务。不要未经检查就向已有训练环境安装另一套torch/CUDA依赖。

## 模式1：API few-shot

```bash
cp ordo/config.example.yaml ordo/config.yaml
export ORDO_ONLINE_API_KEY='自己的密钥'
# 可设置ORDO_ONLINE_BASE_URL、ORDO_ONLINE_MODEL
bash scripts/run_online_structure.sh examples/sample.txt outputs/online_example
```

模型名称必须与你自己的渠道一致，历史记录中的Flash/Plus/Max名称不代表任意平台都可用。
当前代码面向支持JSON-object和thinking开关的Qwen兼容OpenAI接口。
配置、密钥均不应提交Git。也可使用JSON密钥文件，默认字段`Qwen_deli`，`ORDO_ONLINE_KEY_FIELD`可覆盖字段名。

该模式使用`ordo/labels.md`和`ordo/label_example.md`，先全文Analyze，再逐窗Label；输出分析结果、标签、TXT、MD、目录及token/耗时记录。
Label可按签名断点续跑，但外层sh会重做Analyze；若分析结果发生变化，旧Label缓存会被拒绝。需要严格续跑时，复用原Analyze文件直接运行Python标记入口。

## 模式2：本地一体式

下载最终合并模型，设置`ORDO_MODEL_PATH`、选择空闲GPU后，运行[Notebook](notebooks/local_inprocess.ipynb)。它通过`vllm.LLM.chat`直接推理，不启动HTTP服务。

```python
from ordo_local.offline import load_model, label_text
from ordo_local.client import save_result

llm = load_model("/path/to/Ordo-Qwen3.5-2B-Reviewed2-Final-BF16")
result = label_text(llm, "文件控制程序\n\n1. 目的\n\n本程序用于规范文件管理。")
save_result(result, "outputs/inprocess_example")
```

在import torch/vLLM之前设置`CUDA_VISIBLE_DEVICES`。Notebook未预先执行，不含输出；离线调用流程有模拟测试，本次整理没有重新启动GPU实测Notebook。使用结束后重启kernel可释放模型工作进程。

## 模式3：本地解耦式

在GPU环境启动模型：

```bash
export ORDO_MODEL_PATH=/path/to/Ordo-Qwen3.5-2B-Reviewed2-Final-BF16
GPU=0 bash scripts/serve_model.sh
```

如需后台运行：

```bash
mkdir -p outputs
nohup env GPU=0 bash scripts/serve_model.sh > outputs/model.log 2>&1 < /dev/null &
```

在轻量客户端环境调用：

```bash
ordo-label examples/sample.txt --output outputs/local_example \
  --base-url http://127.0.0.1:8010/v1 --model ordo-final-2b --format json txt md
```

不需要启动业务API。客户端按默认16并发调用模型，输出`labels.json`、`labeled.txt`、`labeled.md`、`run.json`；已有输出不覆盖。
模型端口默认只监听回环，外部调用建议使用模式4，而不是裸露模型端口。

## 模式4：对外部署业务API

```bash
cp local_service/config.example.json local_service/config.local.json
# 修改model_path、model_python、GPU、端口；相对路径按配置文件目录解析
ordo-local init-token --config local_service/config.local.json
bash local_service/start.sh
```

如果启动sh使用的Python不是API环境，可设置`ORDO_API_PYTHON`。后台管理器启动模型和API；与模式3择一运行，不要争用同一GPU/端口。

- `GET /health`：API是否存活。
- `GET /ready`：目标模型是否可用。
- `POST /v1/label`：传JSON字符串。
- `POST /v1/label/file`：上传UTF-8 TXT。

```json
{"text":"文件标题\n\n1. 目的\n\n正文内容", "format":["json","txt","md"]}
```

无论选择一种或多种格式，始终返回同一JSON响应中的`files`数组，每项包含文件名、媒体类型和字符串内容；不打ZIP，不传Base64，不生成临时链接。调用方自行分别写文件。

内网访问需把`api_host`改为`0.0.0.0`，客户端访问服务器可路由的内网IP；还需防火墙/ACL允许对应端口。
默认对外部署要求token；明确设置`auth_enabled: false`可允许所有网络可达者匿名调用。显存预算默认0.45，本机3090已验证，但不是所有硬件/输入的保证。
完整接口、curl/Python保存文件示例、启停和报错见[服务文档](docs/SERVICE.md)。

## 简单历史对比

已从历史结果中找到共同的 **114份Test／35,821行**，按相同冻结标签重新评分：

| 方案 | 准确率 | H1 F1 | H2 F1 | H3 F1 |
| --- | ---: | ---: | ---: | ---: |
| Qwen3.7-Plus，Analyze＋few-shot | 89.08% | 81.17% | 60.06% | 57.42% |
| 最终本地2B，单阶段 | 90.11% | 90.68% | 80.11% | 88.75% |

两方均排除了没有完整Plus初标结果的12份开源文档。此表是历史回溯比较，不是新跑的受控实验；基准来自教师初标后复核，且历史提示词有版本差异。耗时记录口径不同，不据此计算加速倍数。[范围、分来源结果与统计明细](docs/BENCHMARKS.md#c-matched-historical-plus-versus-final-2b)。

以下是另外两组不同范围的历史记录，不能跨测试集排名：

以下只整理已有记录，不重新推理。线上三行来自12份QMS校准样本、1912个计分行；本地来自另一套126份混合Test、43,423行。**不能据此跨数据集判定谁更强。**

| 方案 | 数据范围 | 准确率 | H1 F1 | H2 F1 | H3 F1 | 历史耗时 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Qwen3.7-Flash few-shot | 12份QMS校准 | 88.08% | 98.65% | 83.67% | 85.71% | 106.1秒 |
| Qwen3.7-Plus few-shot | 同上 | 97.02% | 98.67% | 91.43% | 90.20% | 197.6秒 |
| Qwen3.7-Max few-shot | 同上 | 96.55% | 99.34% | 89.72% | 85.39% | 163.1秒 |
| 本地最终2B，无Analyze | 126份混合Test | 91.12% | 89.71% | 77.09% | 82.09% | 539.5秒¹ |

¹ 基座＋Best LoRA的历史单卡3090评估，窗口并发16，不含启动；线上耗时包含各自Analyze＋Label，使用当时的调度方式。
后续合并模型业务API验收首轮126份耗时417.3秒，124成功、2份格式失败；部署结构化重试后仅复测失败项，43.2秒全部成功。不能把两轮拼成一次零失败的完整基准。
详细来源和脱敏统计见[历史记录](docs/BENCHMARKS.md)。

最终选2B是速度、成本和效果的取舍，不是精度最高。9B NF4＋生成Analyze在混合Test上达到92.34%，但两阶段约40.6分钟；所测GRPO没有稳定整体提升，均不作为1.0交付。

## 标签、限制与公开范围

12类：`TEXT / NEW_DOCUMENT / HEADER / INFO_PAGE / H1 / H2 / H3 / HN / POINT / TOC / TABLE / APPENDIX`。
[标签摘要](docs/LABELS.md)与[本地冻结完整规则](local_service/ordo_local/assets/labels.md)。超过三级的真实标题统一H3，HN不是H4；带编号的正文不自动变标题或列表。

H2/H3层级、标题/正文/列表边界仍会出错。提取阶段已经丢失的表格或布局不能靠标记可靠恢复；MD是结构化阅读版，不是原版式还原。
Train/Dev为教师标签和不同范围人工审核的混合数据；历史Test已参与多轮开发分析，不是完全盲测。没有完成近模板/全部来源隔离、多seed显著性验证。
代码仓库不提供私有QMS、合同原文、密钥、训练优化器或权重；代码Apache-2.0，数据和权重许可另行核对。

```bash
python -m unittest discover -s local_service/tests -v
python -m unittest discover -s tests -v
```

测试使用模拟模型，不启动GPU或访问线上服务。原训练产物存在时会校验冻结窗口；发布副本缺少私有产物时跳过该项。
见[下载占位与模型要求](docs/MODELS.md)、[更新记录](CHANGELOG.md)、[代码许可](LICENSE)。本轮准备1.0文件，不自动提交、打tag或发布GitHub。
旧换行清洗代码保留为实验性可选工具，不是标准1.0文本服务前置步骤；后续方向是结构化结果到RAG切片库。
