# Travel Agent（小途 AI）使用文档

面向旅游场景的多智能体旅行规划项目：对话式需求收集、RAG 检索、本地 Skill 调用（天气 / POI / 酒店 / 航班 / 黄历）与 Flask Web 界面，根据用户输入生成完整 Markdown 行程。

---

## 1. 项目能力概览

| 模块 | 说明 |
|------|------|
| **对话收集** | 逐步询问旅行类型、天数、预算、**出发地**、人数、**出发日期**（均支持可点击选项） |
| **多智能体** | Planner 决定调用哪些工具 → Executor 执行 → LLM 生成最终规划 |
| **RAG** | Chroma 向量库检索小红书等攻略笔记（当前数据以日韩泰为主） |
| **Skill 工具** | 见下表 |

### 1.1 已接入 Skill 工具

| 工具名 | 能力 | 依赖 | Skill 资源 |
|--------|------|------|------------|
| `weather_lookup` | 境内天气 | `AMAP_WEBSERVICE_KEY` | 高德 API |
| `poi_search` | 境内 POI / 景点 | `AMAP_WEBSERVICE_KEY` | 高德 API |
| `hotel_search` | 酒店候选与价格 | `ROLLINGGO_API_KEY` + Node.js | `npx rollinggo@latest` |
| `flight_search` | 航班班次、时刻、参考价 | `ROLLINGGO_API_KEY` + Node.js | `.agents/skills/rollinggo-flight-skill` → `npx rollinggo-flight@latest` |
| `calendar_lookup` | 农历、宜忌、建除、值神 | Python + 黄历脚本 | `.agents/skills/lao-huangli` |

**运行时说明：**

- **境外目的地**（如东京、首尔）：自动**跳过**高德 weather / POI，仍查询酒店、黄历、航班。
- **黄历**：用户提供日期或「X 月初 / 灵活择日」时，可查询最多 3 个候选日。
- **航班**：固定按 **1 成人** 查询，展示班次与时刻（**1 成人参考价**），与同行人数无关；国际线优先使用机场三字码（如 PEK→ICN）。
- **酒店**：境外目的地自动映射英文城市名（如 Seoul、Tokyo）并传入 `country-code`。

---

## 2. 目录结构

```text
TravelAgent-main/
├── main.py                          # 入口，启动 Flask
├── requirements_agent.txt             # Python 依赖（含 skyfield / jplephem 黄历）
├── .env                             # 环境变量（勿提交密钥）
├── .env.example                     # 环境变量模板
├── skills-lock.json                 # ModelScope Skill 安装记录
├── config/mcp_servers.json          # MCP 配置示例（运行时以 SkillRunner 本地执行为主）
├── .agents/skills/
│   ├── lao-huangli/                 # 老黄历（ModelScope @cikichen/lao-huangli）
│   └── rollinggo-flight-skill/      # 机票 CLI 说明（ModelScope yorklu/rollinggo-flight-skill）
├── travel_agent/
│   ├── multi_agent/                 # Planner / Executor / Coordinator
│   ├── skills/runner.py             # Skill 统一执行层
│   ├── rag/                         # 向量库与检索
│   ├── models/                      # UserProfile、TripPlan
│   └── utils/travel_date.py         # 出发日期解析与黄历候选日
├── web/                             # Flask 路由与前端
├── scripts/test_rag.py              # RAG 测试
├── chroma_db/                       # 向量库（运行后生成）
└── LittleCrawler/                   # 独立爬虫子项目（可选，非主流程必需）
```

---

## 3. 环境准备

### 3.1 基础要求

