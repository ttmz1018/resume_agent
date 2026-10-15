# 部署指南（香港轻量服务器）

目标：拿到一个 **`https://你的域名`** 的 HTTPS 链接，挂在简历上给招聘方点。

## 为什么选香港轻量服务器

先把选型结论放前面，省得你重复踩坑：

| 方案 | 结论 |
|---|---|
| ~~Hugging Face Spaces~~ | `huggingface.co` 国内被 DNS 污染，Spaces 网页 demo 打不开。**不能用作简历主链接** |
| ~~Zeabur 免费档~~ | 2025 年 3 月起所有区域都改为需 Dev Plan（$5/月），免费档不再提供计算资源 |
| ~~Render / Koyeb / Fly.io~~ | 或需绑卡、或已取消免费；且域名在国内访问不稳、还会休眠（冷启动 30-60 秒） |
| **香港轻量服务器** | ✅ 免备案、国内延迟 30-50ms、**常驻不休眠**、成本 ≈¥24-46/月 |

**核心判断**：免费的海外平台都有"冷启动 + 国内访问不稳"这两个毛病，而这恰恰是挂在简历上的链接最不能有的。招聘方点开转半天圈就会关掉。

---

## 一、前置准备

### 1. 买服务器

阿里云或腾讯云，**轻量应用服务器**，地域选**中国香港**。

- **配置**：2 核 2G 足够（实测应用只占 **180MB** 内存；选 2G 主要是为了在服务器上构建镜像时更稳）
- **系统镜像**：Ubuntu 22.04 或 Debian 12
- **⚠️ 阿里云选型注意**：要选「通用型 / CPU 优化型」，**不要选「国际型 BGP_NCO」**——那个线路大陆访问很慢。腾讯云香港轻量的去程 CMI 线路对大陆较友好
- **安全组 / 防火墙**：放行 `22`(SSH)、`80`、`443`。**不要放行 8080**
- **不需要 ICP 备案**（香港节点不在工信部备案管辖范围）。但购买要**实名认证**

### 2. 买域名并解析

任意注册商都行（阿里云、腾讯云、Namecheap…），`.top` / `.xyz` 一年几十块。

在 DNS 控制台加一条 **A 记录**，把域名（或子域）指向服务器公网 IP：

```
类型: A    主机记录: resume    记录值: <服务器公网IP>
```

解析生效通常几分钟。**生效后再启动 Caddy**，否则证书签不下来：

```bash
# 在你自己电脑上执行，能返回服务器 IP 就说明生效了
nslookup resume.你的域名.com
```

> 别用 `IP:端口` 当简历链接，很掉价。域名一年几十块，值得花。

---

## 二、服务器上装 Docker

SSH 登录服务器后执行（Docker 官方安装脚本）：

```bash
curl -fsSL https://get.docker.com | sh

# 验证
docker --version
docker compose version
```

**香港服务器能直连 Docker Hub 和 PyPI**，所以本地开发时用的镜像加速和 `--build-arg PIP_INDEX_URL`
在这里都不需要，用默认的就行。

---

## 三、部署

```bash
# 1. 拉代码
git clone https://github.com/ttmz1018/resume_agent.git
cd resume_agent

# 2. 配环境变量（只改 .env 一个文件，域名也在这里）
cp .env.production.example .env
nano .env
#    DEEPSEEK_API_KEY=<你的密钥>
#    SILICONFLOW_API_KEY=<你的密钥>
#    SITE_ADDRESS=resume.你的域名.com          ← Caddy 用它签 HTTPS 证书
#    CORS_ORIGINS=https://resume.你的域名.com

# 3. 启动（首次会构建镜像，几分钟）
docker compose up -d --build

# 4. 看启动日志，应出现「✅ 首次启动：已自动构建简历索引」
docker compose logs -f app
```

启动后 Caddy 会自动向 Let's Encrypt 申请证书，**几十秒内**就能用 HTTPS 访问了。

### 为什么域名配在 .env 而不是 Caddyfile 里

`Caddyfile` 是被 git 跟踪的文件。如果把域名写死在里面，你在服务器上改完之后，
**每次 `git pull` 都会冲突**——而更新简历是要经常 pull 的。

所以域名放在 `.env` 的 `SITE_ADDRESS` 里（`.env` 已被 `.gitignore` 排除），
`Caddyfile` 只写 `{$SITE_ADDRESS}` 引用它。好处：

