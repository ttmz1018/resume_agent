# 部署指南（Zeabur）

目标：拿到一个 **`https://xxx.zeabur.app` 的 HTTPS 链接**，挂在简历上给招聘方点。

Zeabur 会自动检测根目录的 `Dockerfile` 并构建，所以部署本身不需要写配置文件，
真正需要小心的是**环境变量**和**端口**这两件事。

---

## 一、前置：把代码推到 GitHub

Zeabur 支持从 GitHub 仓库部署（也支持 CLI，但网页端更直观）。当前这个项目还不是 Git 仓库：

```bash
cd D:/langchain1.2_tutorial/resume_agent

git init
git add .
git commit -m "feat: 简历问答 Agent（RAG 双索引 + Agent 编排）"

# 在 GitHub 上新建一个空仓库（不要勾选 README/.gitignore），然后：
git remote add origin https://github.com/ttmz1018/<仓库名>.git
git branch -M main
git push -u origin main
```

**提交前确认 `.env` 没有被提交**（`.gitignore` 里已经排除了）：

```bash
python -m scripts.check_secrets
```

这个脚本会做两件事：确认 `.env` 未被 git 跟踪，以及扫描所有待提交文件里有没有混入真实密钥。
最后打印 `✅ 体检通过，可以安全 push` 就放心推。

> 不要用 `git status | grep ".env"` 来判断——那是子串匹配，会把本该提交的
> `.env.example` 也匹配上，白白吓自己一跳。

> `.env` 里有你的 DeepSeek 和硅基流动密钥。一旦推到公开仓库就等于泄露，
> 只能去两个平台重新生成密钥。**推送前务必确认这一条。**

---

## 二、在 Zeabur 上创建服务

