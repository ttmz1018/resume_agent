"""Agent 可以调用的检索工具。

设计取舍：为什么不给模型一个"执行任意 SQL"的工具？
  1. 安全 —— 这个 Agent 后面要挂成公开链接，等于把数据库交给陌生人；
  2. 稳定 —— LLM 现写的 SQL 经常表名/字段名写错，报错后容易陷入反复重试；
  3. 可约束 —— 每个工具只做一件事、返回格式固定，模型选工具的准确率更高。
所以这里按"实体"封装成受控查询工具，而不是暴露原始 SQL。

每个工具的返回值末尾都会带一行「（来源：xxx）」，一是让模型知道信息出处，
二是服务端可以从工具输出里提取出依据来源，回给前端做可追溯展示。
"""

from __future__ import annotations

from langchain_core.tools import tool

from app import config
from app.db import session_scope
from app.formatting import experience_label as _experience_label
from app.formatting import format_period as _period
from app.models import Award, Education, Experience, Profile, Project, Skill
from app.retrieval.vector_store import get_vector_store


def _source(label: str) -> str:
    """给工具输出追加来源标记。"""
    return f"（来源：{label}）"


# ------------------------------------------------------------------
# 结构化查询：SQLite
# ------------------------------------------------------------------
@tool(parse_docstring=True)
def get_basic_profile() -> str:
    """查询候选人的基本信息：姓名、求职意向、工作年限、所在城市、联系方式和个人简介。
    当问题问及"他叫什么"、"工作几年了"、"他是做什么方向的"、"在哪个城市"、"怎么联系他"时使用。
    """
    with session_scope() as session:
        profile = session.get(Profile, 1)
        if profile is None:
            return "简历中还没有录入基本信息。"

        lines = [
            f"姓名：{profile.name}",
            f"求职意向：{profile.title}",
            _experience_label(profile.years_experience),
        ]
        if profile.location:
            lines.append(f"所在城市：{profile.location}")
        if profile.email:
            lines.append(f"邮箱：{profile.email}")
        if profile.github:
            lines.append(f"GitHub：{profile.github}")
        if profile.blog:
            lines.append(f"博客：{profile.blog}")
        if profile.summary:
            lines.append(f"个人简介：{profile.summary}")
        return "\n".join(lines) + "\n" + _source("基本信息")


@tool(parse_docstring=True)
def get_education_and_awards() -> str:
    """查询候选人的教育经历，以及证书和荣誉。
    当问题问及"什么学历"、"哪个学校毕业的"、"什么专业"、"有哪些证书或获奖"时使用。
    """
    with session_scope() as session:
        educations = session.query(Education).all()
        awards = session.query(Award).all()

    if not educations and not awards:
        return "简历中还没有录入教育经历与荣誉信息。"

    parts = []
    if educations:
        parts.append("教育经历：")
        for item in educations:
            period = _period(item.start_date, item.end_date)
            line = f"- {item.school} | {item.major} | {item.degree}"
            if period:
                line += f" | {period}"
            if item.description:
                line += f"\n  补充：{item.description}"
            parts.append(line)
    if awards:
        parts.append("证书与荣誉：")
        for item in awards:
            line = f"- {item.name}"
            if item.date:
                line += f"（{item.date}）"
            if item.description:
                line += f"：{item.description}"
            parts.append(line)
    return "\n".join(parts) + "\n" + _source("教育经历与证书荣誉")


@tool(parse_docstring=True)
def list_experiences(company: str = "") -> str:
    """查询候选人的工作经历，包含公司、职位、任职时间和工作内容。
    当问题问及"在哪些公司工作过"、"上一家公司在哪"、"某段经历主要做什么"时使用。

    Args:
        company: 可选，公司名称关键字。只在询问某一家具体公司时填写，问"所有经历"时留空。
    """
    with session_scope() as session:
        query = session.query(Experience).order_by(Experience.sort_order)
        if company:
            query = query.filter(Experience.company.like(f"%{company}%"))
        rows = query.all()
        profile = session.get(Profile, 1)

    if not rows:
        if company:
            return f"简历中没有匹配「{company}」的工作经历。"
        # 区分"应届生本来就没有工作经历"和"数据漏录了"。
        # 不区分的话模型可能把应届生说成"简历信息缺失"，面试官观感很差。
        if profile is not None and not profile.years_experience:
            return "候选人是应届毕业生，简历中没有全职工作经历。" + _source("工作经历为空")
        return "简历中还没有录入工作经历。"

    parts = []
    for item in rows:
        period = _period(item.start_date, item.end_date)
        head = f"- {item.company} | {item.title}"
        if period:
            head += f" | {period}"
        parts.append(f"{head}\n  工作内容：{item.description}")
    labels = "；".join(f"工作经历 - {r.company}" for r in rows)
    return "\n".join(parts) + "\n" + _source(labels)


