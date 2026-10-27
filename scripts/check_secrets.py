#!/usr/bin/env python3
"""敏感信息扫描 —— 防止真实凭据 / 内网地址被提交到公开模板仓。

本仓是**公开**的，所有内容都应保持为「可公开」状态。
`{{占位符}}` 是允许的，真实值不允许。

设计要点：
1. **占位符豁免** —— `{{...}}` 包裹的内容一律跳过。
   模板里本来就有 `{{公网 IP}}` `{{密钥路径}}` 这类字样，
   不豁免会满屏误报。
2. **按文件类型分策略** —— README / 治理文件是「说明性」的，
   里面提到 `~/.workbuddy/`、`10.0.0.0/8` 之类的示例是正常的；
   模板文件（USER.md / MEMORY.md）才是高危区。
3. **宁可误报也不漏报** —— 误报会在 CI 里明确指出行号，改起来很快；
   漏报一旦推上去，git 历史里就洗不掉了。

用法：
    python3 scripts/check_secrets.py            # 扫描整个仓库
    python3 scripts/check_secrets.py <文件> ... # 只扫指定文件
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 允许出现敏感字样的「说明性」文件 —— 里面的示例是给读者看的
DOC_FILES = {
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "ROADMAP.md",
    "CHANGELOG.md",
}

SKIP_DIRS = {".git", ".github", "scripts", "node_modules", "__pycache__", ".pytest_cache"}

# ---------------------------------------------------------------------------
# 规则定义
# ---------------------------------------------------------------------------
# 每条规则：(规则名, 正则, 说明, 是否仅在模板文件生效)
# 「仅模板文件生效」= 只在 USER.md / MEMORY.md / SOUL.md / IDENTITY.md 里查

RULES: list[tuple[str, re.Pattern, str, bool]] = [
    # --- 私钥 / 证书 ---
    (
        "私钥文件",
        re.compile(r"-----BEGIN\s+(RSA|DSA|EC|OPENSSH|PGP)?\s*PRIVATE KEY-----"),
        "疑似私钥内容",
        False,
    ),
    (
        "AWS 访问密钥",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "AWS Access Key ID",
        False,
    ),
    (
        "GitHub Token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        "GitHub Personal Access Token",
        False,
    ),
    (
        "OpenAI 风格密钥",
        re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
        "API 密钥（sk- 前缀）",
        False,
    ),
    (
        "Slack Token",
        re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
        "Slack Token",
        False,
    ),
    (
        "JWT",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        "JWT 令牌",
        False,
    ),
    # --- 内网地址 ---
    (
        "内网 IP",
        re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})\b"),
        "内网 IP 地址",
        True,
    ),
    (
        "公网 IP",
        re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        "具体 IP 地址",
        True,
    ),
    (
        "内网域名",
        re.compile(r"\b[\w.-]+\.(?:internal|local|lan|corp|intra)\b"),
        "内网域名后缀",
        True,
    ),
    # --- 凭据赋值 ---
    (
        "疑似凭据赋值",
        re.compile(
            r"(?i)\b(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key)\b"
            r"\s*[:=]\s*[\"']?(?!\{\{)([^\s\"'#$]{6,})"
        ),
        "疑似硬编码凭据（password / token / api_key 等）",
        True,
    ),
    (
        "凭据文件路径",
        # 要求带路径分隔符或明确的文件扩展名，避免误报
        # `process.env` / `os.environ` 这类 API 名与「env 文件」的中文描述
        re.compile(
            r"(?i)(?:[\w.-]+/)*(?:\.env(?:\.[\w]+)?|credentials(?:\.\w+)?|secrets?(?:\.\w+)?"
            r"|id_rsa|id_ed25519|id_ecdsa)(?:\b|/)"
        ),
        "疑似凭据文件路径",
        True,
    ),
    (
        "URL 中的凭据",
        re.compile(r"://[^\s/:@]+:[^\s/@]+@"),
        "URL 里内嵌了用户名密码",
        False,
    ),
]

# 这些词在模板里是「说明 API 用法」，不是真实凭据文件路径
SAFE_TOKEN_PATTERNS = [
    re.compile(r"process\.env"),
    re.compile(r"os\.environ"),
    re.compile(r"os\.getenv"),
    re.compile(r"env 文件"),
    re.compile(r"env 变量"),
    # 教学性用法：`.env` / `.env.example` 的正确用法示范
    re.compile(r"\.env\.example"),
    re.compile(r"`\.env`\s*文件"),
    re.compile(r"\.env`\s*（不提交）"),
]


def strip_placeholders(text: str) -> str:
    """把 `{{...}}` 占位符整段替换掉，避免误报。

    占位符里可能包含「内网 IP」「密钥路径」等字样，
    但它们是模板说明，不是真实值。
    """
    return re.sub(r"\{\{[^}]*\}\}", "«PLACEHOLDER»", text)


def iter_files(explicit: list[str]) -> list[Path]:
    if explicit:
        return [Path(p) for p in explicit]
    files = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf"}:
            continue
        files.append(path)
    return files


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """返回 [(行号, 规则名, 说明)]。"""
    try:
        raw = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    rel = path.relative_to(REPO_ROOT).as_posix()
    is_doc = rel in DOC_FILES
    is_template = rel in {"USER.md", "MEMORY.md", "SOUL.md", "IDENTITY.md"}

    findings: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(raw.splitlines(), start=1):
        cleaned = strip_placeholders(line)
        for name, pattern, desc, template_only in RULES:
            if template_only and not is_template:
                continue
            if is_doc and name in {"公网 IP", "凭据文件路径"}:
                # 说明性文档里的示例允许出现
                continue
            match = pattern.search(cleaned)
            if match:
                # 命中后检查该行是否含「安全词」——
                # 如 `process.env` 这类 API 出现位置不该算凭据路径
                if name == "凭据文件路径" and any(
                    p.search(cleaned) for p in SAFE_TOKEN_PATTERNS
                ):
                    continue
                findings.append((lineno, name, desc))
    return findings


def main() -> int:
    explicit = [a for a in sys.argv[1:] if not a.startswith("-")]
    files = iter_files(explicit)

    total: list[tuple[Path, int, str, str]] = []
    for path in files:
        for lineno, name, desc in scan_file(path):
            total.append((path, lineno, name, desc))

    if not total:
        print("✅ 敏感信息扫描通过 —— 未发现疑似真实凭据或内网地址")
        return 0

    print("❌ 敏感信息扫描发现疑似问题：\n", file=sys.stderr)
    for path, lineno, name, desc in total:
        rel = path.relative_to(REPO_ROOT).as_posix()
        print(f"  {rel}:{lineno}  [{name}] {desc}", file=sys.stderr)

    print(
        "\n本仓是公开模板仓，以上内容不应提交。\n"
        "如果确实是示例需要保留，请写成 {{...}} 占位符形式，\n"
        "或在本脚本的 DOC_FILES 规则中显式豁免该文件。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
