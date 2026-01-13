"""
交互式菜单模块

提供完整的交互式用户界面，包括:
- 主菜单
- 领域选择
- 策略多选
- 子类别选择
- 配置确认
"""

from typing import List, Optional, Dict, Any
import sys
import json
import os

try:
    import questionary
    from questionary import Style
    QUESTIONARY_AVAILABLE = True
except ImportError:
    QUESTIONARY_AVAILABLE = False

from .output import ScannerOutput


# 自定义questionary样式
MENU_STYLE = Style([
    ('qmark', 'fg:cyan bold'),
    ('question', 'bold'),
    ('answer', 'fg:green bold'),
    ('pointer', 'fg:cyan bold'),
    ('highlighted', 'fg:cyan bold'),
    ('selected', 'fg:green'),
    ('separator', 'fg:gray'),
    ('instruction', 'fg:gray'),
]) if QUESTIONARY_AVAILABLE else None


class InteractiveMenu:
    """
    交互式菜单控制器

    使用方式:
        menu = InteractiveMenu()
        menu.show_welcome()

        action = menu.main_menu()
        if action == "scan":
            config = menu.gather_scan_config()
            if menu.confirm_config(config):
                # 执行扫描
    """

    def __init__(self, output: ScannerOutput = None):
        """
        初始化菜单

        Args:
            output: ScannerOutput实例，用于格式化输出
        """
        self.output = output or ScannerOutput()
        self.is_interactive = QUESTIONARY_AVAILABLE and sys.stdin.isatty()

    def show_welcome(self, version: str = "2.2"):
        """显示欢迎界面"""
        self.output.welcome(version)

    def main_menu(self) -> str:
        """
        显示主菜单

        Returns:
            选择的操作: "scan", "config", "history", "help", "exit"
        """
        if not self.is_interactive:
            return "scan"  # 非交互模式默认扫描

        choices = [
            questionary.Choice("开始扫描", value="scan"),
            questionary.Choice("配置设置", value="config"),
            questionary.Choice("查看历史", value="history"),
            questionary.Choice("帮助文档", value="help"),
            questionary.Separator(),
            questionary.Choice("退出", value="exit"),
        ]

        result = questionary.select(
            "请选择操作:",
            choices=choices,
            style=MENU_STYLE,
            use_shortcuts=True
        ).ask()

        return result or "exit"

    def select_domain(self) -> str:
        """
        选择扫描领域

        Returns:
            领域名称: "crypto", "sports", "politics", "other"
        """
        if not self.is_interactive:
            return "crypto"

        domains = [
            questionary.Choice(
                title="加密货币 (推荐) - 规则清晰，流动性好",
                value="crypto"
            ),
            questionary.Choice(
                title="体育赛事 - 规则较标准",
                value="sports"
            ),
            questionary.Choice(
                title="政治选举 - 风险较高，需人工验证",
                value="politics"
            ),
            questionary.Choice(
                title="其他市场",
                value="other"
            ),
        ]

        result = questionary.select(
            "选择扫描领域:",
            choices=domains,
            style=MENU_STYLE
        ).ask()

        return result or "crypto"

    def select_strategies(self, domain: str) -> List[str]:
        """
        多选套利策略

        Args:
            domain: 当前选择的领域

        Returns:
            选中的策略ID列表
        """
        # 延迟导入避免循环依赖
        try:
            from strategies import StrategyRegistry
            available = StrategyRegistry.get_for_domain(domain)
        except ImportError:
            # 注册表尚未加载，使用硬编码列表
            available = self._get_default_strategies(domain)

        if not self.is_interactive:
            # 非交互模式返回所有可用策略
            return [m.id if hasattr(m, 'id') else m['id'] for m in available]

        # 构建选项
        choices = []
        for meta in available:
            # 兼容dict和StrategyMetadata
            if hasattr(meta, 'id'):
                meta_id = meta.id
                meta_name = meta.name
                meta_name_en = meta.name_en
                meta_description = meta.description
                meta_risk = meta.risk_level.value if hasattr(meta.risk_level, 'value') else meta.risk_level
                meta_priority = meta.priority
            else:
                meta_id = meta['id']
                meta_name = meta['name']
                meta_name_en = meta['name_en']
                meta_description = meta['description']
                meta_risk = meta['risk_level']
                meta_priority = meta['priority']

            label = f"{meta_name} ({meta_name_en})"
            hint = f"[{meta_risk.upper()}] {meta_description}"

            choices.append(questionary.Choice(
                title=f"{label}\n    {hint}",
                value=meta_id,
                checked=(meta_priority <= 3)  # 高优先级默认选中
            ))

        selected = questionary.checkbox(
            "选择套利策略 (空格选择，回车确认):",
            choices=choices,
            style=MENU_STYLE,
            validate=lambda x: len(x) > 0 or "请至少选择一个策略"
        ).ask()

        return selected or []

    def _get_default_strategies(self, domain: str) -> List[Dict]:
        """获取默认策略列表（当注册表不可用时）"""
        all_strategies = [
            {
                'id': 'monotonicity',
                'name': '单调性违背套利',
                'name_en': 'Monotonicity Violation',
                'description': '检测阈值市场的价格倒挂',
                'risk_level': 'low',
                'priority': 1,
                'domains': ['crypto']
            },
            {
                'id': 'interval',
                'name': '区间套利',
                'name_en': 'Interval Arbitrage',
                'description': '区间覆盖关系套利',
                'risk_level': 'low',
                'priority': 2,
                'domains': ['crypto', 'all']
            },
            {
                'id': 'exhaustive',
                'name': '完备集套利',
                'name_en': 'Exhaustive Set',
                'description': '互斥完备集定价不足',
                'risk_level': 'medium',
                'priority': 3,
                'domains': ['all']
            },
            {
                'id': 'implication',
                'name': '蕴含关系套利',
                'name_en': 'Implication Violation',
                'description': 'A -> B 价格违背',
                'risk_level': 'medium',
                'priority': 4,
                'domains': ['all']
            },
            {
                'id': 'equivalent',
                'name': '等价市场套利',
                'name_en': 'Equivalent Markets',
                'description': '同事件不同表述',
                'risk_level': 'medium',
                'priority': 5,
                'domains': ['all']
            },
        ]

        return [
            s for s in all_strategies
            if 'all' in s['domains'] or domain in s['domains']
        ]

    def select_subcategories(self, domain: str) -> Optional[List[str]]:
        """
        选择子类别

        Args:
            domain: 当前领域

        Returns:
            子类别列表，None表示全部
        """
        # 尝试加载子类别配置
        subcats = self._load_subcategories(domain)

        if not subcats:
            return None

        if not self.is_interactive:
            return None  # 非交互模式默认全部

        # 按类别分组显示
        choices = [questionary.Choice("全部", value="__ALL__", checked=True)]

        for cat_name, cat_items in subcats.items():
            choices.append(questionary.Separator(f"── {cat_name} ──"))
            for item in cat_items:
                if isinstance(item, dict):
                    choices.append(questionary.Choice(
                        title=f"{item['name']} ({item.get('slug', '')})",
                        value=item.get('slug', item['name'])
                    ))
                else:
                    choices.append(questionary.Choice(title=item, value=item))

        selected = questionary.checkbox(
            "选择子类别 (留空或选择'全部'=所有子类别):",
            choices=choices,
            style=MENU_STYLE
        ).ask()

        if not selected or "__ALL__" in selected:
            return None

        return selected

    def _load_subcategories(self, domain: str) -> Dict[str, List]:
        """加载子类别配置"""
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'tag_categories.json'
        )

        if not os.path.exists(config_path):
            return {}

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                all_cats = json.load(f)
            return all_cats.get(domain, {})
        except Exception:
            return {}

    def select_run_mode(self) -> str:
        """
        选择运行模式

        Returns:
            "debug" 或 "production"
        """
        if not self.is_interactive:
            return "production"

        choices = [
            questionary.Choice(
                "PRODUCTION - 自动保存，无人值守 (推荐)",
                value="production"
            ),
            questionary.Choice(
                "DEBUG - 逐个确认，适合调试",
                value="debug"
            ),
        ]

        result = questionary.select(
            "选择运行模式:",
            choices=choices,
            style=MENU_STYLE
        ).ask()

        return result or "production"

    def select_cache_option(self) -> bool:
        """
        选择缓存选项

        Returns:
            True表示强制刷新，False表示使用缓存
        """
        if not self.is_interactive:
            return False

        choices = [
            questionary.Choice("使用缓存 (推荐)", value=False),
            questionary.Choice("刷新数据", value=True),
        ]

        result = questionary.select(
            "使用缓存还是刷新数据?",
            choices=choices,
            style=MENU_STYLE
        ).ask()

        return result if result is not None else False

    def confirm_config(self, config: Dict[str, Any]) -> bool:
        """
        显示配置并确认

        Args:
            config: 配置字典

        Returns:
            是否确认
        """
        self.output.print_config_table(config)

        if not self.is_interactive:
            return True

        return questionary.confirm(
            "确认开始扫描?",
            default=True,
            style=MENU_STYLE
        ).ask() or False

    def gather_scan_config(self) -> Dict[str, Any]:
        """
        收集完整的扫描配置

        Returns:
            配置字典
        """
        config = {}

        # 1. 选择领域
        config['domain'] = self.select_domain()

        # 2. 选择策略
        config['strategies'] = self.select_strategies(config['domain'])

        # 3. 选择子类别
        config['subcategories'] = self.select_subcategories(config['domain'])

        # 4. 选择运行模式
        config['mode'] = self.select_run_mode()

        # 5. 选择缓存选项
        config['force_refresh'] = self.select_cache_option()

        return config

    def ask_continue(self, prompt: str = "继续?") -> bool:
        """询问是否继续"""
        if not self.is_interactive:
            return True
        return questionary.confirm(prompt, default=True, style=MENU_STYLE).ask() or False

    def ask_input(self, prompt: str, default: str = "") -> str:
        """获取文本输入"""
        if not self.is_interactive:
            return default
        return questionary.text(prompt, default=default, style=MENU_STYLE).ask() or default

    def show_help(self):
        """显示帮助信息"""
        help_text = """
Polymarket 组合套利扫描系统 - 帮助

== 快速开始 ==
1. 选择"开始扫描"进入扫描流程
2. 选择领域（推荐：加密货币）
3. 选择套利策略（可多选）
4. 选择子类别（可选）
5. 确认配置后开始扫描

== 套利策略说明 ==
- 单调性违背: 检测阈值市场价格倒挂（如 BTC>100k > BTC>95k）
- 区间套利: 区间覆盖关系套利
- 完备集套利: 互斥完备集价格总和 < 1
- 蕴含关系套利: A->B 但 P(B) < P(A)
- 等价市场套利: 同事件不同表述有价差

== 命令行模式 ==
使用 --no-interactive 可跳过交互式菜单
示例: python local_scanner_v2.py --no-interactive --domain crypto

== 更多信息 ==
项目文档: docs/PROJECT_BIBLE.md
工作计划: docs/WORK_PLAN.md
"""
        print(help_text)
        if self.is_interactive:
            questionary.press_any_key_to_continue("按任意键返回...").ask()