@tool(parse_docstring=True)
def list_projects(keyword: str = "") -> str:
    """查询候选人的项目经历，包含项目名称、担任角色、技术栈、项目描述和个人贡献。
    当问题问及"做过哪些项目"、"某个项目的技术栈是什么"、"他在某个项目里负责什么"时使用。

    Args:
        keyword: 可选，项目名称或技术栈关键字，例如"RAG"、"订单"。问"所有项目"时留空。
    """
    with session_scope() as session:
        query = session.query(Project).order_by(Project.sort_order)
        rows = query.all()

    if keyword:
        kw = keyword.lower()
        rows = [
            r
            for r in rows
            if kw in r.name.lower()
            or kw in (r.description or "").lower()
            or any(kw in str(t).lower() for t in (r.tech or []))
            or any(kw in str(h).lower() for h in (r.highlights or []))
        ]

    if not rows:
        return f"简历中没有匹配「{keyword}」的项目经历。" if keyword else "简历中还没有录入项目经历。"

    parts = []
    for item in rows:
        period = _period(item.start_date, item.end_date)
        head = f"- {item.name} | 角色：{item.role}"
        if item.company:
            head += f" | 所属：{item.company}"
        if period:
            head += f" | {period}"
        block = [head]
        if item.tech:
            block.append(f"  技术栈：{'、'.join(item.tech)}")
        if item.description:
            block.append(f"  项目描述：{item.description}")
        if item.highlights:
            block.append("  个人贡献与成果：")
            block.extend(f"    · {h}" for h in item.highlights)
        parts.append("\n".join(block))

    labels = "；".join(f"项目经历 - {r.name}" for r in rows)
    return "\n".join(parts) + "\n" + _source(labels)


@tool(parse_docstring=True)
def list_skills(category: str = "") -> str:
    """查询候选人的技能清单，按类别分组，并标注熟练程度。
    当问题问及"会哪些技术"、"Java 怎么样"、"熟悉哪些中间件/框架"时使用。

    Args:
        category: 可选，技能类别关键字，例如"编程语言"、"存储与中间件"。问全部技能时留空。
    """
    with session_scope() as session:
        query = session.query(Skill)
        if category:
            query = query.filter(Skill.category.like(f"%{category}%"))
        rows = query.all()

    if not rows:
        return f"简历中没有匹配「{category}」的技能。" if category else "简历中还没有录入技能信息。"

    grouped: dict[str, list[Skill]] = {}
    for item in rows:
        grouped.setdefault(item.category, []).append(item)

    parts = [
        f"{name}：" + "、".join(f"{s.name}（{s.level}）" for s in items)
        for name, items in grouped.items()
    ]
    labels = "；".join(f"技能 - {name}" for name in grouped)
    return "\n".join(parts) + "\n" + _source(labels)


# ------------------------------------------------------------------
# 语义检索：Chroma
# ------------------------------------------------------------------
@tool(parse_docstring=True)
def search_resume(query: str, k: int = config.RETRIEVE_TOP_K) -> str:
    """对整份简历做语义检索，返回最相关的原文片段。
    适合细节性或开放性问题，例如"他在推荐系统方向做过什么"、"有没有高并发/性能优化的经验"、
    "这个项目的难点在哪"。当结构化查询工具覆盖不到，或问题比较笼统时使用。

    Args:
        query: 检索用的自然语言问题或关键词，尽量保留问题中的关键信息。
        k: 返回片段数量，默认 4，通常不需要修改。
    """
    top_k = max(1, min(int(k or config.RETRIEVE_TOP_K), 8))
    docs = get_vector_store().similarity_search(query, k=top_k)
    if not docs:
        return "没有检索到相关片段。" + _source("语义检索无命中")

    parts = []
    labels = []
    for doc in docs:
        label = doc.metadata.get("title", "简历片段")
        labels.append(label)
        parts.append(f"[{label}]\n{doc.page_content}")

    deduped = list(dict.fromkeys(labels))
    return "\n\n".join(parts) + "\n" + _source("；".join(f"语义检索 - {x}" for x in deduped))


ALL_TOOLS = [
    get_basic_profile,
    get_education_and_awards,
    list_experiences,
    list_projects,
    list_skills,
    search_resume,
]