1. 用 GitHub 账号登录 [zeabur.com](https://zeabur.com)
2. **Create Project** → 选一个免费区域（Free 计划只能选免费区域）
3. **Deploy New Service** → **GitHub** → 选中刚推的仓库
4. Zeabur 检测到 `Dockerfile` 后会自动走 Docker 构建，等构建完成

## 三、配环境变量（关键步骤）

在服务的 **Variables / 环境变量** 页面添加下面这些。

**必填**（缺了服务会启动失败并明确报错提示缺哪个）：

| 变量 | 值 |
|---|---|
| `DEEPSEEK_API_KEY` | 你的 DeepSeek 密钥 |
| `SILICONFLOW_API_KEY` | 你的硅基流动密钥 |

**建议也配上**（代码里有默认值，但显式写出来更可控）：

| 变量 | 值 |
|---|---|
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` |
| `LLM_MODEL` | `deepseek-v4-flash` |
| `LLM_PROVIDER` | `deepseek` |
| `SILICONFLOW_BASE_URL` | `https://api.siliconflow.cn/v1` |
| `EMBED_MODEL` | `openai:Pro/BAAI/bge-m3` |
| `EMBED_DIM` | `1024` |
| `RATE_LIMIT_PER_MINUTE` | `20` |
| `MAX_QUESTION_CHARS` | `500` |

**⚠️ 不要配 `PORT` 和 `HOST`**：Zeabur 会自动注入 `PORT`（Git 部署默认 `8080`），
而 `HOST` 在镜像里已经固定为 `0.0.0.0`。手动覆盖 PORT 反而会导致平台访问不到服务。

## 四、确认端口

在服务的 **Networking / 端口** 设置里：

- 端口填 **8080**，类型选 **HTTP**
- 这样 Zeabur 会自动分配 `xxx.zeabur.app` 域名并签发 TLS 证书

访问 `https://<你的域名>/health` 应该返回：

```json
{"status":"ok","llm_model":"deepseek-v4-flash","embed_model":"openai:Pro/BAAI/bge-m3","indexed":true,"chunks":13}
```

`indexed: true` 且 `chunks: 13` 说明索引已经自动建好了。

---

## 五、索引是怎么来的（重要）

容器里**没有持久盘**，`data/` 每次重启都会清空。所以索引不是打进镜像的，
而是**服务启动时自动重建**的（`app/ingest.py` 里的 `ensure_index()`）：

- 首次启动会自动完成灌库，只需要 1 次 embedding 调用，大约 1 秒
- 代价是每次冷启动多花一点点时间，换来的是**改了 `resume/resume.yaml` 重新部署后索引一定是新的**
  （如果把索引打进镜像，很容易出现"简历改了但 Agent 还在回答旧内容"）

也就是说：**改完简历只需要重新 push，不需要做别的**。

---

## 六、免费档的两个已知限制

1. **会休眠**：免费档服务长时间无访问会自动休眠，下次请求要冷启动，第一次打开可能转几秒到几十秒。
   招聘方点开时体验不好——这是免费档绕不开的代价，先用着，真觉得影响观感再升 Dev（$5/月）或换香港轻量服务器。
2. **日志只保留 48 小时**，排障要趁早看。

> 关于"定时访问保活"：技术上可以（定时 ping `/health`），但免费档本身资源有限，
> 且这属于灰色操作。短期试水可以用，别指望它长期稳定。

---

## 七、本地先验证镜像再推（推荐）

推之前先在本地跑一遍，避免在平台上来回试错。
**Git Bash / PowerShell / CMD 都能执行 docker 命令**，下面写的是 bash 语法，Git Bash 里可直接粘贴。

```bash
cd D:/langchain1.2_tutorial/resume_agent

# 1) 构建镜像（依赖层会被缓存，第一次约几十分钟，之后改代码重建只要几秒）
docker build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple -t resume-agent:local .

# 2) 启动容器。密钥直接复用项目里已有的 .env，不用手打，也就不会留在命令历史里
docker run -d --name resume-test -p 7860:7860 --env-file .env resume-agent:local

# 3) 看启动日志，应出现「✅ 首次启动：已自动构建简历索引」
docker logs resume-test

# 4) 验证
curl http://127.0.0.1:7860/health
# 期望：{"status":"ok",...,"indexed":true,"chunks":13}
# 浏览器打开 http://127.0.0.1:7860 可以直接对话

# 5) 验证完清理
docker rm -f resume-test
```

**两个容易踩的点：**

- **端口要和 `.env` 对齐**：`.env` 里是 `PORT=7860`，所以映射写 `-p 7860:7860`。
  写成 `-p 8080:8080` 的话，容器内监听的是 7860，映射对不上，`curl` 会连不上。
  （Zeabur 上不用管——它自己注入 `PORT=8080` 并接管端口映射。）
- **别把密钥写进命令行**：`-e DEEPSEEK_API_KEY=sk-xxx` 会留在 shell 历史里，
  用 `--env-file .env` 更安全，而且不用复制粘贴密钥。

> Git Bash 里执行 docker 一般没问题；只有带 Linux 绝对路径的参数（例如
> `docker exec xxx /bin/sh`）可能被 MSYS 路径转换搞坏，那种情况在前面加
> `MSYS_NO_PATHCONV=1`。上面这些命令不涉及。
>
> 补充：这一步其实**已经在你的机器上跑过了**——镜像 `resume-agent:local` 已构建，
> 容器内问答、拒答、多轮、健康检查全部验证通过。只有当你改了代码、
> 想在推之前再确认一次时才需要重跑。

---

## 八、换平台的差异（备查）

代码已经做到"换平台只改环境变量，不改代码"，各平台差异只在这几处：

| 平台 | 需要改动 |
|---|---|
| **Zeabur** | 无（当前配置就是按它配的） |
| **Hugging Face Spaces** | 环境变量加 `PORT=7860`，Space 设置里端口填 `7860` |
| **香港/大陆轻量服务器** | `docker run -p 80:8080` + 前面挂 Caddy/Nginx 自动签 HTTPS |
| **国内云函数** | 需改造：`data/` 没有持久盘，Chroma 要换成轻量向量检索（当前只有 13 个切片，numpy 手写余弦足够且冷启动快得多），FastAPI 改成函数入口 |
