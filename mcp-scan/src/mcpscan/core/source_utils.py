from typing import Any, Dict, List, Tuple
import logging
from pathlib import Path
import re

def extract_code_blocks(markdown_text: str, lang: str | None = None) -> List[str]:
    fence_lang = lang if lang is not None else r"\w*"
    pattern = rf"```{fence_lang}\n(.*?)```"
    code_blocks = re.findall(pattern, markdown_text, flags=re.DOTALL | re.IGNORECASE)
    return [block.strip() for block in code_blocks]

def slice_text(text: str, max_len: int = 5000) -> List[str]:
    if len(text) <= max_len:
        return [text]

    parts, buf = [], []
    buf_len = 0
    for line in text.splitlines(keepends=True):
        if buf_len + len(line) > max_len:
            parts.append("".join(buf))
            buf, buf_len = [], 0
        buf.append(line)
        buf_len += len(line)
    if buf:
        parts.append("".join(buf))
    return parts

def numbered(src: str) -> str:
    return "\n".join(f"{i+1:>5}| {line}" for i, line in enumerate(src.splitlines()))

def snippet_with_numbers(fp: Path, start: int, end: int) -> str:
    try:
        lines = fp.read_text(encoding="utf-8", errors="ignore").splitlines()
        return "\n".join(
            f"{i+1:>5}| {lines[i]}" for i in range(start - 1, min(end, len(lines)))
        )
    except Exception as exc:
        logging.error(f"读取代码片段失败 {fp}:{start}-{end} — {exc}")
        return ""

def merge_ranges(ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    if not ranges:
        return []
    ranges.sort()
    merged = [ranges[0]]
    for s, e in ranges[1:]:
        ls, le = merged[-1]
        if s <= le + 1:
            merged[-1] = (ls, max(le, e))
        else:
            merged.append((s, e))
    return merged

def collect_global_code(root: Path) -> str:
    exts = {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".py"}
    parts: List[str] = []
    for f in sorted(root.rglob("*")):
        if f.is_file() and f.suffix in exts:
            try:
                parts.append(
                    f"// ===== {f.relative_to(root)} =====\n"
                    f"```\n{numbered(f.read_text(encoding='utf-8', errors='ignore'))}\n```"
                )
            except Exception as exc:
                logging.warning(f"读取文件失败：{f} — {exc}")
    return "\n\n".join(parts)