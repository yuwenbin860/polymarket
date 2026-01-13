"""
输出格式化模块

提供统一的控制台输出格式，包括:
- 欢迎界面
- 进度显示
- 套利机会展示
- 扫描摘要
"""

from contextlib import contextmanager
from typing import List, Optional, Generator, Any
from dataclasses import dataclass
import sys

try:
    from rich.console import Console
    from rich.progress import (
        Progress, SpinnerColumn, TextColumn,
        BarColumn, TaskProgressColumn, TimeElapsedColumn
    )
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.live import Live
    from rich.style import Style
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


# 颜色和样式定义
STYLES = {
    'success': 'green',
    'warning': 'yellow',
    'error': 'red',
    'info': 'cyan',
    'highlight': 'bold magenta',
    'dim': 'dim',
    'profit_high': 'bold green',
    'profit_medium': 'green',
    'profit_low': 'yellow',
}


class ScannerOutput:
    """
    统一的扫描器输出格式化类

    使用方式:
        output = ScannerOutput()
        output.welcome("v2.2")

        with output.scan_progress(total_steps=4) as progress:
            progress.advance("获取市场数据...")
            # ... 执行操作
            progress.advance("分析逻辑关系...")

        output.print_opportunity(opp, index=1)
        output.print_summary(opportunities, elapsed_time=12.3)
    """

    def __init__(self, force_simple: bool = False):
        """
        初始化输出器

        Args:
            force_simple: 强制使用简单输出（不使用Rich）
        """
        self.use_rich = RICH_AVAILABLE and not force_simple and sys.stdout.isatty()
        if self.use_rich:
            self.console = Console()
        else:
            self.console = None

    def _print(self, message: str, style: str = None):
        """内部打印方法"""
        if self.use_rich and self.console:
            if style:
                self.console.print(message, style=style)
            else:
                self.console.print(message)
        else:
            print(message)

    def welcome(self, version: str = "2.2"):
        """显示欢迎界面"""
        if self.use_rich:
            panel = Panel.fit(
                f"[bold cyan]Polymarket 组合套利扫描系统[/bold cyan]\n"
                f"[dim]v{version} - 交互式版本[/dim]",
                border_style="cyan",
                padding=(1, 4)
            )
            self.console.print(panel)
            self.console.print()
        else:
            print("=" * 50)
            print(f"  Polymarket 组合套利扫描系统 v{version}")
            print("=" * 50)
            print()

    def print_step(self, step: int, total: int, description: str):
        """打印步骤标题"""
        if self.use_rich:
            self.console.print(f"\n[bold cyan][{step}/{total}][/] {description}")
        else:
            print(f"\n[{step}/{total}] {description}")

    def print_market_fetch(self, count: int, domain: str, subcats: List[str] = None):
        """打印市场获取结果"""
        subcat_info = f" ({', '.join(subcats)})" if subcats else ""
        if self.use_rich:
            self.console.print(
                f"  [green]OK[/] 获取到 [bold]{count}[/] 个 {domain}{subcat_info} 市场"
            )
        else:
            print(f"  OK: 获取到 {count} 个 {domain}{subcat_info} 市场")

    def print_strategy_start(self, strategy_name: str):
        """打印策略开始执行"""
        if self.use_rich:
            self.console.print(f"  [cyan]▶[/] 执行 [bold]{strategy_name}[/]...")
        else:
            print(f"  > 执行 {strategy_name}...")

    def print_strategy_result(self, strategy_name: str, count: int):
        """打印策略执行结果"""
        if count > 0:
            if self.use_rich:
                self.console.print(f"    [green]✓[/] 发现 [bold green]{count}[/] 个机会")
            else:
                print(f"    ✓ 发现 {count} 个机会")
        else:
            if self.use_rich:
                self.console.print(f"    [dim]○ 未发现机会[/]")
            else:
                print(f"    ○ 未发现机会")

    def print_opportunity(self, opp: Any, index: int = None):
        """
        打印单个套利机会

        Args:
            opp: ArbitrageOpportunity 对象
            index: 序号
        """
        idx_str = f"#{index} " if index else ""

        # 根据利润率选择样式
        if opp.profit_pct >= 5:
            profit_style = STYLES['profit_high']
            border_style = "green"
        elif opp.profit_pct >= 2:
            profit_style = STYLES['profit_medium']
            border_style = "yellow"
        else:
            profit_style = STYLES['profit_low']
            border_style = "dim"

        if self.use_rich:
            # 构建内容
            content = Text()
            content.append(f"{opp.type}\n\n", style="bold")
            content.append("利润: ", style="dim")
            content.append(f"{opp.profit_pct:.2f}%\n", style=profit_style)
            content.append("成本: ", style="dim")
            content.append(f"${opp.total_cost:.4f}\n", style="white")
            content.append("回报: ", style="dim")
            content.append(f"${opp.guaranteed_return:.4f}\n\n", style="white")

            if hasattr(opp, 'reasoning') and opp.reasoning:
                # 截取推理的前100个字符
                reasoning_short = opp.reasoning[:100] + "..." if len(opp.reasoning) > 100 else opp.reasoning
                content.append(reasoning_short, style="dim italic")

            panel = Panel(
                content,
                title=f"{idx_str}套利机会",
                border_style=border_style,
                padding=(0, 1)
            )
            self.console.print(panel)
        else:
            print(f"\n{'─' * 50}")
            print(f"{idx_str}套利机会: {opp.type}")
            print(f"利润: {opp.profit_pct:.2f}%")
            print(f"成本: ${opp.total_cost:.4f}")
            print(f"回报: ${opp.guaranteed_return:.4f}")
            print(f"{'─' * 50}")

    def print_summary(self, opportunities: List[Any], elapsed_time: float):
        """
        打印扫描摘要

        Args:
            opportunities: 套利机会列表
            elapsed_time: 耗时（秒）
        """
        if self.use_rich:
            table = Table(title="扫描结果摘要", show_header=True)
            table.add_column("指标", style="cyan", width=15)
            table.add_column("值", style="green", width=25)

            table.add_row("发现机会", str(len(opportunities)))
            table.add_row("扫描耗时", f"{elapsed_time:.1f}秒")

            if opportunities:
                profits = [o.profit_pct for o in opportunities]
                avg_profit = sum(profits) / len(profits)
                max_profit = max(profits)
                table.add_row("平均利润", f"{avg_profit:.2f}%")
                table.add_row("最大利润", f"{max_profit:.2f}%")

            self.console.print()
            self.console.print(table)
        else:
            print("\n" + "=" * 40)
            print("扫描结果摘要")
            print("=" * 40)
            print(f"发现机会: {len(opportunities)}")
            print(f"扫描耗时: {elapsed_time:.1f}秒")
            if opportunities:
                profits = [o.profit_pct for o in opportunities]
                print(f"平均利润: {sum(profits)/len(profits):.2f}%")
                print(f"最大利润: {max(profits):.2f}%")
            print("=" * 40)

    def print_error(self, message: str, exception: Exception = None):
        """打印错误信息"""
        if self.use_rich:
            self.console.print(f"[bold red]错误:[/] {message}")
            if exception:
                self.console.print(f"[dim]{type(exception).__name__}: {exception}[/]")
        else:
            print(f"错误: {message}")
            if exception:
                print(f"  {type(exception).__name__}: {exception}")

    def print_warning(self, message: str):
        """打印警告信息"""
        if self.use_rich:
            self.console.print(f"[yellow]警告:[/] {message}")
        else:
            print(f"警告: {message}")

    def print_info(self, message: str):
        """打印信息"""
        if self.use_rich:
            self.console.print(f"[cyan]ℹ[/] {message}")
        else:
            print(f"[INFO] {message}")

    def print_config_table(self, config: dict):
        """打印配置确认表格"""
        if self.use_rich:
            table = Table(title="扫描配置确认", show_header=True)
            table.add_column("参数", style="cyan", width=12)
            table.add_column("值", style="green")

            table.add_row("领域", config.get("domain", "-"))
            strategies = config.get("strategies", [])
            table.add_row("策略", ", ".join(strategies) if strategies else "全部")
            subcats = config.get("subcategories", [])
            table.add_row("子类别", ", ".join(subcats) if subcats else "全部")
            table.add_row("运行模式", config.get("mode", "production"))
            table.add_row("缓存", "刷新" if config.get("force_refresh") else "使用缓存")

            self.console.print()
            self.console.print(table)
        else:
            print("\n配置确认:")
            print(f"  领域: {config.get('domain', '-')}")
            print(f"  策略: {', '.join(config.get('strategies', ['全部']))}")
            print(f"  子类别: {', '.join(config.get('subcategories', ['全部']))}")
            print(f"  运行模式: {config.get('mode', 'production')}")
            print(f"  缓存: {'刷新' if config.get('force_refresh') else '使用缓存'}")

    def print_report_saved(self, filepath: str):
        """打印报告保存信息"""
        if self.use_rich:
            self.console.print(f"[green]✓[/] 报告已保存: [dim]{filepath}[/]")
        else:
            print(f"✓ 报告已保存: {filepath}")

    @contextmanager
    def scan_progress(self, total_steps: int = 5) -> Generator['ScanProgressContext', None, None]:
        """
        扫描进度上下文管理器

        使用方式:
            with output.scan_progress(total_steps=4) as progress:
                progress.advance("获取市场数据...")
                # ...
                progress.advance("分析逻辑关系...")
        """
        if self.use_rich:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                console=self.console,
                transient=False
            ) as progress:
                task = progress.add_task("初始化...", total=total_steps)
                yield ScanProgressContext(progress, task, self.console)
        else:
            yield SimpleProgressContext(total_steps)


class ScanProgressContext:
    """Rich进度上下文"""

    def __init__(self, progress: 'Progress', task_id: int, console: 'Console'):
        self.progress = progress
        self.task_id = task_id
        self.console = console
        self.current_step = 0

    def advance(self, description: str):
        """推进到下一步"""
        self.current_step += 1
        self.progress.update(self.task_id, advance=1, description=description)

    def update(self, description: str):
        """更新描述但不推进"""
        self.progress.update(self.task_id, description=description)

    def print(self, message: str, style: str = None):
        """在进度条下方打印消息"""
        if style:
            self.console.print(message, style=style)
        else:
            self.console.print(message)


class SimpleProgressContext:
    """简单进度上下文（无Rich时使用）"""

    def __init__(self, total_steps: int):
        self.total_steps = total_steps
        self.current_step = 0

    def advance(self, description: str):
        """推进到下一步"""
        self.current_step += 1
        print(f"[{self.current_step}/{self.total_steps}] {description}")

    def update(self, description: str):
        """更新描述"""
        print(f"  > {description}")

    def print(self, message: str, style: str = None):
        """打印消息"""
        print(message)
