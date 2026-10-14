# 简历问答 Agent

一个可以对话式回答「关于我简历」问题的 Agent。把生成的公网链接挂在简历上，
招聘方不用翻 PDF，直接提问就能了解候选人的经历、项目和技术栈。

## 技术架构

```
resume/resume.yaml  ──┬──>  SQLite (data/resume.db)   结构化表：profile/education/experience/project/skill/award
（单一数据源）         └──>  Chroma (data/chroma/)     向量索引：按实体切片后的语义块
                                        │
                        ┌───────────────┴───────────────┐
                        │   6 个受控检索工具              │
                        │   5 个结构化查询 + 1 个语义检索   │
                        └───────────────┬───────────────┘
                                        │
                            LangChain create_agent
                        （DeepSeek deepseek-v4-flash）
                                        │
                            FastAPI  /api/chat 接口
                                        │
                            移动端适配的聊天页面（static/）
```

**为什么做双索引**：HR 的提问分两类。一类是精确/聚合型问题（"工作几年"、"在哪些公司待过"、
"什么学历"），这类问题交给向量库会靠概率去猜，容易答错；另一类是语义型问题
（"他在推荐系统方向做过什么"），这类用关系型数据库很难匹配。所以按问题类型分而治之。

**为什么切片按实体而不是按长度**：简历本身高度结构化，按固定长度切分会把一段经历拦腰截断，
召回片段语义不完整。这里一段经历/一个项目/一类技能各成一个 chunk，并在 chunk 里带上姓名和职位，
避免指代不明导致的误召回。

## 目录结构

```
resume_agent/
├─ app/
│  ├─ config.py              集中配置，全部走环境变量
│  ├─ models.py              SQLAlchemy ORM 模型
│  ├─ db.py                  SQLite 引擎与会话
│  ├─ schemas.py             接口出入参模型
│  ├─ ingest.py              resume.yaml → SQLite + Chroma（双索引灌库）
│  ├─ agent.py               模型、工具、System Prompt、会话记忆
│  ├─ main.py                FastAPI 服务（/health、/api/profile、/api/chat）
│  └─ retrieval/
│     ├─ vector_store.py     Chroma 与 BGE-M3 嵌入
│     └─ tools.py            6 个检索工具
├─ resume/resume.yaml        简历数据源（改这里就够了）
├─ static/index.html         聊天页面
├─ requirements.txt
└─ .env.example
```

## 快速开始

```bash
# 1. 用项目已有的 conda 环境
conda activate langchain1.2

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置密钥
cp .env.example .env      # 然后填入 DEEPSEEK_API_KEY 和 SILICONFLOW_API_KEY

# 4. 把简历灌入两套索引
python -m app.ingest

# 5. 启动服务
python -m app.main
```

打开 http://127.0.0.1:7860 就能聊了。接口文档在 http://127.0.0.1:7860/docs。

## 换成自己的简历

只改 `resume/resume.yaml` 一个文件，然后重新灌库：

```bash
python -m app.ingest
```