- **Python** 3.10 或 3.11
- **Conda**（推荐）或 venv
- **Node.js 18+** 与 `npx`（酒店 / 航班 CLI）
- **Windows**：建议安装 [Node.js LTS](https://nodejs.org/) 到 `C:\Program Files\nodejs`，避免 conda 自带 Node 16 导致 `fetch is not defined`

### 3.2 创建 Conda 环境

```powershell
conda create -n Alice python=3.10 -y
conda activate Alice
cd D:\TravelAgent-main\TravelAgent-main
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements_agent.txt
pip install modelscope
```

黄历相关依赖已写入 `requirements_agent.txt`（`skyfield`、`jplephem`）。

### 3.3 检查 Node.js

```powershell
node -v    # 建议 v18+
npx -v
```

若 `node -v` 仍为 16.x，请在 `.env` 中设置：

```env
TRAVEL_AGENT_NODEJS_DIR=C:\Program Files\nodejs
```

---

## 4. 安装 / 更新 ModelScope Skills

项目通过 ModelScope 维护 `.agents/skills/` 下的 Skill 文档与黄历脚本；**实际执行**由 `travel_agent/skills/runner.py` 完成。

```powershell
pip install --upgrade modelscope

# 老黄历（注意需要 @ 前缀）
modelscope skills add "@cikichen/lao-huangli" --local_dir ".agents\skills"

# 机票 Skill 说明包（无 @ 前缀）
modelscope skills add "yorklu/rollinggo-flight-skill" --local_dir ".agents\skills"
```

**说明：**

- 黄历 reinstall 后若出现 GBK 解码错误，需确认 `huangli_calc.py` 与 `rule_engine.py` 使用 `encoding="utf-8"` 读 profile（官方包偶发缺失）。
- 酒店 CLI 来自 npm 包 `rollinggo@latest`，无需单独下载到 `.agents/skills`。
- RollingGo API Key 申请：<https://rollinggo.store/apply>

---

## 5. 环境变量

复制模板并填写：

```powershell
copy .env.example .env
```

### 5.1 必填

| 变量 | 用途 |
|------|------|
| `DASHSCOPE_API_KEY` | LLM 对话与 Embedding |
| `AMAP_WEBSERVICE_KEY` | 境内天气、POI |
| `ROLLINGGO_API_KEY` | 酒店、航班查询 |

### 5.2 可选

| 变量 | 用途 |
|------|------|
| `PORT` | Web 端口，默认 `5000` |
| `FLASK_DEBUG` / `FLASK_RELOAD` | Flask 调试与热重载 |
| `TRAVEL_AGENT_HUANGLI_SCRIPT` | 覆盖黄历脚本路径 |
| `TRAVEL_AGENT_HUANGLI_PROFILE` | 黄历规则 profile，默认 `market-folk-v1` |
| `TRAVEL_AGENT_NODEJS_DIR` | Windows 下指定 Node 18+ 安装目录 |
| `PYTHONUTF8=1` | 减少 Windows 终端中文乱码 |

`.env` 加载顺序：项目根目录 `.env` → 上一级目录 `.env`。

---

## 6. 启动与使用

### 6.1 启动 Web 服务

```powershell
conda activate Alice
cd D:\TravelAgent-main\TravelAgent-main
python main.py
```

浏览器打开：<http://127.0.0.1:5000>

### 6.2 对话流程（Web）

1. 输入目的地（如「我想去韩国首尔玩 3 天」）
2. 依次回答：**旅行类型 → 天数 → 预算 → 出发地 → 人数 → 出发日期**
3. 确认是否还有补充需求
4. 生成规划（终端可看到 `[Skill] calling tool=...` 日志）

**出发日期选项示例：** 本周末 / 下周末 / X 月初 / 灵活择日（黄历推荐）

### 6.3 推荐测试用例

**境内 + 高德：**

```text
我想去苏州玩3天，6月20日出发，预算4000，想看园林
```

**境外 + 黄历 + 酒店 + 航班：**

```text
我想从北京去首尔玩3天，6月20日出发，预算3000，家庭出游
```

**境外东京：**

```text
我想去日本东京玩4天，本周末出发，预算5000，独自旅行
```

> RAG 向量库目前以**韩国、日本、泰国**内容为主，境外测试效果更佳。

### 6.4 规划输出说明

- 有黄历数据时 → 输出 **「出行择日建议」**（含宜忌、建除、值神）
- 有航班数据时 → 输出 **「交通参考（机票）」**（航班号、机场、时间、是否中转、1 成人参考价）
- 有酒店数据时 → 行程与预算引用实时查价
- 航班查询失败时 → 不写具体班次/价格，标注「待查询」（不会编造 CAxxxx）

---

## 7. 多智能体工具调度规则

Planner 会根据用户画像与对话摘要决定工具，Executor 通过 `SkillRunner` 执行。Postprocess 规则包括：

| 条件 | 行为 |
|------|------|
| 境外目的地 | 移除 `weather_lookup`、`poi_search` |
| 有出发日期 / 择日意图 | 加入 `calendar_lookup`（最多 3 个日期） |
| 境外 + 已知出发地 + 日期 | 加入 `flight_search`（origin/destination 自动归一化，如「日本东京」→「东京」） |
| 有目的地与入住日期 | 加入 `hotel_search`（境外用英文 place + country-code） |

---

## 8. RAG 数据

数据需手动导入，启动时不会自动导入。

```powershell
python -m travel_agent.rag.ingest_data --json .\restaurant_contents_319.json --dir .\chroma_db --collection restaurant
python .\scripts\test_rag.py "首尔 3天 攻略" --collection restaurant --top-k 5
```

检索结果为空时，检查：是否已导入、`collection` 名称、`DASHSCOPE_API_KEY`、查询词是否与库内目的地匹配。

---

## 9. Skill 单独测试

先加载 `.env`：

```powershell
cd D:\TravelAgent-main\TravelAgent-main
python -c "from dotenv import load_dotenv; load_dotenv('.env'); ..."
```

### 9.1 黄历

```powershell
python -c "from dotenv import load_dotenv; load_dotenv('.env'); from travel_agent.skills import SkillRunner; r=SkillRunner().execute_tool('calendar_lookup', {'date':'2026-06-20'}); print(r.success); print(r.to_summary()[:500])"
```

### 9.2 酒店（境外）

```powershell
python -c "from dotenv import load_dotenv; load_dotenv('.env'); from travel_agent.skills import SkillRunner; r=SkillRunner().execute_tool('hotel_search', {'destination':'Seoul','check_in_date':'2026-06-20','check_out_date':'2026-06-22','stay_nights':2}); print(r.success); print(r.to_summary()[:400])"
```

### 9.3 航班

```powershell
# 国内
python -c "from dotenv import load_dotenv; load_dotenv('.env'); from travel_agent.skills import SkillRunner; r=SkillRunner().execute_tool('flight_search', {'origin':'北京','destination':'上海','travel_date':'2026-06-20'}); print(r.success); print(r.to_summary()[:400])"

# 国际（即使传入 adult_number=5，内部也按 1 成人查）
python -c "from dotenv import load_dotenv; load_dotenv('.env'); from travel_agent.skills import SkillRunner; r=SkillRunner().execute_tool('flight_search', {'origin':'北京','destination':'首尔','travel_date':'2026-06-20','adult_number':5}); print(r.success); print(r.to_summary()[:400])"
```

### 9.4 天气 / POI（仅境内）

```powershell
python -c "from dotenv import load_dotenv; load_dotenv('.env'); from travel_agent.skills import SkillRunner; r=SkillRunner().execute_tool('weather_lookup', {'city':'苏州'}); print(r.success); print(r.to_summary())"
```

---

## 10. 常见问题

### 10.1 `DASHSCOPE_API_KEY` 未配置

```powershell
python -c "import os; from dotenv import load_dotenv; load_dotenv('.env'); print(bool(os.getenv('DASHSCOPE_API_KEY')))"
```

### 10.2 酒店报错 `fetch is not defined`

conda 内 Node 版本过旧。安装 Node 18+ 并设置 `TRAVEL_AGENT_NODEJS_DIR`，或把系统 Node 目录置于 PATH 最前。

### 10.3 航班 `未能解析城市/机场代码`

- 使用中文城市名即可（如「首尔」「东京」），勿写「日本东京」；系统会自动归一化。
- 若仍失败，检查 `ROLLINGGO_API_KEY` 与网络。

### 10.4 航班 `航班搜索失败，请稍后重试`

- **不是 Key 无效**：同一 Key 下酒店、国内航班通常正常。
- 国际线已支持 PEK→ICN 等机场码 fallback；若 API 仍返回空，规划中会标注「机票待查询」。
- 价格为 **1 成人参考价**，多人总价需在订票平台另行查询。

### 10.5 黄历 GBK / 脚本找不到

- 确认 `.agents/skills/lao-huangli/scripts/huangli_calc.py` 存在。
- 设置 `TRAVEL_AGENT_HUANGLI_SCRIPT` 指向该脚本或 skill 目录。
- Windows 终端乱码：`chcp 65001` 或设置 `PYTHONUTF8=1`。

### 10.6 规划里没有「出行择日建议」

- 需成功调用 `calendar_lookup`；仅当工具返回真实黄历数据时 LLM 才会输出该章节。
- 重启 `python main.py` 使代码变更生效。

### 10.7 RAG 无结果

确认已导入数据，且查询目的地与库内国家/城市一致（日韩泰优先）。

---

## 11. 测试

```powershell
pip install pytest
pytest tests/ -v
```

---

## 12. 首次运行命令（可复制）

```powershell
conda activate Alice
cd D:\TravelAgent-main\TravelAgent-main
pip install -r requirements_agent.txt
pip install modelscope

copy .env.example .env
# 编辑 .env，填入 DASHSCOPE_API_KEY、AMAP_WEBSERVICE_KEY、ROLLINGGO_API_KEY

modelscope skills add "@cikichen/lao-huangli" --local_dir ".agents\skills"
modelscope skills add "yorklu/rollinggo-flight-skill" --local_dir ".agents\skills"

python main.py
```

---

## 13. 相关文档

| 文件 | 说明 |
|------|------|
| `.env.example` | 环境变量模板 |
| `.agents/skills/lao-huangli/SKILL.md` | 黄历 Skill 官方说明 |
| `.agents/skills/rollinggo-flight-skill/SKILL.md` | 机票 CLI 官方说明 |
| `config/mcp_servers.json` | MCP 服务配置示例（与本地 SkillRunner 并行存在） |
| `LittleCrawler/README.md` | 爬虫子项目（数据采集，非运行时必需） |

---

## 14. 架构简图

```text
用户 Web 对话
    ↓
web/app.py（需求收集 + 选项问答）
    ↓
MultiAgentCoordinator
    ├─ Planner（决定 required_tools + 参数）
    ├─ Executor → SkillRunner（weather / poi / hotel / flight / calendar）
    ├─ RAG Retriever（攻略笔记）
    └─ LLM 生成 Markdown 行程
```

如需扩展新 Skill：在 `travel_agent/skills/registry.py` 注册工具名，在 `runner.py` 实现 `_handle_<tool_name>`，并在 Planner prompt / postprocess 中补充调用规则。
