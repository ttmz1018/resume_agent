"""把简历 YAML 灌入两套索引。

用法（在 resume_agent 目录下执行）：
    python -m app.ingest        # 全量重建，可反复执行，结果幂等

流程：
    resume/resume.yaml  ──┬──>  data/resume.db   (SQLite，结构化)
                          └──>  data/chroma/     (向量索引，语义)
"""

from __future__ import annotations

import shutil
from typing import Any

import yaml
from langchain_core.documents import Document

from app import config
from app.db import engine, init_db, session_scope
from app.formatting import experience_label, format_period
from app.models import Award, Base, Education, Experience, Profile, Project, Skill
from app.retrieval.vector_store import get_embeddings, get_vector_store

# 切片类型 -> 中文标签，用于回答时展示依据来源
KIND_LABELS = {
    "profile": "基本信息",
    "education": "教育经历",
    "experience": "工作经历",
    "project": "项目经历",
    "skill": "技能",
    "award": "证书与荣誉",
}


def load_resume() -> dict[str, Any]:
    """读取简历 YAML。"""
    if not config.RESUME_FILE.exists():
        raise FileNotFoundError(f"没找到简历文件：{config.RESUME_FILE}")
    with open(config.RESUME_FILE, encoding="utf-8") as fp:
        return yaml.safe_load(fp) or {}


# ------------------------------------------------------------------
# ① 结构化索引：YAML -> SQLite
# ------------------------------------------------------------------
def write_sqlite(resume: dict[str, Any]) -> None:
    """全量重建 SQLite。

    这里用 drop_all + create_all 而不是增量 upsert：简历条目数很少（几十条），
    全量重建成本几乎为零，但可以从根上避免"删掉的经历还留在库里"。
    """
    Base.metadata.drop_all(engine)
    init_db()

    with session_scope() as session:
        profile = resume.get("profile") or {}
        session.add(
            Profile(
                id=1,
                name=profile.get("name", ""),
                title=profile.get("title", ""),
                years_experience=int(profile.get("years_experience", 0) or 0),
                location=profile.get("location", ""),
                email=profile.get("email", ""),
                github=profile.get("github", ""),
                blog=profile.get("blog", ""),
                summary=(profile.get("summary") or "").strip(),
            )
        )

        for item in resume.get("education") or []:
            session.add(
                Education(
                    school=item.get("school", ""),
                    major=item.get("major", ""),
                    degree=item.get("degree", ""),
                    start_date=str(item.get("start_date", "")),
                    end_date=str(item.get("end_date", "")),
                    description=(item.get("description") or "").strip(),
                )
            )

        # 经历按 YAML 里的顺序编号，YAML 中已按时间倒序排列
        for order, item in enumerate(resume.get("experiences") or []):
            session.add(
                Experience(
                    company=item.get("company", ""),
                    title=item.get("title", ""),
                    start_date=str(item.get("start_date", "")),
                    end_date=str(item.get("end_date", "")),
                    description=(item.get("description") or "").strip(),
                    sort_order=order,
                )
            )

        for order, item in enumerate(resume.get("projects") or []):
            session.add(
                Project(
                    name=item.get("name", ""),
                    role=item.get("role", ""),
                    company=item.get("company", ""),
                    start_date=str(item.get("start_date", "")),
                    end_date=str(item.get("end_date", "")),
                    description=(item.get("description") or "").strip(),
                    tech=list(item.get("tech") or []),
                    highlights=list(item.get("highlights") or []),
                    sort_order=order,
                )
            )

        for group in resume.get("skills") or []:
            for item in group.get("items") or []:
                session.add(
                    Skill(
                        category=group.get("category", ""),
                        name=item.get("name", ""),
                        level=item.get("level", ""),
                    )
                )

        for item in resume.get("awards") or []:
            session.add(
                Award(
                    name=item.get("name", ""),
                    date=str(item.get("date", "")),
                    description=(item.get("description") or "").strip(),
                )
            )


