"""SQLite 引擎、会话与建表。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import config
from app.models import Base

config.ensure_dirs()

# check_same_thread=False：FastAPI 的请求可能在线程池里跑，SQLite 默认禁止跨线程复用连接
engine = create_engine(
    f"sqlite:///{config.SQLITE_FILE}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """按 ORM 模型建表（已存在则跳过）。"""
    Base.metadata.create_all(engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """给工具函数用的会话上下文，自动提交/回滚。"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
