#!/usr/bin/env python3
"""占位符一致性检查。

四件事：
1. **语法正确** —— `{{...}}` 必须成对闭合，花括号要配平
2. **无残留真值** —— 模板文件里不该出现看起来像被填过的占位符
   （如 `{{10.0.0.1}}`、`{{/opt/app/key}}` —— 说明有人把真值填进去了）
3. **命名规范** —— 占位符必须「字段名在前、示例在后」，
   形如 `{{字段名，如：示例值}}`。没有字段名的占位符（如 `{{如：短狠直接}}`）
   无法被稳定引用，使用者也看不出该填什么。
4. **登记完整** —— 模板里出现的占位符应能在 README 的「占位符速查」表里找到
   （新增占位符时忘了登记，使用者就会漏填）

占位符命名规范
--------------
    {{字段名}}              —— 无示例
    {{字段名，如：示例值}}   —— 带示例

比对时一律按**规范化名**（剥掉「，如：…」之后的示例部分）进行，
这样 `{{数据源1}}` 与 `{{数据源1，如 Zabbix}}` 视为同一个占位符。

用法：
    python3 scripts/check_placeholders.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TEMPLATE_FILES = ["SOUL.md", "IDENTITY.md", "USER.md", "MEMORY.md"]
README = REPO_ROOT / "README.md"

# 完整占位符：{{内容}}
PLACEHOLDER_RE = re.compile(r"\{\{([^{}]*)\}\}")
# 示例后缀分隔符：`字段名，如：示例值` / `字段名，如 示例值` / `字段名, 如: 示例值`
# 出现在**任意位置**都算示例后缀 —— 用它从内容里切出字段名。
EXAMPLE_SEP_RE = re.compile(r"[,，]\s*如\s*[：:]?\s*")
# 只有示例、没有字段名：`{{如：短狠直接}}` —— 内容以「如」开头
EXAMPLE_ONLY_RE = re.compile(r"^\s*如\s*[：:]?\s*")
# 通配写法 `{{...}}` —— 说明性文字，不是真实占位符
WILDCARD = "..."

# 填进占位符里的「真值」特征 —— 出现即说明有人误填
FILLED_VALUE_PATTERNS = [
    (re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"), "看起来是 IP 地址"),
    (re.compile(r"^/[\w./-]+$"), "看起来是绝对路径"),
    (re.compile(r"(?i)^(?:https?://|git@)"), "看起来是 URL"),
    (re.compile(r"(?i)\.(?:pem|key|p12|pfx)$"), "看起来是密钥文件名"),
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "看起来是日期"),
]


def normalize(content: str) -> str:
    """把占位符内容规范化为「字段名」。

    `数据源1，如 Zabbix` → `数据源1`
    `沟通风格，如：短狠直接` → `沟通风格`
    """
    return EXAMPLE_SEP_RE.split(content.strip(), maxsplit=1)[0].strip()


def strip_inline_code(line: str) -> str:
    """去掉行内代码（`` `...` ``）与代码块内容。

    README 里会写 ``grep -n '{{' *.md`` 这样的**命令示例**，
    里面的 `{{` 是字面量而非占位符起始 —— 不豁免会误判为「未闭合」。
    """
    return re.sub(r"`[^`]*`", "", line)


def check_syntax() -> list[str]:
    """占位符花括号必须配平。

    逐个 `{{` 往后找配对的 `}}` —— 不能用「负向前瞻」判断未闭合，
    那样会把每个正常占位符都误判（`{{X}}` 结尾后面通常没有 `{`）。
    """
    errors = []
    for name in TEMPLATE_FILES + ["README.md"]:
        path = REPO_ROOT / name
        if not path.exists():
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            # 行内代码里的 {{ 是字面量，不参与配平检查
            checked = strip_inline_code(line)
            idx = 0
            while True:
                start = checked.find("{{", idx)
                if start == -1:
                    break
                end = checked.find("}}", start + 2)
                if end == -1:
                    errors.append(
                        f"{name}:{lineno}  占位符未闭合（缺少 '}}'）: {line.strip()[:70]}"
                    )
                    break
                idx = end + 2
    return errors


def is_real_placeholder(content: str) -> bool:
    """`{{...}}` 是通配写法（说明性文字），不是真实占位符。"""
    return content.strip() not in ("", WILDCARD)


def check_filled_values() -> list[str]:
    """占位符里不能塞真值。"""
    errors = []
    for name in TEMPLATE_FILES:
        path = REPO_ROOT / name
        if not path.exists():
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for content in PLACEHOLDER_RE.findall(line):
                content = content.strip()
                if not is_real_placeholder(content):
                    continue
                for pattern, desc in FILLED_VALUE_PATTERNS:
                    if pattern.search(content):
                        errors.append(
                            f"{name}:{lineno}  占位符里疑似填了真值（{desc}）: {{{{{content}}}}}"
                        )
    return errors


def check_naming() -> list[str]:
    """占位符必须有字段名。

    `{{如：短狠直接}}` 这类只有示例没有字段名的占位符：
    - 使用者看不出这里该填什么
    - 无法在 README 速查表里稳定引用（示例值会变）
    """
    errors = []
    for name in TEMPLATE_FILES:
        path = REPO_ROOT / name
        if not path.exists():
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for content in PLACEHOLDER_RE.findall(line):
                content = content.strip()
                if not is_real_placeholder(content):
                    continue
                if EXAMPLE_ONLY_RE.match(content):
                    example = EXAMPLE_ONLY_RE.sub("", content).strip()
                    errors.append(
                        f"{name}:{lineno}  占位符缺少字段名（只有示例）: {{{{{content}}}}}"
                        f"  → 改为 {{{{字段名，如：{example}}}}}"
                    )
    return errors


def check_registry() -> list[str]:
    """模板里的占位符应登记在 README 的速查表里。

    按**规范化名**比对（去重），`{{数据源1}}` 与 `{{数据源1，如 Zabbix}}`
    视为同一个占位符，避免重复报告。
    """
    readme = README.read_text(encoding="utf-8") if README.exists() else ""
    # 速查表区域（从「占位符速查」到下一个一级标题）
    match = re.search(r"## 占位符速查(.*?)(?=\n## )", readme, re.DOTALL)
    if not match:
        return ["README.md  找不到「占位符速查」章节"]
    table = match.group(1)
    registered = {normalize(c) for c in PLACEHOLDER_RE.findall(table)}
    registered.discard("")

    missing = []
    seen: set[tuple[str, str]] = set()
    for name in TEMPLATE_FILES:
        path = REPO_ROOT / name
        if not path.exists():
            continue
        for content in PLACEHOLDER_RE.findall(
            path.read_text(encoding="utf-8")
        ):
            key = normalize(content)
            if not is_real_placeholder(key):
                continue
            if key in registered:
                continue
            if (name, key) in seen:
                continue
            seen.add((name, key))
            missing.append(f"{name}  占位符 {{{{{key}}}}} 未登记到 README 速查表")

    return missing


def main() -> int:
    errors: list[str] = []
    errors += check_syntax()
    errors += check_filled_values()
    errors += check_naming()
    errors += check_registry()

    if errors:
        print("❌ 占位符检查未通过：\n", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        print(
            "\n修复方式：\n"
            "  · 花括号不配平 → 检查是否漏了 '}}'\n"
            "  · 占位符里填了真值 → 改回 {{描述}} 形式，真值放本地\n"
            "  · 占位符缺字段名 → 改成 {{字段名，如：示例值}}\n"
            "  · 未登记速查表 → 在 README 的「占位符速查」表里补一行",
            file=sys.stderr,
        )
        return 1

    total = 0
    for name in TEMPLATE_FILES:
        path = REPO_ROOT / name
        if path.exists():
            total += len(PLACEHOLDER_RE.findall(path.read_text(encoding="utf-8")))
    print(f"✅ 占位符检查通过（{total} 个占位符，语法正确、命名规范、无真值残留、已登记）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
