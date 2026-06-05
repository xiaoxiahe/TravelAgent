# AgentLLM-copy 使用文档

`AgentLLM-copy` 是一个面向旅游场景的多智能体旅行规划项目，结合了对话式需求收集、RAG 检索、本地/第三方 Skill 调用与 Web 前端界面，可以根据用户输入自动生成更完整的旅行建议。

本文档覆盖以下内容：

- Conda 环境构建
- 依赖安装
- 环境变量配置
- 项目启动方式
- RAG 数据导入与检索测试
- Skill 工具测试
- 基础测试与常见问题

## 1. 项目简介

项目当前包含几类核心能力：

- **对话式旅游规划**：通过 Web 页面逐步收集出发地、目的地、天数、预算、交通偏好等信息。
- **多智能体工作流**：Planner 负责决定优先调用哪些工具，Executor 负责实际执行工具并汇总结果。
- **RAG 检索**：使用 Chroma 本地向量库保存旅游相关内容，支持检索景点/餐饮等资料。
- **Skill 能力接入**：目前已接入天气、POI、酒店、航班、黄历等能力。
- **Flask Web 服务**：启动后可在浏览器中直接交互测试。

## 2. 目录说明

建议主要关注以下目录：

```text
AgentLLM-copy/
├─ main.py                         # 项目入口，启动 Flask 服务
├─ requirements_agent.txt          # Python 依赖
├─ config/
│  └─ mcp_servers.json             # MCP / 工具配置示例
├─ scripts/
│  └─ test_rag.py                  # RAG 检索测试脚本
├─ travel_agent/
│  ├─ agent/                       # 单 Agent 对话流程
│  ├─ multi_agent/                 # 多智能体 Planner / Executor / Coordinator
│  ├─ rag/                         # 向量库、检索、导入脚本
│  ├─ skills/                      # Skill 注册与执行层
│  ├─ models/                      # 用户画像与行程数据模型
│  └─ services/                    # 数据管道与爬虫服务
├─ web/                            # Flask 接口与前端页面
├─ tests/                          # 基础测试
├─ chroma_db/                      # 本地向量数据库目录（运行后生成）
└─ .agents/skills/                 # 本地 skill 资源（如黄历）
```

## 3. 环境准备

### 3.1 基础要求

建议准备以下运行环境：

- Python 3.10 或 3.11
- Conda 或 Miniconda
- Node.js 18+ 与 npm / npx
- Windows PowerShell（本文命令示例以 PowerShell 为主）

其中：

- Python 用于运行主项目、RAG、测试脚本。
- Node.js 主要用于执行酒店/航班相关 CLI 能力。

### 3.2 使用 Conda 创建环境

在项目根目录外或任意目录执行：

```powershell
conda create -n agentllm-travel python=3.11 -y
conda activate agentllm-travel
```

如果你的机器上部分依赖对 3.11 兼容性不稳定，也可以退回 3.10：

```powershell
conda create -n agentllm-travel python=3.10 -y
conda activate agentllm-travel
```

### 3.3 进入项目目录

```powershell
cd "d:\大四上\AgentLLM\AgentLLM-copy"
```

## 4. 依赖安装

### 4.1 安装 Python 依赖

```powershell
pip install -r requirements_agent.txt
```

如果你希望先升级安装工具，可以执行：

```powershell
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements_agent.txt
```

### 4.2 检查 Node.js / npx

酒店与航班查询能力会调用 `npx rollinggo@latest`，因此建议确认本机可用：

```powershell
node -v
npm -v
npx -v
```

如果这些命令不可用，请先安装 Node.js LTS 版本。

## 5. 环境变量配置

项目启动时会优先读取以下位置的 `.env`：

- `AgentLLM-copy/.env`
- 上一级目录的 `.env`

建议直接在 `AgentLLM-copy` 根目录新建或维护 `.env` 文件。

### 5.1 最小配置

至少建议配置以下变量：

```env
DASHSCOPE_API_KEY=你的通义千问Key
AMAP_WEBSERVICE_KEY=你的高德WebServiceKey
ROLLINGGO_API_KEY=你的RollingGoKey
```

