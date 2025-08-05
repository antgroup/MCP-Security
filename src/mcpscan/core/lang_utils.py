# src/mcpscan/core/lang_utils.py
from pathlib import Path

JS_EXTS = {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"}
PY_EXTS = {".py"}


def detect_primary_language(root: Path) -> str:

    js_cnt = py_cnt = 0
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix in JS_EXTS:
            js_cnt += 1
        elif f.suffix in PY_EXTS:
            py_cnt += 1
    return "js" if js_cnt >= py_cnt else "py"
