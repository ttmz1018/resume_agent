"""向量库（Chroma）与嵌入模型。

选 Chroma 而不是 Milvus 的原因：Chroma 是嵌入式向量库，数据直接落本地目录，
不需要额外跑一个服务进程。这个项目后续要部署到免费/低配环境，
少一个中间件就少一份运维成本和内存开销。
"""

from __future__ import annotations

from functools import lru_cache

from langchain.embeddings import init_embeddings
from langchain_chroma import Chroma

from app import config


@lru_cache(maxsize=1)
def get_embeddings():
    """嵌入模型：硅基流动上的 BGE-M3，走 OpenAI 兼容接口。

    ⚠️ check_embedding_ctx_length=False 是必须的，不是可选优化，别删。

    OpenAIEmbeddings 默认会先用 tiktoken 把文本切成 token 再解码拼回字符串发给接口，
    这一步预处理会把中文改坏，导致向量区分度严重下降、检索结果接近随机。
    实测同一组文本（查询 vs 正确切片 / 无关切片 / 闲聊）：

        默认 True ：0.627 / 0.703 / 0.627   ← 无关的反而比正确的更相似，完全失效
        设为 False：0.653 / 0.431 / 0.323   ← 正常的分层

    这个坑很隐蔽：接口不报错、向量维度正常、模长也归一化，只有检索结果悄悄地变差。
    """
    return init_embeddings(
        model=config.EMBED_MODEL,
        api_key=config.SILICONFLOW_API_KEY,
        base_url=config.SILICONFLOW_BASE_URL,
        check_embedding_ctx_length=False,
    )


@lru_cache(maxsize=1)
def get_vector_store() -> Chroma:
    """进程内单例的 Chroma 实例，数据持久化在 data/chroma/。"""
    config.ensure_dirs()
    return Chroma(
        collection_name=config.COLLECTION_NAME,
        embedding_function=get_embeddings(),
        persist_directory=str(config.CHROMA_DIR),
    )


def chunk_count() -> int:
    """当前集合里的切片数量，用于健康检查与"是否已建索引"的判断。"""
    try:
        return get_vector_store()._collection.count()
    except Exception:
        return 0