注意：公开链接上的简历建议脱敏——手机号、身份证、住址、现公司的敏感数据不要放进来。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查，返回模型名与已建索引的切片数，也用于[保活](#部署提醒) |
| GET | `/api/profile` | 首屏需要的候选人信息与建议问题 |
| POST | `/api/chat` | 问答主接口，Body：`{"message": "...", "session_id": "..."}` |

```bash
curl -X POST http://127.0.0.1:7860/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "他做过哪些 RAG 相关的项目？", "session_id": "test-1"}'
```

返回里除了 `answer`，还有 `sources`（答案依据的简历条目），页面会渲染成标签，让回答可追溯。

## 工程上做的几件事

- **回答边界**：System Prompt 严格限定只答简历相关问题，无关问题固定话术拒答，
  并防"忽略以上指令"这类越狱诱导，避免公开链接被当成免费通用大模型刷爆额度。
- **限流**：按 IP 的滑动窗口限流 + 单次提问字数上限，单进程内存实现，不引入额外中间件。
- **不暴露 SQL**：给模型的是 6 个受控查询工具，而不是"执行任意 SQL"的能力，
  既避免把数据库暴露给陌生人，也避免 LLM 写错字段后反复重试。
- **可追溯**：工具输出自带来源标记，服务端提取后随答案返回。
- **配置即部署**：端口、密钥、模型名全部走环境变量，代码里同时兼容固定端口（HF Spaces 的 7860）
  和注入端口（`$PORT`）两种平台，迁移时不用改代码。

## 踩过的坑

这几个问题都**不报错**，但结果会悄悄变差，排查起来比较费劲，记下来备查。

### 1. 嵌入向量被 LangChain 的默认参数改坏

`OpenAIEmbeddings` 默认 `check_embedding_ctx_length=True`，会先用 tiktoken 把文本切成 token、
再解码拼回字符串发给接口。这个预处理会把中文改得面目全非，导致向量区分度严重下降：

| `check_embedding_ctx_length` | cos(查询, 正确切片) | cos(查询, 无关切片) | 结果 |
|---|---|---|---|
| `True`（默认） | 0.627 | **0.703** | 无关的反而排在前面，检索接近随机 |
| `False` | **0.653** | 0.431 | 正常分层 |

接口不报错、向量维度正常、模长也归一化，只有检索结果变差。现在固定在
`app/retrieval/vector_store.py` 里关掉这个参数，代码注释里写了实测数据，别删。

### 2. `.env` 覆盖掉平台注入的环境变量

`load_dotenv(override=True)` 会让本地 `.env` 里的值覆盖云平台注入的环境变量，
部署后会出现"控制台明明改了密钥/端口，服务还按旧值跑"的怪现象。
现在用 `override=False`，真实环境变量的优先级更高。

### 3. iOS 输入框小于 16px 会触发页面自动放大

移动端聊天页的输入框字号必须 ≥16px，否则 iOS Safari 聚焦时会把整个页面放大，
体验很差。`static/index.html` 里已固定为 16px。

## 部署

完整的部署步骤见 **[DEPLOY.md](DEPLOY.md)**（Zeabur 免费档，含环境变量清单与本地验证命令）。

下面是要点速查。

### 本地先验证镜像

```bash
docker build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple -t resume-agent:local .
docker run -d --name resume-test -p 7860:7860 --env-file .env resume-agent:local
docker logs resume-test          # 应出现「✅ 首次启动：已自动构建简历索引」
curl http://127.0.0.1:7860/health
docker rm -f resume-test         # 验证完清理
```

注意端口要和 `.env` 里的 `PORT` 对齐（本地 `.env` 是 7860）。
密钥用 `--env-file .env` 传入，不要写成 `-e KEY=sk-xxx`，否则会留在命令历史里。

国内网络下如拉取基础镜像超时，需要给 Docker 配镜像加速（改 `~/.docker/daemon.json`
的 `registry-mirrors` 后重启 Docker Desktop），或加 `--build-arg PIP_INDEX_URL=...` 加速依赖安装。

### 要点提醒

- **端口**：Hugging Face Spaces 的 Docker 应用必须监听 `7860`；Zeabur 注入的 `PORT` 默认是 `8080`。
  代码里两种都兼容，换平台只改环境变量，不用动代码。
- **索引**：容器环境磁盘是临时的，`data/` 每次重启都会丢，所以索引没有打进镜像，
  而是**启动时自动重建**（`app/ingest.py` 的 `ensure_index()`，一次 embedding 调用约 1 秒）。
  好处是改完 `resume.yaml` 重新部署后索引一定是新的。
- **保活**：免费档在长时间无访问后会休眠，冷启动需要几十秒。
  可以用免费监控服务定时 ping `/health`，但这属于灰色操作，别指望长期稳定。
- **国内访问**：`huggingface.co` 在国内基本无法直连，Spaces 链接不适合作为简历上的主链接。

## 后续可以继续做的

- SSE 流式输出，降低"等待感"
- 小评测集（20 条问答对）跑 hit rate / 准确率，量化检索效果
- 会话持久化（换成 SQLite/Postgres checkpointer），服务重启后上下文不丢
- 接入 LangSmith 追踪（`.env.example` 里已留好配置项）
