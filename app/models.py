"""简历的结构化数据模型（SQLAlchemy 2.0 声明式）。

为什么要有这一层：HR 的提问可以分成两类——
  1. 精确/聚合型："你工作几年了"、"你在哪几家公司待过"、"最高学历是什么"
  2. 语义型："你在推荐系统方向做过什么"
第 1 类交给关系型数据库（本文件），第 2 类交给向量库。只用向量库的话，
聚合型问题会靠概率去猜，很容易答错。

两张索引的数据都来自 resume/resume.yaml 单一数据源，由 app/ingest.py 生成，
避免"改了简历但数据库没更新"这类不一致。
"""

from __future__ import annotations

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Profile(Base):
    """基本信息。整份简历只有一条记录，id 固定为 1。"""

    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(128), default="")        # 求职意向 / 当前职位
    years_experience: Mapped[int] = mapped_column(Integer, default=0)  # 工作年限
    location: Mapped[str] = mapped_column(String(64), default="")
    email: Mapped[str] = mapped_column(String(128), default="")
    github: Mapped[str] = mapped_column(String(128), default="")
    blog: Mapped[str] = mapped_column(String(128), default="")
    summary: Mapped[str] = mapped_column(Text, default="")             # 个人简介


class Education(Base):
    """教育经历。"""

    __tablename__ = "education"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    school: Mapped[str] = mapped_column(String(128))
    major: Mapped[str] = mapped_column(String(128), default="")
    degree: Mapped[str] = mapped_column(String(32), default="")  # 本科 / 硕士
    start_date: Mapped[str] = mapped_column(String(16), default="")  # 统一用 "2020.09" 字符串，兼容"至今"
    end_date: Mapped[str] = mapped_column(String(16), default="")
    description: Mapped[str] = mapped_column(Text, default="")


class Experience(Base):
    """工作经历，一条记录对应一段任职。"""

    __tablename__ = "experience"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(128), default="")
    start_date: Mapped[str] = mapped_column(String(16), default="")
    end_date: Mapped[str] = mapped_column(String(16), default="")  # 在职能写"至今"
    description: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)    # 时间倒序展示


class Project(Base):
    """项目经历。highlights 存要点列表，JSON 列避免再拆一张表。"""

    __tablename__ = "project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(128), default="")
    company: Mapped[str] = mapped_column(String(128), default="")
    start_date: Mapped[str] = mapped_column(String(16), default="")
    end_date: Mapped[str] = mapped_column(String(16), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    tech: Mapped[list] = mapped_column(JSON, default=list)        # 技术栈
    highlights: Mapped[list] = mapped_column(JSON, default=list)  # 个人贡献 / 成果
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Skill(Base):
    """技能，按类别分组（语言 / 框架 / 存储 / 工具）。"""

    __tablename__ = "skill"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(64))
    level: Mapped[str] = mapped_column(String(32), default="")  # 熟练 / 熟悉 / 了解


class Award(Base):
    """证书与荣誉。"""

    __tablename__ = "award"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    date: Mapped[str] = mapped_column(String(16), default="")
    description: Mapped[str] = mapped_column(Text, default="")
