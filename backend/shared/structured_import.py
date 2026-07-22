"""Deterministic Markdown/marker importer for Structured Episodes."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MAX_SOURCE_CHARS = 200_000

TYPE_SLUGS = {
    "HOOK": "hook", "CTA_TAG": "cta", "PROBLEM": "problem", "STORY": "story",
    "MECHANISM": "mechanism", "JUDGMENT": "judgment", "METHOD": "method",
    "SHORT_OUTRO": "short_outro", "BRIDGE_IN": "bridge_in", "BRIDGE_OUT": "bridge_out",
    "COMMENT_CTA": "comment_cta",
}
ALIASES = {
    "钩子": "HOOK", "开头": "HOOK", "开场": "HOOK", "高价值开头": "HOOK",
    "行动引导": "CTA_TAG", "设置引导": "CTA_TAG", "前置引导": "CTA_TAG",
    "问题": "PROBLEM", "困境": "PROBLEM", "矛盾": "PROBLEM",
    "故事": "STORY", "案例": "STORY", "历史故事": "STORY",
    "机制": "MECHANISM", "原理": "MECHANISM", "底层逻辑": "MECHANISM",
    "判断": "JUDGMENT", "判词": "JUDGMENT", "结论": "JUDGMENT",
    "方法": "METHOD", "破解": "METHOD", "解决办法": "METHOD",
    "短收尾": "SHORT_OUTRO", "收尾": "SHORT_OUTRO", "升华": "SHORT_OUTRO",
    "章节引入": "BRIDGE_IN", "承接": "BRIDGE_IN", "进入章节": "BRIDGE_IN",
    "章节钩": "BRIDGE_OUT", "章节收尾": "BRIDGE_OUT", "下章钩子": "BRIDGE_OUT",
    "评论引导": "COMMENT_CTA", "互动引导": "COMMENT_CTA",
}


@dataclass(frozen=True)
class ParsedSection:
    source_heading: str
    detected_type: str | None
    text: str
    source_start_line: int
    source_end_line: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedStructuredDocument:
    title: str
    sections: tuple[ParsedSection, ...]
    warnings: tuple[str, ...] = ()


def _normalize_heading(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip()
    value = re.sub(r"[:：]+$", "", value).strip()
    return value


def detect_block_type(heading: str) -> str | None:
    normalized = _normalize_heading(heading)
    upper = normalized.upper()
    if upper in TYPE_SLUGS:
        return upper
    return ALIASES.get(normalized)


def _section_heading(line: str) -> tuple[str, int] | None:
    match = re.match(r"^\s{0,3}(#{2,6})\s+(.+?)\s*$", line)
    if match:
        return _normalize_heading(match.group(2)), len(match.group(1))
    match = re.match(r"^\s*\[([^\]\r\n]+)\]\s*$", line)
    if match:
        return _normalize_heading(match.group(1)), 2
    return None


def parse_structured_markdown(source_text: str) -> ParsedStructuredDocument:
    if not isinstance(source_text, str) or not source_text.strip():
        raise ValueError("structured source text must not be empty")
    if len(source_text) > MAX_SOURCE_CHARS:
        raise ValueError(f"structured source text exceeds {MAX_SOURCE_CHARS} characters")
    lines = source_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    title = ""
    title_line = None
    headings: list[tuple[int, str, int]] = []
    for idx, line in enumerate(lines, 1):
        match = re.match(r"^\s{0,3}#\s+(.+?)\s*$", line)
        if match and not title:
            title = _normalize_heading(match.group(1))
            title_line = idx
            continue
        parsed = _section_heading(line)
        if parsed:
            heading, level = parsed
            headings.append((idx, heading, level))
    warnings: list[str] = []
    if not title:
        title = ""
    first_section_line = headings[0][0] if headings else None
    if first_section_line and any(line.strip() for line in lines[: first_section_line - 1]) and not title_line:
        warnings.append("unassigned_preamble")
    sections: list[ParsedSection] = []
    for position, (start, heading, _level) in enumerate(headings):
        end = headings[position + 1][0] - 1 if position + 1 < len(headings) else len(lines)
        body_lines = lines[start:end]
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)
        while body_lines and not body_lines[-1].strip():
            body_lines.pop()
        text = "\n".join(body_lines)
        section_warnings: list[str] = []
        detected = detect_block_type(heading)
        if detected is None:
            section_warnings.append("unknown_section")
            warnings.append(f"unknown_section:{heading}")
        if not text.strip():
            section_warnings.append("empty_section")
            warnings.append(f"empty_section:{heading}")
        sections.append(ParsedSection(heading, detected, text, start, end, tuple(section_warnings)))
    return ParsedStructuredDocument(title, tuple(sections), tuple(warnings))
