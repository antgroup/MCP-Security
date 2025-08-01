from pathlib import Path
import typer
from rich.console import Console
from rich.panel import Panel

from mcpscan import __version__, BANNER
from mcpscan.core.runner import run_scan

app = typer.Typer(add_completion=False, rich_markup_mode="rich")
console = Console()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit")
):
    """
    🛰️  MCP 两阶段安全扫描器
    """
    if version:
        console.print(f"[bold cyan]mcpscan[/] {__version__}")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        console.print(Panel.fit(BANNER, style="bold magenta"))
        console.print("[bold]Try[/]: mcpscan scan --help")
        raise typer.Exit()


@app.command()
def scan(
    code: str = typer.Argument(..., help="本地路径或 GitHub URL"),
    out: Path = typer.Option(
        "triage_report.json", "--out", "-o", help="输出结果文件（JSON）"
    ),
    save: bool = typer.Option(
        False,
        "--save/--no-save",
        help="是否将扫描结果保存到文件（默认保存）"
    ),
    monitor_desc: bool = typer.Option(
        True,
        "--monitor-desc/--no-monitor-desc",
        help="是否执行 metadata 描述字段的安全监测（默认开启）"
    ),
    monitor_code: bool = typer.Option(
        True,
        "--monitor-code/--no-monitor-code",
        help="是否执行代码层面风险扫描与跨文件流提取（默认开启）"
    ),
):
    """
    🚀  对目标仓库执行 Semgrep + LLM 两阶段安全扫描

    支持按需开启/关闭 metadata 描述监测、代码风险监测，以及选择是否保存运行结果。
    """
    output_path = out if save else None
    run_scan(
        code,
        output_path,
        monitor_desc=monitor_desc,
        monitor_code=monitor_code,
    )


@app.command()
def rules():
    """打印内置 Semgrep 规则集所在目录（可复制后自定义）"""
    from importlib.resources import files

    console.print(str(files("mcpscan") / "rules"), style="green")


if __name__ == "__main__":
    app()