# ------------------------------------------------------------------
# ② 语义索引：YAML -> Chroma
# ------------------------------------------------------------------
def build_chunks(resume: dict[str, Any]) -> list[Document]:
    """面向结构切片：一段经历 / 一个项目 / 一类技能各成一个 chunk。

    简历本身就是高度结构化的数据，按固定长度强行切分会把一段经历拦腰截断，
    检索时召回的片段语义不完整。按实体切块能让每个 chunk 自洽，
    同时每个 chunk 都带上姓名和职位，避免"指代不明"导致的误召回。
    """
    profile = resume.get("profile") or {}
    name = profile.get("name", "候选人")
    title = profile.get("title", "")
    chunks: list[Document] = []

    # ---- 基本信息 ----
    profile_lines = [
        f"{name}的基本信息",
        f"姓名：{name}",
        f"求职意向：{title}",
        experience_label(int(profile.get("years_experience", 0) or 0)),
    ]
    if profile.get("location"):
        profile_lines.append(f"所在城市：{profile['location']}")
    if profile.get("email"):
        profile_lines.append(f"邮箱：{profile['email']}")
    if profile.get("github"):
        profile_lines.append(f"GitHub：{profile['github']}")
    if profile.get("blog"):
        profile_lines.append(f"博客：{profile['blog']}")
    if profile.get("summary"):
        profile_lines.append(f"个人简介：{profile['summary']}")
    chunks.append(
        Document(
            page_content="\n".join(profile_lines),
            metadata={"kind": "profile", "title": f"{name}的基本信息"},
        )
    )

    # ---- 教育经历 ----
    for item in resume.get("education") or []:
        lines = [
            f"{name}的教育经历：{item.get('school', '')}",
            f"专业：{item.get('major', '')}",
            f"学历：{item.get('degree', '')}",
        ]
        period = format_period(item.get("start_date"), item.get("end_date"))
        if period:
            lines.append(f"时间：{period}")
        if (item.get("description") or "").strip():
            lines.append(f"在校情况：{item['description'].strip()}")
        chunks.append(
            Document(
                page_content="\n".join(lines),
                metadata={"kind": "education", "title": f"教育经历 - {item.get('school', '')}"},
            )
        )

    # ---- 工作经历 ----
    for item in resume.get("experiences") or []:
        lines = [
            f"{name}的工作经历：{item.get('company', '')}",
            f"职位：{item.get('title', '')}",
        ]
        period = format_period(item.get("start_date"), item.get("end_date"))
        if period:
            lines.append(f"任职时间：{period}")
        if (item.get("description") or "").strip():
            lines.append(f"工作内容：{item['description'].strip()}")
        chunks.append(
            Document(
                page_content="\n".join(lines),
                metadata={"kind": "experience", "title": f"工作经历 - {item.get('company', '')}"},
            )
        )

    # ---- 项目经历 ----
    for item in resume.get("projects") or []:
        lines = [
            f"{name}的项目经历：{item.get('name', '')}",
            f"担任角色：{item.get('role', '')}",
        ]
        if item.get("company"):
            lines.append(f"所属：{item['company']}")
        period = format_period(item.get("start_date"), item.get("end_date"))
        if period:
            lines.append(f"项目时间：{period}")
        if item.get("tech"):
            lines.append(f"技术栈：{'、'.join(item['tech'])}")
        if (item.get("description") or "").strip():
            lines.append(f"项目描述：{item['description'].strip()}")
        highlights = item.get("highlights") or []
        if highlights:
            lines.append("个人贡献与成果：")
            lines.extend(f"- {h}" for h in highlights)
        chunks.append(
            Document(
                page_content="\n".join(lines),
                metadata={"kind": "project", "title": f"项目经历 - {item.get('name', '')}"},
            )
        )

    # ---- 技能（按类别成块） ----
    for group in resume.get("skills") or []:
        items = group.get("items") or []
        if not items:
            continue
        text = "\n".join(
            [
                f"{name}的技能：{group.get('category', '')}",
                "掌握情况：" + "、".join(f"{i.get('name', '')}（{i.get('level', '')}）" for i in items),
            ]
        )
        chunks.append(
            Document(
                page_content=text,
                metadata={"kind": "skill", "title": f"技能 - {group.get('category', '')}"},
            )
        )

    # ---- 证书与荣誉 ----
    awards = resume.get("awards") or []
    if awards:
        lines = [f"{name}的证书与荣誉"]
        for a in awards:
            line = f"- {a.get('name', '')}"
            if a.get("date"):
                line += f"（{a['date']}）"
            if (a.get("description") or "").strip():
                line += f"：{a['description'].strip()}"
            lines.append(line)
        chunks.append(
            Document(page_content="\n".join(lines), metadata={"kind": "award", "title": "证书与荣誉"})
        )

    return chunks


def rebuild_vector_store(chunks: list[Document]) -> int:
    """清空并重建向量集合，返回写入的切片数。"""
    config.ensure_dirs()
    # 先清掉旧目录，避免上一版简历的切片残留
    if config.CHROMA_DIR.exists():
        shutil.rmtree(config.CHROMA_DIR, ignore_errors=True)
    # 进程内可能已经有缓存的实例，需要失效掉
    get_vector_store.cache_clear()

    store = get_vector_store()
    ids = [f"{doc.metadata['kind']}-{i:03d}" for i, doc in enumerate(chunks)]
    store.add_documents(documents=chunks, ids=ids)
    return len(chunks)


def ingest_all() -> int:
    """完整灌库流程，返回切片数。"""
    resume = load_resume()
    write_sqlite(resume)
    chunks = build_chunks(resume)
    rebuild_vector_store(chunks)
    return len(chunks)


def ensure_index() -> bool:
    """索引不存在时自动构建，服务启动时调用。返回是否执行了构建。"""
    from app.retrieval.vector_store import chunk_count

    if config.SQLITE_FILE.exists() and chunk_count() > 0:
        return False
    ingest_all()
    return True


def main() -> None:
    chunks = ingest_all()
    print(f"✅ 简历已灌入两套索引：{config.SQLITE_FILE} / {config.CHROMA_DIR}")
    print(f"   向量切片数量：{chunks}")


if __name__ == "__main__":
    main()
