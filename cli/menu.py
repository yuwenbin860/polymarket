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


# 导入场景常量
try:
    from llm_config import LLMScenario
except ImportError:
    # 如果llm_config不可用，使用简单的字符串常量
    class LLMScenario:
        TAG_CLASSIFICATION = "tag_classification"
        STRATEGY_SCAN = "strategy_scan"


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

        # 保存当前会话中选择的LLM配置
        self.current_llm_profile = None
        self.current_llm_model = None

    def show_llm_confirmation_prompt(self, config) -> Optional[Dict[str, str]]:
        """
        显示当前配置的LLM并提供快速切换选项

        在程序启动时调用，让用户确认或切换LLM配置。

        Args:
            config: AppConfig对象，包含active_profile等配置

        Returns:
            None: 继续使用配置文件中的LLM
            Dict: 用户选择的新LLM配置 {"profile": "xxx", "model": "xxx"}
        """
        from llm_config import LLMConfigManager
        from llm_providers import get_model_icon

        manager = LLMConfigManager()

        # 获取active_profile
        active_profile_name = getattr(config, 'active_profile', None)
        if not active_profile_name:
            # 没有配置active_profile，尝试自动检测
            active_profile = manager.get_active_profile()
            if not active_profile:
                self.output.print_error("未检测到任何已配置的LLM")
                self.output.print_info("请先配置LLM API Key")
                return self.select_llm_profile()
            active_profile_name = active_profile.name
        else:
            active_profile = manager.get_profile(active_profile_name)

        if not active_profile:
            self.output.print_error(f"配置文件中的active_profile '{active_profile_name}' 不存在")
            return self.select_llm_profile()

        # 检查API Key是否配置
        if not active_profile.is_configured():
            self.output.print_warning(f"LLM配置 '{active_profile_name}' 未设置API Key")
            self.output.print_info(f"请设置环境变量: {active_profile.api_key_env}")
            return self.select_llm_profile()

        # 显示当前配置
        if self.output.use_rich:
            from rich.panel import Panel
            icon = get_model_icon(active_profile.model)

            # 检查是否有场景化模型配置
            scenario_info = ""
            if active_profile.scenario_models:
                tag_model = active_profile.scenario_models.get("tag_classification", active_profile.model)
                scan_model = active_profile.scenario_models.get("strategy_scan", active_profile.model)
                if tag_model != active_profile.model or scan_model != active_profile.model:
                    scenario_info = f"\n[dim]  • Tag分类: {tag_model.split('/')[-1]}\n  • 策略扫描: {scan_model.split('/')[-1]}[/dim]"

            panel = Panel.fit(
                f"[bold cyan]系统LLM配置[/bold cyan]  [dim](config.json)[/dim]\n\n"
                f"{icon} [bold]{active_profile.name}[/bold]: {active_profile.model.split('/')[-1]}\n"
                f"[dim]{active_profile.description}[/dim]"
                f"{scenario_info}",
                border_style="cyan",
                padding=(0, 2)
            )
            self.output.console.print(panel)
        else:
            print(f"\n当前LLM配置: {active_profile.name}")
            print(f"  模型: {active_profile.model}")
            print(f"  描述: {active_profile.description}")

        # 非交互模式直接使用配置
        if not self.is_interactive:
            self.current_llm_profile = active_profile_name
            self.current_llm_model = active_profile.model
            return None

        # 询问是否切换
        choices = [
            questionary.Choice("继续使用此配置", value="continue"),
            questionary.Choice("切换到其他LLM配置", value="change"),
        ]

        action = questionary.select(
            "请选择操作:",
            choices=choices,
            style=MENU_STYLE
        ).ask()

        if action == "change":
            return self.select_llm_profile()
        else:
            # 继续使用配置文件中的LLM，保存到实例变量
            self.current_llm_profile = active_profile_name
            self.current_llm_model = active_profile.model
            return None

    def show_welcome(self, version: str = "2.2"):
        """显示欢迎界面"""
        self.output.welcome(version)

    def display_current_llm_config(self) -> None:
        """
        显示当前会话的LLM配置信息

        在交互模式启动时调用，让用户清楚当前使用的LLM模型。
        """
        if not self.is_interactive:
            return

        from llm_config import LLMConfigManager
        from llm_providers import get_model_icon

        manager = LLMConfigManager()

        # 获取当前LLM配置
        if self.current_llm_profile:
            # 使用会话中选择的配置
            profile = manager.get_profile(self.current_llm_profile)
        else:
            # 使用默认配置（从config.json读取）
            try:
                from config import Config as AppConfig
                config = AppConfig.load()
                active_profile_name = getattr(config, 'active_profile', None)
                if active_profile_name:
                    profile = manager.get_profile(active_profile_name)
                else:
                    profile = manager.get_active_profile()
            except:
                profile = manager.get_active_profile()

        if not profile:
            self.output.print_warning("未检测到LLM配置")
            return

        # 显示Panel
        if self.output.use_rich:
            from rich.panel import Panel
            icon = get_model_icon(profile.model)

            # 构建场景模型信息
            scenario_info = ""
            if profile.scenario_models:
                tag_model = profile.scenario_models.get("tag_classification", profile.model)
                scan_model = profile.scenario_models.get("strategy_scan", profile.model)
                if tag_model != profile.model or scan_model != profile.model:
                    scenario_info = (
                        f"\n\n[dim]场景化模型配置：\n"
                        f"  • Tag分类: {tag_model.split('/')[-1]}\n"
                        f"  • 策略扫描: {scan_model.split('/')[-1]}[/dim]"
                    )

            panel = Panel.fit(
                f"[bold cyan]当前LLM配置[/bold cyan]\n\n"
                f"{icon} [bold]{profile.name}[/bold]\n"
                f"[dim]模型: {profile.model}[/dim]"
                f"{scenario_info}",
                border_style="cyan",
                padding=(0, 2)
            )
            self.output.console.print(panel)
            print()  # 添加空行
        else:
            print(f"\n当前LLM配置: {profile.name}")
            print(f"  模型: {profile.model}")
            print()

    def main_menu(self) -> str:
        """
        显示主菜单

        Returns:
            选择的操作: "scan", "llm_config", "config", "history", "classify_tags", "help", "exit"
        """
        if not self.is_interactive:
            return "scan"  # 非交互模式默认扫描

        choices = [
            questionary.Choice("开始扫描", value="scan"),
            questionary.Choice("LLM配置", value="llm_config"),
            questionary.Choice("配置设置", value="config"),
            questionary.Choice("Tags智能分类", value="classify_tags"),
            questionary.Choice("历史回测", value="backtest"),
            questionary.Choice("灵敏度分析", value="sensitivity_analysis"),
            questionary.Choice("同步结算状态", value="sync_settlements"),
            questionary.Choice("收益统计 (PnL)", value="stats"),
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

    def select_llm_profile(self) -> Dict[str, str]:
        """
        选择LLM配置和模型

        Returns:
            包含profile和model选择的字典，如 {"profile": "siliconflow", "model": "xxx"}
        """
        if not self.is_interactive:
            return {}

        from llm_config import LLMConfigManager
        from llm_providers import is_reasoning_model, get_model_icon

        manager = LLMConfigManager()
        configured = manager.get_configured_profiles()

        if not configured:
            self.output.print_error("未检测到任何已配置的LLM API Key")
            self.output.print_info("请设置以下环境变量之一：")
            self.output.print_info("  - SILICONFLOW_API_KEY (推荐)")
            self.output.print_info("  - DEEPSEEK_API_KEY")
            self.output.print_info("  - MODELSCOPE_API_KEY")
            self.output.print_info("  - OPENAI_API_KEY")
            return {}

        # 1. 选择Provider/Profile
        choices = []
        for p in configured:
            icon = get_model_icon(p.model)
            desc = p.description or p.name
            # 显示场景模型配置提示
            scenario_hint = ""
            if p.scenario_models:
                if LLMScenario.TAG_CLASSIFICATION in p.scenario_models:
                    tag_model = p.scenario_models[LLMScenario.TAG_CLASSIFICATION]
                    if tag_model != p.model:
                        scenario_hint = f" [Tag: {tag_model.split('/')[-1]}]"

            choices.append(questionary.Choice(
                title=f"{icon} {p.name}: {p.model.split('/')[-1]}{scenario_hint}",
                value=p.name,
                description=desc
            ))

        profile_name = questionary.select(
            "选择LLM配置:",
            choices=choices,
            style=MENU_STYLE,
            use_shortcuts=True
        ).ask()

        if not profile_name:
            return {}

        profile = manager.get_profile(profile_name)
        result = {"profile": profile_name, "model": profile.model}

        # 2. 如果profile有多个可用模型，提供模型选择
        if profile.models_available and len(profile.models_available) > 1:
            model_choices = []

            # 按思考模型分组
            reasoning_models = [m for m in profile.models_available if is_reasoning_model(m)]
            fast_models = [m for m in profile.models_available if not is_reasoning_model(m)]

            # 先添加思考模型
            if reasoning_models:
                for model in reasoning_models:
                    marker = " [当前Tag分类]" if model == profile.scenario_models.get(LLMScenario.TAG_CLASSIFICATION, "") else ""
                    model_choices.append(questionary.Choice(
                        title=f"🧪 {model} [THINK]{marker}",
                        value=model
                    ))

            # 再添加快速模型
            if fast_models:
                for model in fast_models:
                    marker = " [当前策略扫描]" if model == profile.scenario_models.get(LLMScenario.STRATEGY_SCAN, "") else ""
                    model_choices.append(questionary.Choice(
                        title=f"⚡ {model} [FAST]{marker}",
                        value=model
                    ))

            model_choices.append(questionary.Separator())
            model_choices.append(questionary.Choice(
                title="使用默认配置 (保持场景化模型设置)",
                value=profile.model
            ))

            selected_model = questionary.select(
                "选择默认模型 (可稍后在扫描时按场景自动切换):",
                choices=model_choices,
                style=MENU_STYLE
            ).ask()

            if selected_model:
                result["model"] = selected_model

        # 保存到实例变量（用于后续功能如Tags分类）
        if result:
            self.current_llm_profile = result.get("profile")
            self.current_llm_model = result.get("model")

            # 🆕 保存到 config.json
            self._save_active_profile_to_config(result.get("profile"))

        return result

    def _save_active_profile_to_config(self, profile_name: str) -> bool:
        """
        将选择的LLM profile保存到config.json的active_profile字段

        Args:
            profile_name: profile名称

        Returns:
            是否成功保存
        """
        config_path = "config.json"

        if not os.path.exists(config_path):
            return False

        try:
            # 读取现有配置
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 更新 active_profile
            config['active_profile'] = profile_name

            # 保存回文件
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            # 提示用户
            if self.output.use_rich:
                self.output.console.print(
                    f"[green]✓ 已保存LLM配置: {profile_name}[/green]"
                )
                self.output.console.print(
                    "[dim]提示: 下次启动将自动使用此配置[/dim]"
                )

            return True

        except Exception as e:
            if self.output.use_rich:
                self.output.console.print(
                    f"[yellow]⚠ 保存配置失败: {e}[/yellow]"
                )
            return False

    def select_category(self, scanner) -> Any:
        """
        选择扫描类别 (支持动态发现和固定域)

        Args:
            scanner: ArbitrageScanner 实例

        Returns:
            选中的 CategoryInfo 对象
        """
        if not self.is_interactive:
            categories = scanner.get_available_categories()
            return categories[0] if categories else None

        # 获取可用类别
        if scanner.use_dynamic_categories:
            self.output.print_info("🔍 正在获取市场分类...")
            categories = scanner.get_available_categories()
        else:
            categories = scanner.get_available_categories()

        if not categories:
            self.output.print_error("未找到任何可用类别")
            return None

        # 构建菜单选项
        choices = []
        for cat in sorted(categories, key=lambda c: c.priority):
            icon = cat.icon or "📁"
            # 只有动态分类才有市场统计
            market_hint = f" ({cat.market_count} markets)" if cat.market_count > 0 else ""

            choices.append(questionary.Choice(
                title=f"{icon} {cat.name_zh} - {cat.description[:50]}{market_hint}",
                value=cat
            ))

        # 添加管理选项
        choices.append(questionary.Separator())
        if scanner.use_dynamic_categories:
            choices.append(questionary.Choice(
                title="🔄 重新发现分类 (强制刷新 LLM 分析)",
                value="refresh"
            ))

        choices.append(questionary.Choice(
            title="⚙️ 切换分类模式 (动态/固定)",
            value="switch_mode"
        ))

        result = questionary.select(
            "选择扫描类别:",
            choices=choices,
            style=MENU_STYLE
        ).ask()

        # 处理特殊操作
        if result == "refresh":
            self.output.print_info("正在重新分析市场 tags...")
            scanner.get_available_categories(force_refresh=True)
            return self.select_category(scanner)  # 递归调用
        elif result == "switch_mode":
            scanner.use_dynamic_categories = not scanner.use_dynamic_categories
            mode_name = "动态分类" if scanner.use_dynamic_categories else "固定分类"
            self.output.print_info(f"已切换到 {mode_name} 模式")
            return self.select_category(scanner)
        elif result is None:
            # 用户按了 Ctrl+C
            return categories[0]
        else:
            return result

    def select_domain(self) -> str:
        """
        选择扫描领域 (旧版 API 兼容)

        注意：新代码应优先使用 select_category
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

    def show_strategy_help(self, strategy_id: str, domain: str) -> None:
        """
        显示单个策略的详细帮助信息

        Args:
            strategy_id: 策略ID
            domain: 当前领域
        """
        try:
            from strategies import StrategyRegistry
            strategy = StrategyRegistry.get(strategy_id)
            if strategy:
                meta = strategy.metadata
            else:
                raise KeyError(strategy_id)
        except (ImportError, KeyError):
            # 从默认列表获取
            all_strategies = self._get_default_strategies(domain)
            for s in all_strategies:
                if s['id'] == strategy_id:
                    meta = s
                    break
            else:
                return

        # 兼容dict和StrategyMetadata
        if hasattr(meta, 'name'):
            name = meta.name
            name_en = meta.name_en
            description = meta.description
            risk = meta.risk_level.value if hasattr(meta.risk_level, 'value') else meta.risk_level
            help_detail = getattr(meta, 'help_detail', '')
            example = getattr(meta, 'example', '')
        else:
            name = meta['name']
            name_en = meta['name_en']
            description = meta['description']
            risk = meta['risk_level']
            help_detail = meta.get('help_detail', '')
            example = meta.get('example', '')

        # 显示详细信息
        help_text = f"""
{'='*60}
  {name} ({name_en})
{'='*60}

[描述] {description}
[风险] {risk.upper()}
"""

        if help_detail:
            help_text += f"""
[详细说明]
{help_detail}
"""

        if example:
            help_text += f"""
[示例]
{example}
"""

        help_text += "="*60 + "\n"

        # 使用 UTF-8 编码输出
        import sys
        if sys.platform == 'win32':
            # Windows 控制台使用 UTF-8
            sys.stdout.reconfigure(encoding='utf-8')
        print(help_text)
        if self.is_interactive:
            try:
                questionary.press_any_key_to_continue("按任意键返回...").ask()
            except Exception:
                # 非交互环境，跳过
                pass

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

        # 首先询问是否查看策略说明
        show_help = questionary.confirm(
            "是否先查看策略详细说明?",
            default=False,
            style=MENU_STYLE
        ).ask()

        if show_help:
            # 显示策略说明菜单
            strategy_choices = []
            for meta in available:
                if hasattr(meta, 'id'):
                    strategy_id = meta.id
                    name = meta.name
                else:
                    strategy_id = meta['id']
                    name = meta['name']

                strategy_choices.append(questionary.Choice(
                    title=f"{name}",
                    value=strategy_id
                ))

            strategy_choices.append(questionary.Separator())
            strategy_choices.append(questionary.Choice("返回策略选择", value="back"))

            while True:
                choice = questionary.select(
                    "选择要查看的策略:",
                    choices=strategy_choices,
                    style=MENU_STYLE
                ).ask()

                if choice == "back" or choice is None:
                    break
                self.show_strategy_help(choice, domain)

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
                'domains': ['crypto'],
                'help_detail': '检测原理: 检测阈值市场的价格倒挂现象\n适用条件: 加密货币阈值市场（如 BTC>100k, ETH>5k）',
                'example': '示例: BTC>100k 价格 65¢，BTC>95k 价格 60¢\n套利: 买入 BTC>95k YES，卖出 BTC>100k YES\n收益: 5¢（约8.3%）'
            },
            {
                'id': 'interval',
                'name': '区间套利',
                'name_en': 'Interval Arbitrage',
                'description': '区间覆盖关系套利',
                'risk_level': 'low',
                'priority': 2,
                'domains': ['crypto', 'all'],
                'help_detail': '检测原理: 利用区间覆盖关系和完备性\n适用条件: 价格区间类市场',
                'example': '示例: 完备区间总和 < 1 时，买入所有区间的YES'
            },
            {
                'id': 'exhaustive',
                'name': '完备集套利',
                'name_en': 'Exhaustive Set',
                'description': '互斥完备集定价不足',
                'risk_level': 'medium',
                'priority': 3,
                'domains': ['all'],
                'help_detail': '检测原理: 互斥完备集的YES价格总和应等于1\n适用条件: 多选项市场',
                'example': '示例: 选举候选人价格总和 < 1 时，买入所有候选人YES'
            },
            {
                'id': 'implication',
                'name': '蕴含关系套利',
                'name_en': 'Implication Violation',
                'description': 'A -> B 价格违背',
                'risk_level': 'medium',
                'priority': 4,
                'domains': ['all'],
                'help_detail': '检测原理: 利用逻辑蕴含关系 P(B) >= P(A)\n适用条件: 存在逻辑蕴含关系的两个市场',
                'example': '示例: "BTC>100k" 蕴含 "BTC>95k"\n套利: 买入B_YES + 买入A_NO'
            },
            {
                'id': 'equivalent',
                'name': '等价市场套利',
                'name_en': 'Equivalent Markets',
                'description': '同事件不同表述',
                'risk_level': 'medium',
                'priority': 5,
                'domains': ['all'],
                'help_detail': '检测原理: 同一事件的不同表述应有相同价格\n适用条件: 语义等价的两个市场',
                'example': '示例: 同一BTC目标价的不同表述有价差时，低买高卖'
            },
        ]

        return [
            s for s in all_strategies
            if 'all' in s['domains'] or domain in s['domains']
        ]

    def select_subcategories(self, domain: str) -> Optional[List[str]]:
        """
        选择子类别（按分组选择）

        Args:
            domain: 当前领域

        Returns:
            子类别标签列表，None表示全部
        """
        # 尝试加载子类别分组配置
        groups = self._load_subcategory_groups(domain)

        # 检查是否有有效的子类别分组
        if not groups or len(groups) == 0:
            return None

        if not self.is_interactive:
            return None  # 非交互模式默认全部

        # 构建分组选项
        choices = [questionary.Choice("全部 (所有标签)", value="__ALL__", checked=True)]

        for group_name, tags in groups.items():
            tag_count = len(tags)
            choices.append(questionary.Choice(
                title=f"{group_name} ({tag_count}个标签)",
                value=f"GROUP:{group_name}",
                checked=False
            ))

        selected = questionary.checkbox(
            "选择子类别分组 (留空或选择'全部'=所有子类别):",
            choices=choices,
            style=MENU_STYLE
        ).ask()

        if not selected or "__ALL__" in selected:
            return None

        # 展开选中的分组，返回所有相关标签
        expanded_tags = []
        for selection in selected:
            if selection.startswith("GROUP:"):
                group_name = selection.replace("GROUP:", "")
                expanded_tags.extend(groups.get(group_name, []))

        return expanded_tags if expanded_tags else None

    def _load_subcategory_groups(self, domain: str) -> Optional[Dict[str, List[str]]]:
        """
        加载子类别分组配置

        Args:
            domain: 当前领域

        Returns:
            分组字典，如 {"BTC相关": ["bitcoin", "bitcoin-prices", ...]}
        """
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'data',
            'tag_categories.json'
        )

        if not os.path.exists(config_path):
            return None

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 优先使用 groups 配置
            groups = data.get('groups', {}).get(domain, {})
            if groups:
                return groups

            # 回退到首字母分组（兼容旧配置）
            subcats = data.get('categories', {}).get(domain, [])
            if not subcats:
                return None

            # 按首字母分组
            grouped = {}
            for tag in sorted(subcats):
                first_char = tag[0].upper() if tag else '其他'
                if first_char.isalpha():
                    group_name = f"{first_char}开头"
                else:
                    group_name = '其他'

                if group_name not in grouped:
                    grouped[group_name] = []
                grouped[group_name].append(tag)

            return grouped if grouped else None

        except Exception:
            return None

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
            questionary.Choice(
                "使用缓存数据 (推荐，速度更快)",
                value=False
            ),
            questionary.Choice(
                "强制刷新市场数据 (从API重新获取最新价格)",
                value=True
            ),
        ]

        result = questionary.select(
            "选择数据来源:",
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

    def gather_backtest_config(self) -> Dict[str, Any]:
        """
        收集回测配置

        Returns:
            配置字典
        """
        if not self.is_interactive:
            return {}

        # 1. 选择时间范围
        from datetime import datetime, timedelta
        now = datetime.now()
        
        choices = [
            questionary.Choice("最近 24 小时", value="24h"),
            questionary.Choice("最近 3 天", value="3d"),
            questionary.Choice("最近 7 天", value="7d"),
            questionary.Choice("自定义范围", value="custom"),
            questionary.Separator(),
            questionary.Choice("返回", value="back"),
        ]
        
        time_range = questionary.select(
            "请选择回测时间范围:",
            choices=choices,
            style=MENU_STYLE
        ).ask()
        
        if not time_range or time_range == "back":
            return None
            
        start_time = ""
        end_time = now.isoformat()
        
        if time_range == "24h":
            start_time = (now - timedelta(hours=24)).isoformat()
        elif time_range == "3d":
            start_time = (now - timedelta(days=3)).isoformat()
        elif time_range == "7d":
            start_time = (now - timedelta(days=7)).isoformat()
        elif time_range == "custom":
            # 简单实现：输入 ISO 格式
            start_time = questionary.text(
                "请输入开始时间 (ISO格式, 例如 2026-01-01T00:00:00):",
                default=(now - timedelta(days=1)).isoformat()
            ).ask()
            
            end_time = questionary.text(
                "请输入结束时间 (ISO格式):",
                default=now.isoformat()
            ).ask()

        # 2. 选择策略 (复用 select_strategies，但传入 "all" 以显示所有策略)
        # 注意：这里我们假设回测通常跨越多个领域，或者让用户自己过滤
        # 为了简化，我们先让用户选择领域，或者直接显示所有
        
        domain_choices = [
            questionary.Choice("加密货币 (Crypto)", value="crypto"),
            questionary.Choice("政治 (Politics)", value="politics"),
            questionary.Choice("体育 (Sports)", value="sports"),
            questionary.Choice("其他 (Other)", value="other"),
            questionary.Choice("所有领域", value="all")
        ]
        
        domain = questionary.select(
            "请选择主要回测领域 (用于筛选策略):",
            choices=domain_choices,
            style=MENU_STYLE
        ).ask()
        
        if not domain:
            return None
            
        strategies = self.select_strategies(domain)
        if not strategies:
            return None
            
        return {
            "start_time": start_time,
            "end_time": end_time,
            "strategies": strategies
        }

    def gather_scan_config(self) -> Dict[str, Any]:
        """
        收集完整的扫描配置

        Returns:
            配置字典
        """
        config = {}

        # 0. LLM配置 (新增，在最前面)
        llm_config = self.select_llm_profile()
        if llm_config:
            config['llm_profile'] = llm_config.get('profile')
            config['llm_model'] = llm_config.get('model')

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

== Tags智能分类 ==
自动从Polymarket API获取所有tags，使用LLM智能分类到：
- crypto: 加密货币、区块链、DeFi相关
- politics: 政治、选举相关
- sports: 体育、赛事相关
- other: 其他类别

分类后会生成预览报告，确认后可更新配置文件。

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

    def tags_classify_menu(self) -> bool:
        """
        Tags智能分类菜单（二级菜单）

        提供两种分类模式：
        1. 刷新分类标签 - 从API重新拉取所有tags
        2. 细分Other分类 - 将other重分类到细分类别

        Returns:
            是否成功完成分类
        """
        from .tag_classifier import classify_tags_interactive

        if not self.is_interactive:
            self.output.print_info("Tags分类需要交互模式，跳过...")
            return False

        # 1. 显示二级菜单选项
        choices = [
            questionary.Choice("刷新分类标签 (从API重新拉取)", value="refresh"),
            questionary.Choice("细分Other分类 (将other重分类)", value="refine"),
            questionary.Separator(),
            questionary.Choice("返回主菜单", value="back"),
        ]

        action = questionary.select(
            "Tags分类操作:",
            choices=choices,
            style=MENU_STYLE,
            use_shortcuts=True
        ).ask()

        if action == "back" or not action:
            return False

        # 2. 根据选择显示不同的说明Panel
        if action == "refresh":
            # 显示"刷新分类标签"说明
            if self.output.use_rich:
                from rich.panel import Panel
                panel = Panel.fit(
                    "[bold cyan]Tags智能分类 - 刷新标签[/bold cyan]\n\n"
                    "从Polymarket API获取所有tags，\n"
                    "使用LLM智能分类到9个类别。\n\n"
                    "[dim]• 批量分类，快速高效\n"
                    "• 生成预览报告，确认后应用\n"
                    "• 自动备份原配置文件\n\n"
                    "分类类别：\n"
                    "crypto, politics, sports, finance, tech,\n"
                    "entertainment, science, weather, misc[/dim]",
                    border_style="cyan",
                    padding=(1, 2)
                )
                self.output.console.print(panel)
            else:
                print("\n" + "=" * 40)
                print("Tags智能分类 - 刷新标签")
                print("=" * 40)
                print("从API获取tags并使用LLM智能分类到9个类别")

            # 确认是否继续
            confirm = questionary.confirm(
                "开始从API获取tags并进行智能分类?",
                default=True,
                style=MENU_STYLE
            ).ask()

            if not confirm:
                return False

            # 执行刷新分类
            return classify_tags_interactive(
                menu=self,
                llm_profile=self.current_llm_profile,
                mode='refresh'
            )

        elif action == "refine":
            # 显示"细分Other分类"说明
            if self.output.use_rich:
                from rich.panel import Panel
                panel = Panel.fit(
                    "[bold cyan]Tags智能分类 - 细分Other[/bold cyan]\n\n"
                    "将当前标记为'other'的tags（约2439个）\n"
                    "重新分类到6个细分类别。\n\n"
                    "[dim]• finance (传统金融)\n"
                    "• tech (科技/AI)\n"
                    "• entertainment (娱乐/文化)\n"
                    "• science (科学/研究)\n"
                    "• weather (天气/自然)\n"
                    "• misc (杂项)\n\n"
                    "预计需要约120次LLM调用[/dim]",
                    border_style="cyan",
                    padding=(1, 2)
                )
                self.output.console.print(panel)
            else:
                print("\n" + "=" * 40)
                print("Tags智能分类 - 细分Other")
                print("=" * 40)
                print("将other标签重新分类到细分类别")

            # 确认是否继续
            confirm = questionary.confirm(
                "开始对Other标签进行细分分类?",
                default=True,
                style=MENU_STYLE
            ).ask()

            if not confirm:
                return False

            # 执行细分分类
            return classify_tags_interactive(
                menu=self,
                llm_profile=self.current_llm_profile,
                mode='refine'
            )

        return False
