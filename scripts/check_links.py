#!/usr/bin/env python3
"""内部链接检查 —— 确认 README / 治理文件里的相对链接不断。

公开仓的链接一断，读者点进去看到 404 —— 对模板仓尤其致命：
用户是照着 README 一步步填配置的，链接断了整条路径就断了。

检查两类链接：
1. **相对链接** —— `[文字](相对路径)`，指向仓内文件 → 文件必须存在
2. **锚点链接** —— `[文字](#小节标题)` → 目标标题必须存在

外链（http/https）只做格式检查，不发网络请求（CI 里不能依赖网络）。

用法：
    python3 scripts/check_links.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 会被检查的 Markdown 文件
DOC_FILES = [
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "ROADMAP.md",
]

# 跳过目录
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", "scripts"}

# Markdown 链接：[文字](目标)
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
# 去掉代码块，避免把示例代码里的链接语法误判
CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]*`")


def iter_doc_files() -> list[Path]:
    files = []
    for path in sorted(REPO_ROOT.rglob("*.md")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return files


def extract_headings(text: str) -> set[str]:
    """收集标题文本（GitHub 锚点规则：去空格、转小写、连字符化）。"""
    headings = set()
    for line in text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*$", line)
        if m:
            headings.add(anchorize(m.group(2)))
    return headings


def anchorize(text: str) -> str:
    """把标题文本转成 GitHub 风格锚点。"""
    text = re.sub(r"[`*_~]", "", text).strip().lower()
    text = re.sub(r"[^\w\s一-鿿-]", "", text)
    return re.sub(r"\s+", "-", text)


def check() -> list[str]:
    errors: list[str] = []

    # 预加载各文件的标题集合，供锚点校验
    heading_cache: dict[Path, set[str]] = {}

    for path in iter_doc_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        raw = path.read_text(encoding="utf-8")
        # 去掉代码块与行内代码 —— 里面的方括号不是链接
        text = CODE_FENCE_RE.sub("", raw)
        text = INLINE_CODE_RE.sub("", text)

        for lineno, line in enumerate(text.splitlines(), start=1):
            for label, target in LINK_RE.findall(line):
                if not target or target.startswith(("http://", "https://", "mailto:")):
                    # 外链只查基本格式
                    if " " in target and not target.startswith("<"):
                        errors.append(f"{rel}:{lineno}  链接目标含空格（可能未用 <> 包裹）: {target}")
                    continue

                if target.startswith("#"):
                    # 锚点链接
                    anchor = target[1:].lower()
                    if not anchor:
                        continue
                    if path not in heading_cache:
                        heading_cache[path] = extract_headings(raw)
                    if anchor not in heading_cache[path]:
                        errors.append(
                            f"{rel}:{lineno}  锚点链接指向不存在的标题: #{anchor}"
                        )
                    continue

                # 相对路径链接
                clean = target.split("#")[0].strip()
                if not clean:
                    continue
                resolved = (path.parent / clean).resolve()
                if not resolved.exists():
                    errors.append(
                        f"{rel}:{lineno}  链接指向不存在的文件: {target}"
                    )

    return errors


def main() -> int:
    errors = check()
    if errors:
        print("❌ 内部链接检查未通过：\n", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        print(
            "\n修复方式：\n"
            "  · 文件名对不上 → 改名或改链接（注意大小写）\n"
            "  · 锚点不存在 → 改标题或改锚点\n"
            "  · 指向仓外 → 换成完整 URL",
            file=sys.stderr,
        )
        return 1

    count = len(iter_doc_files())
    print(f"✅ 内部链接检查通过（{count} 个 Markdown 文件，相对链接与锚点均有效）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