### 5.2 可选配置

```env
PORT=5000
FLASK_DEBUG=true
FLASK_RELOAD=false
SECRET_KEY=任意随机字符串
TRAVEL_AGENT_HUANGLI_SCRIPT=黄历脚本绝对路径
```

说明：

- `DASHSCOPE_API_KEY`：用于 LLM / 向量嵌入。
- `AMAP_WEBSERVICE_KEY`：用于天气查询与 POI 搜索。
- `ROLLINGGO_API_KEY`：用于酒店与航班查询。
- `TRAVEL_AGENT_HUANGLI_SCRIPT`：如黄历脚本不在默认位置，可显式指定。
- `PORT`：Web 服务端口，默认 `5000`。
- `FLASK_DEBUG`：是否开启 Flask 调试模式。
- `FLASK_RELOAD`：是否开启自动重载。

### 5.3 PowerShell 临时设置方式

如果你不想写入 `.env`，也可以在当前终端临时设置：

```powershell
$env:DASHSCOPE_API_KEY="你的通义千问Key"
$env:AMAP_WEBSERVICE_KEY="你的高德WebServiceKey"
$env:ROLLINGGO_API_KEY="你的RollingGoKey"
```

如果黄历脚本路径需要手动指定：

```powershell
$env:TRAVEL_AGENT_HUANGLI_SCRIPT="D:\绝对路径\huangli"
```

## 6. 运行项目

### 6.1 启动 Web 服务

在 `AgentLLM-copy` 目录下执行：

```powershell
python main.py
```

正常启动后，终端会输出服务信息，并默认监听：

```text
http://127.0.0.1:5000
```
ps:目前向量数据库只导入了韩国、日本、泰国的数据，最好用这三个
浏览器打开该地址即可使用页面版旅行规划助手。

### 6.2 交互接口说明

Web 服务当前主要包含以下接口：

- `/`：前端页面
- `/api/chat`：对话输入
- `/api/select`：选项式补充输入
- `/api/sessions`：会话列表与会话管理

一般测试时直接打开首页即可，不需要手工调用接口。

### 6.3 推荐测试输入

可以直接输入类似内容验证完整规划链路：

```text
我想去苏州玩3天，6月20日出发，预算4000，想看园林
```

```text
我想从上海去广州玩4天，2026-06-20出发，预算6000，坐飞机
```

这两类输入分别适合验证：

- 基础旅游规划
- 日期识别
- 航班 Skill 自动调用
- 天气 / POI / 酒店补充查询

## 7. RAG 数据导入

项目中的 RAG 数据不会在启动时自动导入，需要手动执行导入。

### 7.1 导入前准备

确认：

- 已安装 Python 依赖
- 已配置 `DASHSCOPE_API_KEY`
- 待导入 JSON 文件存在

例如先进入项目目录：

```powershell
cd "d:\大四上\AgentLLM\AgentLLM-copy"
```

### 7.2 导入餐饮/笔记数据到 Chroma

如果你使用现有数据文件，例如 `restaurant_contents_319.json`，可执行：

```powershell
python -m travel_agent.rag.ingest_data --json .\restaurant_contents_319.json --dir .\chroma_db --collection restaurant
```

如果你沿用旧命名，也可以导入到 `travel_knowledge`：

```powershell
python -m travel_agent.rag.ingest_data --json .\restaurant_contents_319.json --dir .\chroma_db --collection travel_knowledge
```

说明：

- `--json`：待导入的数据文件。
- `--dir`：本地 Chroma 持久化目录。
- `--collection`：向量集合名。

### 7.3 导入后快速搜索测试

你也可以直接使用导入脚本附带的查询模式：

```powershell
python -m travel_agent.rag.ingest_data --dir .\chroma_db --collection restaurant --query "日本美食" --top-k 5
```

或者测试旧 collection：

```powershell
python -m travel_agent.rag.ingest_data --dir .\chroma_db --collection travel_knowledge --query "北京好吃的餐厅" --top-k 5
```

