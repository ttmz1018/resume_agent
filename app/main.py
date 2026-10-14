"""FastAPI 服务：对外的问答接口 + 聊天页面。

本地启动：
    python -m app.main
或：
    uvicorn app.main:app --host 0.0.0.0 --port 7860
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import config, ingest
from app.agent import ask
from app.db import session_scope
from app.models import Profile
from app.retrieval.vector_store import chunk_count
from app.schemas import ChatRequest, ChatResponse, HealthResponse, Source

# 首屏的建议问题，命中面试官最常问的几类。
# 换成自己的简历后，建议同步调整成贴合自身经历的问题。
SUGGESTED_QUESTIONS = [
    "他的毕业设计是什么？用了哪些技术？",
    "他做过哪些 LLM / Agent 相关的项目？",
    "他熟悉哪些技术栈？",
    "他的简历问答 Agent 是怎么设计的？",
    "他是哪一届毕业的？什么学校什么专业？",
    "怎么联系他？",
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    """启动时做两件事：校验密钥、确保索引已就绪。"""
    missing = config.missing_keys()
    if missing:
        raise RuntimeError(
            f"缺少必填环境变量：{', '.join(missing)}。请参考 .env.example 配置 .env 后重启。"
        )
    if ingest.ensure_index():
        print("✅ 首次启动：已自动构建简历索引")
    yield


app = FastAPI(
    title="简历问答 Agent",
    description="基于 RAG 的简历问答服务：结构化查询 + 语义检索 + Agent 编排",
    version="0.1.0",
    lifespan=lifespan,
)

# 本地开发放开跨域，方便用其他端口的前端直接调接口
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# 按 IP 的滑动窗口限流
#
# 这个服务是要挂在公开链接上的，不限流的话陌生访客可以把大模型额度刷爆，
# 所以这里是必要的，不是可选项。单进程内存实现，不引入 Redis 这类额外依赖；
# 如果以后要多实例部署，再换成 Redis 计数即可。
# ------------------------------------------------------------------
_hits: dict[str, deque[float]] = defaultdict(deque)


def _rate_limit(client_ip: str) -> None:
    now = time.time()
    window = _hits[client_ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= config.RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="提问太频繁了，请稍后再试。")
    window.append(now)


def _client_ip(request: Request) -> str:
    """取真实客户端 IP。部署在反向代理后面时，优先读 X-Forwarded-For。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ------------------------------------------------------------------
# 接口
# ------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse, tags=["系统"])
def health() -> HealthResponse:
    """健康检查 + 保活用接口。"""
    return HealthResponse(
        status="ok",
        llm_model=config.LLM_MODEL,
        embed_model=config.EMBED_MODEL,
        indexed=chunk_count() > 0,
        chunks=chunk_count(),
    )


@app.get("/api/profile", tags=["简历"])
def get_profile() -> dict:
    """页面首屏需要的候选人信息和建议问题。"""
    with session_scope() as session:
        profile = session.get(Profile, 1)
        if profile is None:
            raise HTTPException(status_code=503, detail="简历索引尚未构建，请先执行 python -m app.ingest")
        return {
            "name": profile.name,
            "title": profile.title,
            "summary": profile.summary,
            "location": profile.location,
            "years_experience": profile.years_experience,
            "suggestions": SUGGESTED_QUESTIONS,
        }


@app.post("/api/chat", response_model=ChatResponse, tags=["简历"])
def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    """简历问答主接口。

    注意这里故意用同步 def：agent.invoke 是阻塞调用，写成 async def 会卡住事件循环，
    同步 def 会被 FastAPI 放到线程池里执行。
    """
    _rate_limit(_client_ip(request))

    question = payload.message.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空。")

    try:
        answer, sources = ask(question, payload.session_id)
    except Exception as exc:  # 模型侧/网络侧异常，转成 502 让前端有明确提示
        raise HTTPException(status_code=502, detail=f"模型调用失败：{exc}") from exc

    return ChatResponse(
        answer=answer,
        session_id=payload.session_id,
        sources=[Source(**item) for item in sources],
    )


# ------------------------------------------------------------------
# 静态页面
# ------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(config.STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    # 直接传 app 对象而不是 "app.main:app" 字符串：避免 uvicorn 反复导入本模块
    # 导致 FastAPI 实例和 lifespan 被创建两次。
    # 端口走配置：Zeabur 注入 PORT(8080)，Hugging Face Spaces 需要 7860，
    # 其他平台通常也注入 PORT，代码不用改。
    uvicorn.run(app, host=config.HOST, port=config.PORT)
