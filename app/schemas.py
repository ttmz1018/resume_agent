"""接口的请求与响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app import config


class ChatRequest(BaseModel):
    """一次提问。session_id 用来关联多轮对话的上下文。"""

    message: str = Field(
        ...,
        min_length=1,
        max_length=config.MAX_QUESTION_CHARS,
        description="用户提问内容",
    )
    session_id: str = Field(
        default="default",
        max_length=64,
        description="会话标识，前端生成并复用，用于保存多轮上下文",
    )


class Source(BaseModel):
    """答案所依据的简历片段，让回答可追溯。"""

    kind: str = Field(description="来源类型：结构化数据 / 语义检索")
    title: str = Field(description="来源名称，例如某段项目经历")


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    sources: list[Source] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    llm_model: str
    embed_model: str
    indexed: bool
    chunks: int