## 8. RAG 检索测试

项目已经提供了专门的测试脚本 `scripts/test_rag.py`。

### 8.1 基础检索

```powershell
python .\scripts\test_rag.py "日本"
```

### 8.2 指定 collection

```powershell
python .\scripts\test_rag.py "日本美食" --collection restaurant
```

### 8.3 指定类型过滤

```powershell
python .\scripts\test_rag.py "日本景点" --filter-type attraction
```

### 8.4 指定返回条数

```powershell
python .\scripts\test_rag.py "苏州园林" --collection travel --top-k 8
```

### 8.5 结果说明

脚本会打印：

- 当前 collection 名称
- 检索 query
- 过滤条件
- collection 中文档数量
- 每条结果的 score、source_type、metadata 与内容摘要

如果返回 `results=0`，通常说明：

- collection 为空
- 查询词与现有数据不匹配
- collection 名写错
- 向量库目录不正确

## 9. 清理或重建向量库

### 9.1 清空某个 collection

清空 `restaurant`：

```powershell
python -c "from travel_agent.rag.vectorstore import ChromaVectorStore; print(ChromaVectorStore(collection_name='restaurant').clear())"
```

清空 `travel_knowledge`：

```powershell
python -c "from travel_agent.rag.vectorstore import ChromaVectorStore; print(ChromaVectorStore(collection_name='travel_knowledge').clear())"
```

### 9.2 直接删除本地向量库目录

```powershell
Remove-Item -Recurse -Force .\chroma_db
```

删除后再次导入即可完成重建。

## 10. Skill 工具测试

项目中的 Skill 调用由 `travel_agent.skills.SkillRunner` 统一管理。

当前主要工具包括：

- `weather_lookup`：天气查询
- `poi_search`：POI / 景点查询
- `hotel_search`：酒店查询
- `calendar_lookup`：黄历查询
- `flight_search`：航班查询

### 10.1 测试前检查

先确保对应依赖已配置：

- 天气 / POI：需要 `AMAP_WEBSERVICE_KEY`
- 酒店 / 航班：需要 `ROLLINGGO_API_KEY`
- 黄历：需要本地黄历脚本路径有效

### 10.2 测试黄历 Skill

```powershell
python -c "from travel_agent.skills import SkillRunner; r=SkillRunner().execute_tool('calendar_lookup', {'date':'2026-06-20'}); print(r.success); print(r.to_summary())"
```

### 10.3 测试天气 Skill

```powershell
python -c "from travel_agent.skills import SkillRunner; r=SkillRunner().execute_tool('weather_lookup', {'city':'苏州'}); print(r.success); print(r.to_summary())"
```

### 10.4 测试 POI Skill

```powershell
python -c "from travel_agent.skills import SkillRunner; r=SkillRunner().execute_tool('poi_search', {'city':'苏州','keyword':'拙政园'}); print(r.success); print(r.to_summary())"
```

### 10.5 测试酒店 Skill

```powershell
python -c "from travel_agent.skills import SkillRunner; r=SkillRunner().execute_tool('hotel_search', {'city':'苏州','destination':'苏州','keyword':'苏州 园林 酒店','travel_date':'2026-06-20'}); print(r.success); print(r.to_summary())"
```

### 10.6 测试航班 Skill

```powershell
python -c "from travel_agent.skills import SkillRunner; r=SkillRunner().execute_tool('flight_search', {'origin':'上海','destination':'广州','travel_date':'2026-06-20'}); print(r.success); print(r.to_summary())"
```

### 10.7 验证流程中的自动调用

当前多智能体流程会按用户信息自动决定是否调用工具：

- 默认优先考虑 `poi_search`、`weather_lookup`、`hotel_search`
- 提供了明确出发日期时，会额外考虑 `calendar_lookup`
- 提供了出发地 + 日期 + 飞机/航班意图时，会额外考虑 `flight_search`

因此你可以直接启动服务后，在页面中输入：

```text
我想从上海去广州玩4天，2026-06-20出发，预算6000，坐飞机
```

