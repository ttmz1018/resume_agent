"""共用的文本格式化助手。

单独抽出来的原因：工具输出（结构化查询路径）和向量切片（语义检索路径）必须用
同一套措辞。各写一份的话，同一份简历在两条路径上会被描述成两种样子，
模型综合两边的结果时就容易给出前后不一致的回答。
"""

from __future__ import annotations


def format_period(start: str | None, end: str | None) -> str:
    """拼时间区间。

    两端都为空时返回空串，避免输出 "时间： - " 这种残缺内容。
    应届生的项目常常没写起止时间，不处理的话模型会把残缺字符串当成有效信息，
    甚至顺着往下编时间。
    """
    if start and end:
        return f"{start} - {end}"
    return start or end or ""


def experience_label(years: int) -> str:
    """工作年限的表述。

    0 年要写成"应届毕业生"：直接说"0 年经验"既不好看，也容易被模型误读成
    "没有经验"而不是"应届生"。
    """
    if years and years > 0:
        return f"工作年限：{years} 年"
    return "工作经验：应届毕业生，暂无全职工作经历"