- `git pull` 永远不冲突
- **换域名只改 `.env` 一个地方**，`docker compose up -d` 重启即可生效
- 还没有域名时可以用 `SITE_ADDRESS=:80` 先跑纯 HTTP（此时端口映射改为 `-p 80:8080` 直连应用，不走 Caddy）

如果 `.env` 里没设 `SITE_ADDRESS`，`docker compose up` 会**直接报错退出**并提示你设置，
不会出现"Caddy 起来了但签不到证书"这种难排查的情况。

---

## 四、验证

```bash
# 服务器上或本地都行
curl https://resume.你的域名.com/health
```

期望返回：

```json
{"status":"ok","llm_model":"deepseek-v4-flash","embed_model":"openai:Pro/BAAI/bge-m3","indexed":true,"chunks":13}
```

`indexed: true` 且 `chunks: 13` 说明简历索引已自动建好，可以开始对话。

**然后必须做这一步**：用**手机流量（4G/5G，不要连 WiFi）**打开链接，实际问一个问题。

这一步比电脑上测有用得多，因为它同时验证了：域名解析、HTTPS 证书、服务器带宽、以及**招聘方所在的网络能不能访问**。

---

## 五、日常维护

### 改了简历怎么办

索引不是打进镜像的，而是**容器启动时自动重建**（一次 embedding 调用，约 1 秒）。
所以流程是：改文件 → 推代码 → 服务器重建：

```bash
# 本地
#   改 resume/resume.yaml
git add . && git commit -m "update resume" && git push

# 服务器
cd resume_agent && git pull && docker compose up -d --build
```

这样能保证索引一定是最新的，不会出现"简历改了但 Agent 还在答旧内容"。

### 常用命令

```bash
docker compose ps                        # 服务状态
docker compose logs -f --tail=100 app    # 看应用日志
docker compose logs caddy | grep -i cert # 看证书申请/续期情况
docker compose restart app               # 重启应用
docker compose up -d --build             # 更新代码后重新部署
```

**证书**：Caddy 自动申请并自动续期，不需要任何操作。证书存放在 `caddy_data` 卷里——
**这个卷别删**，删了会重新申请，而 Let's Encrypt 有颁发频率限制。

---

## 六、成本

| 项目 | 费用 |
|---|---|
| 香港轻量服务器 2核2G | ≈ ¥24-46/月（新用户活动价更低） |
| 域名 | ≈ ¥30-70/年 |
| DeepSeek + 硅基流动 API | 按量，个人使用量级基本可忽略 |
| **合计** | **≈ ¥350-600/年** |

一年几百块换"面试官一定打得开"，我认为比省这笔钱值。

---

## 七、常见问题

| 现象 | 原因与排查 |
|---|---|
| 证书签不下来 / 一直 HTTP | ① 域名解析没生效 ② 安全组没放行 80 端口。`docker compose logs caddy` 会写明原因 |
| 502 Bad Gateway | app 容器没起来。`docker compose logs app` 看报错；多半是 `.env` 里密钥没填对 |
| 启动报缺少环境变量 | `.env` 里 `DEEPSEEK_API_KEY` / `SILICONFLOW_API_KEY` 没填。服务启动时会明确报缺哪个 |
| 打开很慢 | 先看服务器带宽是否被占满；页面首屏只有 11KB，正常应该秒开 |
| 担心额度被刷 | `.env` 里调小 `RATE_LIMIT_PER_MINUTE`；`.env.example` 已默认开启按 IP 限流 |
| 构建很慢 | 香港服务器直连 Docker Hub 和 PyPI，正常几分钟。慢通常是服务器配置过低 |

### 安全建议

- 安全组**只开 22 / 80 / 443**，应用端口 8080 只在 Docker 内部网络暴露（compose 里已这样配好）
- `CORS_ORIGINS` 收紧成自己的域名，别用 `*`
- `.env` 不要提交到 git（推送前跑 `python -m scripts.check_secrets`）
- 可选加固：SSH 改端口 / 禁用密码登录改密钥、开启 BBR 加速

---

## 附：其他平台的适配方式

代码已做到"换平台只改环境变量，不改代码"：

| 平台 | 需要改动 |
|---|---|
| **香港/大陆轻量服务器** | 无（当前配置就是这个） |
| Hugging Face Spaces | 环境变量加 `PORT=7860`，Space 端口设 `7860` |
| Zeabur（Dev Plan） | 删掉 compose，让它直接用 Dockerfile；不要配 `PORT` / `HOST` |
| 国内云函数 | 需改造：`data/` 无持久盘，Chroma 要换成轻量向量检索，FastAPI 改成函数入口 |