然后观察终端输出中的 Skill 调用日志。

## 11. 运行基础测试

项目包含一组基础测试，可用于快速验证核心模型与部分逻辑。

### 11.1 安装 pytest（如未自动装入）

如果你的环境中缺少 `pytest`，先安装：

```powershell
pip install pytest
```

### 11.2 执行测试

```powershell
pytest tests/
```

如果你只想跑当前这个测试文件，也可以执行：

```powershell
pytest tests/__init__.py -v
```

## 12. 常见问题

### 12.1 启动时报 `DASHSCOPE_API_KEY` 未配置

原因：

- `.env` 未被读取
- 当前终端没有设置环境变量
- key 名拼写错误

建议排查：

```powershell
python -c "import os; print(bool(os.getenv('DASHSCOPE_API_KEY')))"
```

### 12.2 天气 / POI 调用失败

通常是 `AMAP_WEBSERVICE_KEY` 缺失或不可用。

排查方式：

```powershell
python -c "import os; print(os.getenv('AMAP_WEBSERVICE_KEY'))"
```

### 12.3 酒店 / 航班调用失败

通常与以下情况有关：

- `ROLLINGGO_API_KEY` 未设置
- 本机没有 `node` / `npx`
- 网络请求超时

建议先检查：

```powershell
node -v
npx -v
python -c "import os; print(bool(os.getenv('ROLLINGGO_API_KEY')))"
```

### 12.4 黄历 Skill 报脚本不存在

说明默认黄历脚本路径未命中，此时需要手动指定：

```powershell
$env:TRAVEL_AGENT_HUANGLI_SCRIPT="D:\你的实际路径\huangli"
```

### 12.5 RAG 检索结果为空

优先确认以下几项：

- 数据是否已经导入成功
- `collection` 名称是否匹配
- `chroma_db` 目录是否正确
- `DASHSCOPE_API_KEY` 是否可用于嵌入

## 13. 推荐调试顺序

如果你是第一次在新机器上跑这个项目，推荐按下面顺序操作：

1. 创建 Conda 环境并激活
2. 安装 `requirements_agent.txt`
3. 安装 / 检查 Node.js
4. 配置 `.env`
5. 运行 `python main.py`
6. 打开页面验证基础对话是否正常
7. 导入 RAG 数据
8. 用 `scripts/test_rag.py` 测试检索
9. 分别测试天气、POI、黄历、酒店、航班 Skill
10. 最后做一次完整的页面链路联调

## 14. 一套可直接复制的首次运行命令

下面是一套从零开始的 PowerShell 示例：

```powershell
conda create -n agentllm-travel python=3.11 -y
conda activate agentllm-travel
cd "d:\大四上\AgentLLM\AgentLLM-copy"
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements_agent.txt

$env:DASHSCOPE_API_KEY="你的通义千问Key"
$env:AMAP_WEBSERVICE_KEY="你的高德WebServiceKey"
$env:ROLLINGGO_API_KEY="你的RollingGoKey"

python main.py
```

如果你还要测试 RAG：

```powershell
python -m travel_agent.rag.ingest_data --json .\restaurant_contents_319.json --dir .\chroma_db --collection restaurant
python .\scripts\test_rag.py "日本美食" --collection restaurant
```

如果你还要测试 Skill：

```powershell
python -c "from travel_agent.skills import SkillRunner; r=SkillRunner().execute_tool('weather_lookup', {'city':'苏州'}); print(r.success); print(r.to_summary())"
python -c "from travel_agent.skills import SkillRunner; r=SkillRunner().execute_tool('poi_search', {'city':'苏州','keyword':'拙政园'}); print(r.success); print(r.to_summary())"
python -c "from travel_agent.skills import SkillRunner; r=SkillRunner().execute_tool('flight_search', {'origin':'上海','destination':'广州','travel_date':'2026-06-20'}); print(r.success); print(r.to_summary())"
```

---

如果后面你还想要，我也可以继续把这份文档再细化成：

- 面向答辩展示版 README
- 面向开发者协作版 README
- 面向部署版 README
