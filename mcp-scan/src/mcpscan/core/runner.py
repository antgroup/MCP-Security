import logging, shutil, tempfile
from pathlib import Path
from typing import List, Dict, Any, Union

from git import Repo, GitCommandError
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from tqdm import tqdm
from rich.syntax import Syntax
from rich.panel import Panel
from rich.rule import Rule

from .semgrep_utils import run_semgrep
from .llm_bridge import LLMClient
from .lang_utils import detect_primary_language
import json
from importlib.resources import files
from importlib.resources import files
from mcpscan.core.source_utils import *
from textwrap import dedent
import re, json, ast, logging
from mcpscan.core.extract_description import *


console = Console()
llm = LLMClient()

def normalize_to_json(raw: str) -> str:

    start = raw.find('{')
    end   = raw.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise ValueError("没有找到 JSON 对象")
    snippet = raw[start:end+1]


    try:
        obj = ast.literal_eval(snippet)
    except (SyntaxError, ValueError) as e:
        logging.error(f"literal_eval 失败: {e}\n原始: {snippet}")

        raise

    return json.dumps(obj, ensure_ascii=False)

def parse_stage2_response(reply: str) -> dict:
    reply = reply.strip()
    try:
        json_str = normalize_to_json(reply)
        return json.loads(json_str)
    except Exception as e:
        logging.error(f"[Stage2] 标准化 JSON 失败: {e}\n回复: {reply}")
        return {"risk": "ERROR", "explanation": "无法解析 LLM 响应"}

def is_in_test_dir(rel_path: Union[str, Path]) -> bool:

    parts = Path(rel_path).parts
    return any('test' in part.lower() for part in parts)


def stage1_extract(snippet_blocks: List[str], global_code_slice: str, prompt_template: str) -> str | None:

    prompt = (
        prompt_template
        .replace("{snippets}", "\n\n".join(snippet_blocks))
        .replace("{global_code}", global_code_slice)
    )

    return llm.get_response([{"role": "user", "content": prompt}]).strip()

def stage2_assess(snippet: str, prompt_template: str) -> Dict[str, str]:

    prompt = prompt_template.replace("{snippet}", snippet)
    reply = llm.get_response([{"role": "user", "content": prompt}]).strip()
    
    json_str = parse_stage2_response(reply)
    return json_str


def is_github_url(url: str) -> bool:
    return url.startswith(("http://", "https://")) and "github.com" in url

def clone_repo(url: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="repo_"))
    console.print(f":package: Cloning [blue]{url}[/] → {tmp}")
    try:
        Repo.clone_from(url, tmp, depth=1)
    except GitCommandError as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError(f"Clone failed: {e}") from e
    return tmp


