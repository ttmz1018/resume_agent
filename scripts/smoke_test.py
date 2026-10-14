"""冒烟测试：不启动 HTTP 服务，直接验证检索工具与 Agent。

用法：
    python -m scripts.smoke_test
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent import ask  # noqa: E402
from app.retrieval.tools import ALL_TOOLS  # noqa: E402

TOOL_CALLS = [
    ("get_basic_profile", {}),
    ("get_education_and_awards", {}),
    ("list_experiences", {}),
    ("list_projects", {"keyword": "RAG"}),
    ("list_skills", {"category": "LLM"}),
    ("search_resume", {"query": "高并发或性能优化相关的经验"}),
]

QUESTIONS = [
    "他工作几年了？现在做什么方向？",           # 结构化：基本信息
    "他做过哪些和 RAG / Agent 相关的项目？",     # 语义检索
    "有没有高并发或性能优化相关的经验？",         # 语义检索
    "推荐一个长沙好吃的餐厅",                    # 越界，应当拒答
]


def test_tools() -> None:
    print("=" * 60)
    print("① 检索工具")
    print("=" * 60)
    by_name = {t.name: t for t in ALL_TOOLS}
    for name, args in TOOL_CALLS:
        result = by_name[name].invoke(args)
        preview = result if len(result) < 400 else result[:400] + " …"
        print(f"\n--- {name}({args}) ---\n{preview}")


def test_agent() -> None:
    print("\n" + "=" * 60)
    print("② Agent 端到端问答")
    print("=" * 60)
    for i, question in enumerate(QUESTIONS):
        answer, sources = ask(question, session_id=f"smoke-test-{i}")
        # 每条问题用独立 session，避免多轮上下文互相干扰
        print(f"\n【问】{question}")
        print(f"【答】{answer}")
        if sources:
            print(f"【依据】{', '.join(s['kind'] + '：' + s['title'] for s in sources)}")


if __name__ == "__main__":
    test_tools()
    test_agent()
    print("\n✅ 冒烟测试结束")
