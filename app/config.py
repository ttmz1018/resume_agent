"""集中配置：路径、模型、服务参数。

所有可变项都走环境变量，目的是让本地开发和线上部署复用同一份代码，
部署时只需要在平台的控制台里配好环境变量，不用改代码。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（app/ 的上一级）
BASE_DIR = Path(__file__).resolve().parent.parent

# 本地开发从 .env 读取。
# override=False 是关键：已存在的真实环境变量优先级高于 .env，
# 否则部署到云平台后，仓库里如果带了 .env，会把平台控制台配置的密钥/端口覆盖掉。
load_dotenv(BASE_DIR / ".env", override=False)

# ---------- 目录与文件 ----------
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
RESUME_FILE = Path(os.getenv("RESUME_FILE") or BASE_DIR / "resume" / "resume.yaml")
SQLITE_FILE = DATA_DIR / "resume.db"
CHROMA_DIR = DATA_DIR / "chroma"

# ---------- 大模型：DeepSeek ----------
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# ---------- 嵌入模型：硅基流动 BGE-M3 ----------
EMBED_MODEL = os.getenv("EMBED_MODEL", "openai:Pro/BAAI/bge-m3")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))  # BGE-M3 输出维度固定 1024
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")

# ---------- 服务 ----------
# 注意：Hugging Face Spaces 的 Docker 应用必须监听 7860，其他平台基本都注入 PORT，
# 所以这里两种都兼容，迁移平台时不用改代码。
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "7860"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))  # 单 IP 每分钟提问上限
MAX_QUESTION_CHARS = int(os.getenv("MAX_QUESTION_CHARS", "500"))       # 单次提问字数上限

# ---------- 检索 ----------
RETRIEVE_TOP_K = int(os.getenv("RETRIEVE_TOP_K", "4"))
COLLECTION_NAME = "resume_chunks"


def ensure_dirs() -> None:
    """确保数据目录存在（首次运行时 data/ 可能还不存在）。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def missing_keys() -> list[str]:
    """返回缺失的必填密钥名，空列表表示配置完整。"""
    missing = []
    if not DEEPSEEK_API_KEY:
        missing.append("DEEPSEEK_API_KEY")
    if not SILICONFLOW_API_KEY:
        missing.append("SILICONFLOW_API_KEY")
    return missing