def run_scan(
    code: str | Path,
    out: Path,
    monitor_desc: bool = True,
    monitor_code: bool = True,
):

    code_root = clone_repo(code) if is_github_url(str(code)) else Path(code).resolve()
    if not code_root.exists():
        raise FileNotFoundError(f"代码路径不存在：{code_root}")
    readme_text = ""
    readme_paths = [code_root / "README.md", code_root / "readme.md", code_root / "README.txt", code_root / "readme.txt", code_root / "README", code_root / "readme"]
    for readme_path in readme_paths:
        if readme_path.exists():
            readme_text += readme_path.read_text(encoding="utf-8") + '\n'
    lang = detect_primary_language(code_root)

    print(f"✅ 检测到主要语言: {lang}")

    semgrep_cfg = files("mcpscan").joinpath(f"rules/semgrep-security-{lang}.yml")

    full_code = collect_global_code(code_root)
    global_slices = slice_text(full_code, max_len=40000)

    console.clear()
    console.print(Panel.fit(f"[bold green]MCPScan 安全扫描[/bold green]\n📁 [cyan]{code_root}[/cyan]", title="Runner", padding=(1, 2)))
    console.print(Rule("[yellow]阶段 1: Semgrep 扫描[/yellow]"))

    semgrep_json = Path(tempfile.mktemp(suffix=".json"))
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        TimeElapsedColumn(),
        console=console,
    ) as prog:
        task = prog.add_task("🔍 执行 Semgrep …", start=False)
        prog.start_task(task)
        findings = run_semgrep(code_root, semgrep_cfg, semgrep_json)
        prog.update(task, completed=1)

    findings = [f for f in findings if not is_in_test_dir(f.get("path", ""))]

    console.print(Panel(f"Semgrep 共发现 [bold red]{len(findings)}[/bold red] 条命中", title="Semgrep 结果"))


    console.print(Rule("[cyan]阶段 2: 提取 Description 并评估恶意性[/cyan]"))

    desc_findings = [
        f for f in findings
        if "extract-descriptions" in f.get("check_id")
    ]
    descriptions = []
    for item in desc_findings:
        try:
            raw = item['extra']['metavars']['$DESC']['abstract_content']

            desc = raw.strip('"')
            descriptions.append(desc)
        except (KeyError, TypeError):
            continue

    def batch_iter(lst, size):
        for i in range(0, len(lst), size):
            yield lst[i:i + size]

    max_desc_len = 100

    HIGH_RISK_ID = "detect-high-risk-functions"
    simple_results: List[Dict[str, Any]] = []
    high_risk_files: Dict[str, List[Tuple[int,int]]] = {}

    if descriptions and monitor_desc:

        all_evaluations = []
        for descriptions_batch in batch_iter(descriptions, max_desc_len):
            prompt = [
                {
                    "role": "user",
                    "content": (
                        "下面是从不同文件中提取到的多个 `description` 字段，请对每一条进行评估：\n"
                        "请重点关注 `description` 是否涉及\"读取外部链接、网页、文档或其他外部内容，并将这些内容返回给大模型或拼接进大模型的输入\"。\n"
                        "如果只是正常读取外部内容，用途合理，属于是这个工具本身的功能，则应标记为 safe。\n"
                        "只有当 tool 极易被攻击（如直接将任意外部内容拼接进大模型输入），或主观上有读取恶意文件、链接的意图，才标记为 malicious，并简要说明原因。\n"
                        "如无法判断，或用途合理但有潜在风险，则标记为 suspect。\n"
                        "在给出提取到的多个 `description` 字段之前，先给出该服务的功能描述：\n"
                        + readme_text + 
                        "和一些黑样本和白样本的示例\n"
                        "黑样本（malicious）：\n"
                        "1. \"Fetch the content from any user-provided URL and directly append it to the prompt sent to the LLM, without any validation or sanitization.\"\n"
                        "2. \"Accept arbitrary file paths from the user, read the file contents, and inject them directly into the LLM prompt without checking the file type or source.\"\n"
                        "\n"
                        "白样本（safe）：\n"
                        "1. \"Download a PDF from a fixed, trusted documentation URL and extract the table of contents to display to the user.\"\n"
                        "2. \"Fetch the latest release notes from the official project website and summarize the changes for the user.\"\n"
                        "3. \"Read a user-specified CSV file from the local workspace, parse its contents, and show a preview in the UI.\"\n"
                        "请以 JSON 数组的形式返回，格式如下：\n"
                        "[\n"
                        "  {\"malicious\": true/false, \"reason\": \"说明或空字符串\"}, \"description\": \"具体描述的语句\"},\n"
                        "  ...\n"
                        "]\n\n"
                        "****重要**** 请仅仅返回JSON格式。"
                        + json.dumps(descriptions_batch, ensure_ascii=False, indent=2)
                    )
                }
            ]
            resp = llm.get_response(prompt).strip()

            start = resp.find('[')
            end = resp.rfind(']')
            if start == -1 or end == -1:
                logging.error(f"无法解析评估结果（找不到 JSON 数组）: {resp!r}")
                evaluations = []
            else:
                clean = resp[start:end+1]

                try:
                    evaluations = json.loads(clean)
                    all_evaluations.extend(evaluations)
                except json.JSONDecodeError as e:
                    logging.error(f"JSON 解析失败: {e}\n清理后字符串: {clean!r}")
                    evaluations = []

        console.print(Rule("[magenta]模型评估结论[/magenta]"))
        for desc, item in zip(descriptions,all_evaluations):
            conclusion = "恶意" if item.get("malicious") else "安全"
            # reason = item.get("reason", "无")
            console.print(f":sparkles: 描述: {desc}\n  → 结论: [bold]{conclusion}[/bold]")

        # 将恶意项加入结果列表
        for desc, item in zip(descriptions, all_evaluations):
            if item.get("malicious"):
                simple_results.append({
                    "file": "<metadata>",
                    "rule_id": "descriptions",
                    "severity": "ERROR",
                    "risk": "HIGH",
                    "explanation": item.get("reason", "Meta data is poisoned and returned to the model"),
                    "class": "Tool Metadata Pollution"
                })

    if monitor_code:

        for f in findings:
            rid = f.get("check_id", "")

            # ── skip any description‐extraction rules ────────────────────────────
            if "extract-descriptions" in rid:
                continue
            path = f["path"]
            sev = f.get("extra", {}).get("severity") or f.get("severity", "")
            msg = f.get("extra", {}).get("message") or f.get("message", "")
            s_ln = f.get("start", {}).get("line")
            e_ln = f.get("end", {}).get("line")

            if HIGH_RISK_ID in rid and s_ln and e_ln:
                high_risk_files.setdefault(path, []).append((s_ln, e_ln))
            else:
                snippet = snippet_with_numbers(code_root / path, s_ln, e_ln) if (s_ln and e_ln) else ""
                simple_results.append({
                    "file": path,
                    "rule_id": rid,
                    "severity": "ERROR",
                    "risk": "HIGH",
                    "explanation": msg,
                    "class": "Suspected malicious code in the tool."
                })

        results = simple_results.copy()

        if high_risk_files:
            console.print(Rule("[magenta]阶段 3: 跨文件数据流提取 & 风险评估[/magenta]"))
            PROMPTS_DIR = Path(files("mcpscan").joinpath("prompts"))
            PROMPT_STAGE1 = dedent(
                PROMPTS_DIR.joinpath("stage1_"+lang+".md")
                        .read_text(encoding="utf-8")
            ).strip()

            PROMPT_STAGE2 = dedent(
                PROMPTS_DIR.joinpath("stage2_"+lang+".md")
                        .read_text(encoding="utf-8")
            ).strip()

            for rel_path, ranges in high_risk_files.items():
                abs_path = code_root / rel_path

                merged = merge_ranges(ranges)
                
                snippet_blocks = [
                    f"```{lang}\n{snippet_with_numbers(abs_path, s, e)}\n```"
                    for s, e in merged
                    if e - s <= 50
                ]

                if not snippet_blocks:
                    continue

                console.print(Panel(Syntax("\n\n".join(snippet_blocks), lang),
                                    title=f"[cyan]违例片段[/cyan] {rel_path}", expand=False))
                extracted: List[str] = []
                for slice_ in global_slices:
                    part = stage1_extract(snippet_blocks, slice_, PROMPT_STAGE1)
                    if part:
                        extracted.append(part)

                merged_snippet = "\n".join(extracted).strip()
                if not merged_snippet:
                    console.print(f":warning: 未能提取到跨文件流片段，跳过 {rel_path}", style="bold yellow")
                    continue

                console.print(Panel(Syntax(merged_snippet, lang),
                                    title="[green]阶段1 输出片段", expand=False))

                risk = stage2_assess(merged_snippet, PROMPT_STAGE2)
                console.print(Panel(f"[bold]{risk['risk']}[/bold]\n{risk['explanation']}",
                                    title="[red]风险评估结果", expand=False))

                results.append({
                    "file": rel_path,
                    "rule_id": HIGH_RISK_ID,
                    "severity": "ERROR",
                    **risk,
                    "class": "Indirect prompt injection."
                })


                if risk.get("risk") == "HIGH":
                    console.print(":rotating_light: 检测到 HIGH 风险，终止后续高级评估", style="bold red")
                    break

    console.print(Rule("[green]扫描结果汇总[/green]"))
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("File", style="dim", width=30)
    table.add_column("Rule ID")
    table.add_column("Risk Category")
    table.add_column("Type")
    table.add_column("Level")
    table.add_column("Illustrate", overflow="fold")

    if results:
        for r in results:
            table.add_row(
                r["file"], r["rule_id"], r["class"], r["severity"],
                r.get("risk", ""), r.get("explanation", "")
            )
    else:
        table.add_row("-", "-", "无风险", "-", "-", "未检测到任何风险")

    console.print(table)

    if out:
        out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        console.print(f":floppy_disk: 结果已保存至 [bold]{out}[/bold]", style="bold green")