# A–E 病历分级 Agent

项目使用 LangGraph 编排两个 DeepSeek Agent：第一个 Agent 从病历提取结构化事实，第二个 Agent 审核提取结果。审核不通过时最多修正三次，随后由确定性规则引擎输出等级。未提及的原始事实仍保持缺失标记；规则计算按运行时字段注册表中的默认值处理，未设置默认值时返回所有可区分的可能分级。

当前输入包含 35 个原始事实字段。现行分级条件、字段契约和系统边界分别见[规则引擎规范](docs/规则引擎规范.md)、[字段策略](docs/字段策略.md)与[系统架构](docs/ARCHITECTURE.md)；README 不另行维护规则副本。

规则引擎输出示例：

```json
{"results": [{"grade": "C1", "has_r": false}, {"grade": "B1", "has_r": false}]}
```

## 目录

```text
medi/
├── cases/               虚构测试病例
├── docs/                现行规范、文档导航、参考资料和归档
├── src/medi/            唯一 Python 包
│   ├── grading/         确定性规则引擎与事实契约
│   ├── workflow/        LangGraph 与 DeepSeek Agent
│   ├── web/             FastAPI 医生工作台、PDF/OCR 与规则实验页
│   └── cli.py           grade / web 命令入口
├── tests/               自动化测试
├── AGENTS.md            AI 修改项目时的简短约定
└── pyproject.toml       Python项目与依赖配置
```

## 文档

[文档导航](docs/README.md)区分现行规范、参考资料与归档；AI 修改约定见 [AGENTS.md](AGENTS.md)。

## 安装

需要 Python 3.10 或更高版本。在项目根目录创建虚拟环境并安装依赖。扫描版 PDF 的 OCR 另外需要本机 Tesseract 和 `chi_sim`、`eng` 语言包；可复制文本的 PDF 无需 OCR：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

## 配置 DeepSeek

在运行命令时的当前目录创建 `.env`；进程环境变量优先于文件中的同名值：

```dotenv
DEEPSEEK_API_KEY=你的真实API密钥
DEEPSEEK_MODEL=deepseek-v4-flash
```

项目根目录的 `.env` 已被 Git 忽略，也可以复制 `.env.example` 后再填写。在其他目录运行 `medi` 时，该目录的 `.env` 才会被读取；也可直接设置环境变量。

## 运行

从项目根目录运行示例病例（必须明确给出路径）：

```bash
.venv/bin/medi grade cases/case3.txt
```

也可从标准输入读取，或用 `python -m medi` 调用同一命令：

```bash
.venv/bin/medi grade - < cases/case2.txt
.venv/bin/python -m medi grade cases/case3.txt
```

启动本地医生工作台：

```bash
.venv/bin/medi web
```

打开 `http://127.0.0.1:8765/`，可粘贴病历或上传 PDF；PDF 转成文字后会自动执行提取、审核和分级。病历文本可在下一次分析前修改。结果页展示所有可能等级，结构化事实和证据可人工修订，修订后仅重新运行规则引擎。手工规则实验页位于 `/lab`。

这是本地研究原型：病历会发送给配置的 DeepSeek 服务，当前无脱敏、鉴权、审计或持久化功能，不应直接用于临床决策或在未经合规评估的环境处理真实敏感病历。

运行全部测试：

```bash
.venv/bin/python -m unittest discover -s tests -q
```
