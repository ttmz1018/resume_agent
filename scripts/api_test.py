"""HTTP 接口自测：验证 /health、/api/profile、/api/chat 与限流。

用法（先启动服务）：
    python -m scripts.api_test                  # 常规用例
    python -m scripts.api_test --flood 25       # 连续打 25 次，验证限流是否生效
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:7860"


def request(method: str, path: str, payload: dict | None = None) -> tuple[int, object]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body.strip().startswith(("{", "[")) else body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body


def chat(message: str, session_id: str) -> tuple[int, object]:
    return request("POST", "/api/chat", {"message": message, "session_id": session_id})


def show(status: int, body: object, limit: int = 220) -> None:
    if isinstance(body, dict) and "answer" in body:
        print(f"  HTTP {status}  答：{body['answer'][:limit]}")
        print(f"           依据：{', '.join(s['kind'] + '：' + s['title'] for s in body['sources'])}")
    else:
        print(f"  HTTP {status}  {str(body)[:limit]}")


def run_cases() -> None:
    print("① 健康检查")
    status, body = request("GET", "/health")
    show(status, body)

    print("\n② 首屏信息")
    status, body = request("GET", "/api/profile")
    show(status, body)

    print("\n③ 聊天页面")
    status, body = request("GET", "/")
    print(f"  HTTP {status}  页面大小 {len(str(body))} 字符")

    print("\n④ 单轮问答")
    status, body = chat("他最近做的个人项目是什么？", "api-test-1")
    show(status, body)

    print("\n⑤ 多轮追问（复用同一个 session_id，测上下文是否保留）")
    status, body = chat("它用到了哪些技术？", "api-test-1")
    show(status, body)

    print("\n⑥ 越界问题（应拒答）")
    status, body = chat("帮我写一个 Python 快排", "api-test-2")
    show(status, body)

    print("\n⑦ 空消息校验（应返回 422/400）")
    status, body = request("POST", "/api/chat", {"message": "", "session_id": "api-test-3"})
    show(status, body)


def run_flood(times: int) -> None:
    print(f"⑧ 限流测试：连续请求 {times} 次，观察是否出现 429")
    codes: dict[int, int] = {}
    for i in range(times):
        status, _ = chat("他工作几年了？", f"flood-{i % 3}")
        codes[status] = codes.get(status, 0) + 1
    for code, count in sorted(codes.items()):
        note = "（限流生效）" if code == 429 else ""
        print(f"  HTTP {code}: {count} 次 {note}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--flood", type=int, default=0, help="连续请求次数，用于验证限流")
    parser.add_argument("--base", default=BASE, help="服务地址")
    args = parser.parse_args()
    BASE = args.base  # noqa: F841

    if args.flood:
        run_flood(args.flood)
    else:
        run_cases()
    print("\n✅ 接口自测结束")
