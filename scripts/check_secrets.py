"""Push 前体检：确认密钥不会被提交到 Git。

为什么需要这个：`.gitignore` 只能挡住"文件名匹配"的情况。真正危险的是密钥被
硬编码进了某个会被提交的文件里（比如你调试时在脚本里写了一行 api_key="sk-..."），
这种情况 gitignore 完全挡不住，而一旦 push 到公开仓库就等于泄露。

用法（在项目根目录执行）：
    python -m scripts.check_secrets

检查两项：
  1. `.env` 是否已被 git 跟踪（被跟踪 = 会随 push 上传）
  2. `.env` 里的真实密钥值是否出现在任何待提交的文件内容中
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

# 变量名里带这些词就当成敏感值
SENSITIVE_KEY = re.compile(r"KEY|TOKEN|SECRET|PASSWORD", re.I)


def read_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def placeholder_like(value: str) -> bool:
    """判断是不是 .env.example 里的占位符（如 sk-xxxxxxxx），这类不算真密钥。"""
    if not value or len(value) <= 8:
        return True
    return set(value.lower()) <= set("sk-x0123456789-_")


def is_tracked(rel_path: str) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", rel_path],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8"
    )
    return [f for f in result.stdout.splitlines() if f.strip()]


def main() -> int:
    if not (ROOT / ".git").exists():
        print("这个目录还不是 Git 仓库，先执行 git init。")
        return 1

    problems: list[str] = []

    # ---- 检查 1：.env 是否被跟踪 ----
    print("① .env 是否会被 push")
    # 直接问 git，比 grep 文件名可靠：grep "\\.env" 会把 .env.example 一起匹配上造成误报
    if is_tracked(".env"):
        problems.append(".env 已被 git 跟踪，push 会泄露密钥")
        print("   ❌ .env 已被跟踪！")
    else:
        print("   ✅ .env 未被跟踪")

    # ---- 检查 2：密钥值是否出现在待提交文件里 ----
    print("\n② 待提交文件里是否混入了真实密钥")
    secrets = {
        k: v
        for k, v in read_env(ENV_FILE).items()
        if SENSITIVE_KEY.search(k) and not placeholder_like(v)
    }
    files = tracked_files()
    print(f"   待提交文件 {len(files)} 个，待扫描密钥 {len(secrets)} 个")

    hits: list[str] = []
    for name in files:
        try:
            content = (ROOT / name).read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        for key, value in secrets.items():
            if value in content:
                hits.append(f"{name} ← 含 {key} 的值")

    if hits:
        problems.extend(hits)
        for item in hits:
            print(f"   ❌ {item}")
    else:
        print("   ✅ 没有发现泄露")

    # ---- 结论 ----
    print()
    if problems:
        print("⚠️ 发现 " + str(len(problems)) + " 个问题，先处理再 push：")
        for item in problems:
            print(f"   - {item}")
        if is_tracked(".env"):
            print("\n   修复方式（保留本地文件，只从 git 里移除）：")
            print("     git rm --cached .env")
            print("     git commit --amend -m \"...\"   # 或新开一个 commit")
        return 1

    print("✅ 体检通过，可以安全 push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
