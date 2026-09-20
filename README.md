# A–E 病历分级 Agent

项目使用 LangGraph 编排两个 DeepSeek Agent：第一个 Agent 从病历提取结构化事实，第二个 Agent 审核提取结果。审核不通过时最多修正三次，随后由确定性规则引擎输出等级。2.0 对缺失事实不设默认值，而是返回所有可区分的可能分级。

规则引擎 2.0 输出示例：

```json
{"results": [{"grade": "B1", "has_r": false}, {"grade": "C1", "has_r": false}]}
```

## 目录

```text
medi/
├── ae_grading/          确定性规则引擎
├── ae_workflow/         LangGraph与DeepSeek Agent
├── cases/               虚构测试病例
├── docs/                规则规范和学习笔记
├── tests/               自动化测试
├── web_app/             规则引擎测试网页
├── run_deepseek.py      Agent工作流入口
├── run_web.py           规则引擎网页入口
└── pyproject.toml       Python项目与依赖配置
```

## 配置 DeepSeek

在项目根目录创建`.env`：

```dotenv
DEEPSEEK_API_KEY=你的真实API密钥
DEEPSEEK_MODEL=deepseek-v4-flash
```

`.env`已被Git忽略。也可以复制`.env.example`后再填写。

## 运行

直接运行时默认读取`cases/case2.txt`：

```bash
.venv/bin/python run_deepseek.py
```

指定其他病例：

```bash
.venv/bin/python run_deepseek.py cases/case3.txt
```

运行全部测试：

```bash
.venv/bin/python -m unittest discover -s tests
```
