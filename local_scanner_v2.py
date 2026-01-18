#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Polymarket 组合套利系统 - 本地完整版 v2
========================================

支持多种LLM提供商，可快速切换：
- SiliconFlow (国内聚合，推荐)
- DeepSeek (便宜好用)
- OpenAI / Anthropic / 阿里云 / 智谱
- Ollama (本地免费)

使用方法：
    # 方式1: 使用预设配置（推荐）
    python local_scanner_v2.py --profile siliconflow
    python local_scanner_v2.py --profile deepseek
    python local_scanner_v2.py --profile ollama
    
    # 方式2: 环境变量
    export SILICONFLOW_API_KEY="your-key"
    python local_scanner_v2.py --profile siliconflow
    
    # 方式3: 自动检测
    python local_scanner_v2.py
    
    # 查看所有可用配置
    python llm_config.py --list
    
    # 切换模型
    python local_scanner_v2.py --profile siliconflow --model deepseek-ai/DeepSeek-V3
"""

import logging
import traceback
import requests
import json
import os
import sys
import sqlite3
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict, is_dataclass
from pathlib import Path
from typing import List, Optional, Dict, Tuple, Any
from collections import defaultdict
from enum import Enum

# ============================================================
# UTF-8编码配置 - 已通过emoji→ASCII替换解决编码问题
# ============================================================
# 注意：由于io.TextIOWrapper会导致stderr关闭问题，
# 我们采用更简单的方案：所有emoji已替换为ASCII字符
from datetime import datetime, UTC, timezone, timedelta
from enum import Enum

# 导入LLM提供商和配置
from llm_providers import create_llm_client, BaseLLMClient, LLMResponse
from config import Config as AppConfig
from prompts import (
    format_analysis_prompt,
    format_exhaustive_prompt,
    PromptConfig,
    RELATIONSHIP_ANALYSIS_PROMPT_V2
)

# ✅ 新增：导入验证层
from validators import MathValidator

# ✅ 新增：导入动态分类模块 (v3.1)
from category_discovery import CategoryDiscovery, CategoryInfo

# ✅ 新增：导入验证引擎 (v2.5)
from validation_engine import ValidationEngine
from notifier import ArbitrageNotifier
from execution_engine import ExecutionEngine
from semantic_cluster import SemanticClusterer
from data_recorder import TimeSeriesRecorder
from backtest_engine import BacktestEngine
from secret_manager import secrets
from ws_client import PolymarketWSClient

# ✅ 新增：导入 CLI 模块（v3.1）
try:
    from cli import InteractiveMenu, ScannerOutput
    from strategies import StrategyRegistry, BaseArbitrageStrategy, StrategyMetadata
    CLI_AVAILABLE = True
except ImportError:
    CLI_AVAILABLE = False
    InteractiveMenu = None
    ScannerOutput = None
    StrategyRegistry = None

# ============================================================
# Logging 配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================
# 🆕 子类别简写映射（v2.1新增）
# ============================================================
# 支持常见币种/标签的简写，方便用户快速输入
SUBCATEGORY_ALIASES = {
    "btc": "bitcoin",
    "eth": "ethereum",
    "sol": "solana",
    "bnb": "bnb",
    "xrp": "xrp",
    "ada": "cardano",  # ada对应cardano
    "dot": "polkadot",
    "avax": "avalanche",
    "matic": "polygon",
    "uni": "uniswap",
    "aave": "aave",
    "comp": "compound",
    "link": "chainlink",
}


# ============================================================
# 数据结构
# ============================================================


class RelationType(Enum):
    IMPLIES_AB = "implies_ab"
    IMPLIES_BA = "implies_ba"
    EQUIVALENT = "equivalent"
    MUTUAL_EXCLUSIVE = "mutual_exclusive"
    EXHAUSTIVE = "exhaustive"
    UNRELATED = "unrelated"

    # ✅ 新增: 区间关系类型
    INTERVAL_COVERS = "interval_covers"      # A的区间覆盖B（B是A的子集）
    INTERVAL_SUBSET = "interval_subset"      # A是B的子集
    INTERVAL_OVERLAP = "interval_overlap"    # 区间重叠


class RunMode(Enum):
    """运行模式枚举"""
    DEBUG = "debug"           # 调试模式：发现套利后暂停确认
    PRODUCTION = "production" # 生产模式：自动保存所有机会，无人值守运行


@dataclass
class Market:
    id: str
    condition_id: str
    question: str
    description: str              # Market-level description (legacy, may be empty)
    yes_price: float              # 中间价/参考价 (展示用)
    no_price: float               # 1 - yes_price (展示用)
    volume: float
    liquidity: float
    end_date: str
    event_id: str
    event_title: str
    resolution_source: str
    outcomes: List[str]
    # 陷阱1修复: 增加真实的 Bid/Ask 价格
    best_bid: float = 0.0         # 最佳买价 (你卖出时的价格)
    best_ask: float = 0.0         # 最佳卖价 (你买入时的价格)
    spread: float = 0.0           # 价差 = ask - bid
    token_id: str = ""            # CLOB token ID - YES token (用于获取订单簿)
    # 单调性套利修复: 增加 NO token 相关字段
    no_token_id: str = ""         # CLOB token ID - NO token
    best_bid_no: float = 0.0      # NO的最佳买价
    best_ask_no: float = 0.0      # NO的最佳卖价

    # ✅ 新增: Rules分析相关字段
    event_description: str = ""   # Event的description (包含resolution rules!)
    market_description: str = ""  # Market自己的description
    tags: List[Dict] = None       # Event的tags (用于分类过滤)
    orderbook: Dict = None        # Full orderbook data (for arbitrage opportunity reporting)

    # ✅ 新增: 区间市场相关字段 (用于多outcome/区间市场套利)
    group_item_title: str = ""     # 区间显示名称 (如 "80,000-82,000")
    group_item_threshold: str = "" # 区间排序序号 (如 "0", "1", "2"...)
    interval_type: str = ""        # 区间类型: "below", "range", "above", ""
    interval_lower: float = None   # 区间下界 (如 80000)
    interval_upper: float = None   # 区间上界 (如 82000)


    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.orderbook is None:
            self.orderbook = {}
    def __repr__(self):
        return f"Market('{self.question[:50]}...', YES=${self.yes_price:.2f}, spread={self.spread:.3f})"

    @property
    def full_description(self) -> str:
        """获取完整的描述信息（优先使用event_description）"""
        if self.event_description:
            return self.event_description
        return self.market_description or self.description

    @property
    def effective_buy_price(self) -> float:
        """实际买入价格 - 套利计算时使用 best_ask"""
        return self.best_ask if self.best_ask > 0 else self.yes_price

    @property
    def effective_sell_price(self) -> float:
        """实际卖出价格 - 套利计算时使用 best_bid"""
        return self.best_bid if self.best_bid > 0 else self.yes_price

    @property
    def is_expired(self) -> bool:
        """检查市场是否已过期（end_date已过）

        Note: Polymarket API dates are in UTC, so we use UTC time for comparison
        """
        if not self.end_date:
            return False  # 无结算日期的市场视为未过期
        try:
            # 解析 end_date，支持多种格式
            date_str = self.end_date
            if 'T' in date_str:
                # ISO 8601 格式: "2024-01-15T00:00:00Z" 或 "2024-01-15T00:00:00.000Z"
                date_str = date_str.split('T')[0]
            # 解析日期部分
            end_dt = datetime.strptime(date_str, "%Y-%m-%d")
            # 使用UTC时间比较，因为Polymarket API使用UTC
            from datetime import timezone
            now_utc = datetime.now(timezone.utc)
            # 如果 end_date 在UTC今天之前，则视为已过期
            return end_dt.date() < now_utc.date()
        except (ValueError, TypeError):
            return False  # 解析失败则视为未过期，保守处理


@dataclass
class ArbitrageOpportunity:
    id: str
    type: str
    markets: List[Dict]
    relationship: str
    confidence: float
    total_cost: float
    guaranteed_return: float
    profit: float
    profit_pct: float
    action: str
    reasoning: str
    edge_cases: List[str]
    needs_review: List[str]
    timestamp: str

    # 🆕 Phase 2.5 新增风控字段
    mid_price_profit: float = 0.0      # 基于中间价的理论利润
    effective_profit: float = 0.0      # 考虑订单簿深度后的实际利润
    slippage_cost: float = 0.0         # 预估滑点损失 (USD)
    days_to_resolution: int = 0        # 距离结算的预估天数
    apy: float = 0.0                   # 年化收益率 (%)
    apy_rating: str = "N/A"            # 收益评级 (EXCELLENT, GOOD, etc.)
    oracle_alignment: str = "UNKNOWN"  # 预言机对齐状态 (ALIGNED, MISALIGNED)
    validation_results: Dict = field(default_factory=dict)  # 五层验证的详细结果
    checklist_path: str = ""           # 自动生成的 Markdown 复核清单路径
    gas_estimate: float = 0.0          # 预估执行所需的 Gas 费 (USD)
    max_position_usd: float = 0.0      # 建议的最大投入金额 (USD)


# ============================================================
# JSON序列化辅助函数
# ============================================================

def json_serialize(obj: Any) -> Any:
    """
    递归序列化对象为JSON兼容格式

    处理:
    - dataclass对象 -> dict
    - Enum对象 -> value
    - 其他不可序列化对象 -> str
    """
    if is_dataclass(obj):
        return {k: json_serialize(v) for k, v in asdict(obj).items()}
    elif isinstance(obj, Enum):
        return obj.value
    elif isinstance(obj, dict):
        return {k: json_serialize(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [json_serialize(item) for item in obj]
    else:
        return obj


# ============================================================
# 速率限制器
# ============================================================

import threading

class RateLimiter:
    """简单的速率限制器，控制API请求频率 (线程安全)"""

    def __init__(self, calls_per_second: float = 2.0):
        """
        初始化速率限制器

        Args:
            calls_per_second: 每秒允许的请求数
        """
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0
        self.lock = threading.Lock()

    def wait(self):
        """在发起请求前调用，确保不超过速率限制"""
        import time
        with self.lock:
            elapsed = time.time() - self.last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_call = time.time()


# ============================================================
# Polymarket API客户端
# ============================================================

class PolymarketClient:
    """Polymarket API客户端"""

    def __init__(
        self,
        api_base: str = "https://gamma-api.polymarket.com",
        rate_limit: float = 2.0
    ):
        """
        初始化 Polymarket API 客户端

        Args:
            api_base: API基础URL
            rate_limit: 每秒请求数限制（默认2次/秒）
        """
        self.base_url = api_base
        self.session = requests.Session()

        # 🆕 配置重试策略 (Phase 5.3 稳定性增强)
        from requests.adapters import HTTPAdapter
        from urllib3.util import Retry
        retries = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

        self.session.headers.update({
            "User-Agent": "PolymarketArbitrageScanner/2.0"
        })
        # 初始化速率限制器
        self.rate_limiter = RateLimiter(calls_per_second=rate_limit)
    
    def get_markets(self, limit: int = 100, active: bool = True, 
                    min_liquidity: float = 0) -> List[Market]:
        """获取市场列表"""
        url = f"{self.base_url}/markets"
        params = {
            "limit": limit,
            "active": str(active).lower(),
            "closed": "false",
            "order": "volume",
            "ascending": "false"
        }
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            markets = []
            for item in data:
                try:
                    market = self._parse_market(item)
                    # 过滤掉已过期的市场和流动性不足的市场
                    if market and market.liquidity >= min_liquidity and not market.is_expired:
                        markets.append(market)
                except Exception as e:
                    continue
            
            return markets
            
        except requests.RequestException as e:
            print(f"API请求失败: {e}")
            return []
    
    def _parse_market(self, data: Dict, event_data: Dict = None) -> Optional[Market]:
        """
        解析市场数据

        Args:
            data: Market API返回的数据
            event_data: Event API返回的数据（如果从events端点获取）

        Returns:
            Market对象或None
        """
        try:
            outcome_prices = data.get('outcomePrices', '["0.5","0.5"]')
            if isinstance(outcome_prices, str):
                prices = json.loads(outcome_prices)
            else:
                prices = outcome_prices

            yes_price = float(prices[0]) if prices else 0.5

            outcomes_str = data.get('outcomes', '["Yes","No"]')
            if isinstance(outcomes_str, str):
                outcomes = json.loads(outcomes_str)
            else:
                outcomes = outcomes_str

            # 陷阱1修复: 获取 CLOB token ID (用于后续获取订单簿)
            clob_token_ids = data.get('clobTokenIds', '[]')
            if isinstance(clob_token_ids, str):
                try:
                    token_ids = json.loads(clob_token_ids)
                except:
                    token_ids = []
            else:
                token_ids = clob_token_ids or []
            # YES token 是第一个, NO token 是第二个
            yes_token_id = token_ids[0] if len(token_ids) > 0 else ""
            no_token_id = token_ids[1] if len(token_ids) > 1 else ""

            # ✅ 新增: 提取Event级别的description和tags
            event_description = ""
            tags = []
            if event_data:
                event_description = event_data.get('description', '')
                tags = event_data.get('tags', [])

            # ✅ 新增: Market自己的description
            market_description = data.get('description', '')

            # 兼容旧的description字段
            description = market_description or event_description

            # ✅ 新增: 解析区间市场信息
            group_item_title = data.get('groupItemTitle', '')
            group_item_threshold = data.get('groupItemThreshold', '')

            # 使用区间解析器解析区间信息
            interval_type = ""
            interval_lower = None
            interval_upper = None

            question = data.get('question', '')

            if group_item_title or question:
                from interval_parser_v2 import IntervalParser
                parser = IntervalParser()

                # 优先从 groupItemTitle 解析，如果没有则从 question 解析
                interval = parser.parse(group_item_title, question)
                if interval:
                    interval_type = interval.type.value
                    interval_lower = interval.lower
                    interval_upper = interval.upper if interval.upper != float('inf') else None

            # /events API 返回的market数据没有liquidity字段，使用volume作为流动性指标
            liquidity_value = data.get('liquidity')
            if liquidity_value is None:
                liquidity_value = data.get('volume', 0)

            market = Market(
                id=data.get('id', ''),
                condition_id=data.get('conditionId', ''),
                question=question,
                description=description,
                yes_price=yes_price,
                no_price=1 - yes_price,
                volume=float(data.get('volume', 0) or 0),
                liquidity=float(liquidity_value or 0),
                end_date=data.get('endDate', ''),
                event_id=(event_data.get('slug', '') if event_data else '') or data.get('eventSlug', '') or '',
                event_title=(event_data.get('title', '') if event_data else '') or data.get('groupItemTitle', '') or '',
                resolution_source=data.get('resolutionSource', ''),
                outcomes=outcomes,
                token_id=yes_token_id,
                no_token_id=no_token_id,
                event_description=event_description,
                market_description=market_description,
                tags=tags,
                # ✅ 新增: 区间市场字段
                group_item_title=group_item_title,
                group_item_threshold=group_item_threshold,
                interval_type=interval_type,
                interval_lower=interval_lower,
                interval_upper=interval_upper
            )

            return market
        except Exception:
            return None

    def get_market_details(self, market_id: str) -> Optional[Dict]:
        """
        [Phase 4.8] 获取单个市场的详细数据 (用于结算检查)
        """
        if not market_id:
            return None

        # 遵守速率限制
        if hasattr(self, 'rate_limiter'):
            self.rate_limiter.wait()

        url = f"{self.base_url}/markets/{market_id}"
        try:
            response = self.session.get(url, timeout=15)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.debug(f"获取市场详情失败 {market_id}: {e}")
            return None

    def fetch_orderbook(self, token_id: str) -> Dict:
        """
        从 CLOB API 获取订单簿数据

        陷阱1修复: 获取真实的 Bid/Ask 价格

        Args:
            token_id: CLOB token ID

        Returns:
            {"best_bid": float, "best_ask": float, "spread": float}
        """
        if not token_id:
            return {"best_bid": 0.0, "best_ask": 0.0, "spread": 0.0}

        # ✅ 遵守速率限制
        if hasattr(self, 'rate_limiter'):
            self.rate_limiter.wait()

        clob_url = f"https://clob.polymarket.com/book"
        try:
            response = self.session.get(
                clob_url,
                params={"token_id": token_id},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            # 解析订单簿
            bids = data.get("bids", [])
            asks = data.get("asks", [])

            # Best bid = 最高买价 (别人愿意买的最高价)
            best_bid = float(bids[0]["price"]) if bids else 0.0
            # Best ask = 最低卖价 (别人愿意卖的最低价)
            best_ask = float(asks[0]["price"]) if asks else 0.0
            spread = best_ask - best_bid if (best_ask > 0 and best_bid > 0) else 0.0

            return {
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread": spread
            }
        except Exception as e:
            # 静默失败，返回默认值
            return {"best_bid": 0.0, "best_ask": 0.0, "spread": 0.0}

    def enrich_market_with_orderbook(self, market: Market) -> Market:
        """
        为市场对象补充订单簿数据

        Args:
            market: Market 对象

        Returns:
            补充了 best_bid/best_ask/spread 的 Market 对象
        """
        if not market.token_id:
            return market

        orderbook = self.fetch_orderbook(market.token_id)
        market.best_bid = orderbook["best_bid"]
        market.best_ask = orderbook["best_ask"]
        market.spread = orderbook["spread"]
        market.orderbook = orderbook  # Store full orderbook for arbitrage reporting

        return market

    def enrich_with_no_orderbook(self, market: Market) -> Market:
        """
        为市场对象补充 NO token 的订单簿数据

        单调性套利修复: 获取真实的 NO 买入价，而非用 1 - YES价格 估算

        Args:
            market: Market 对象

        Returns:
            补充了 best_bid_no/best_ask_no 的 Market 对象
        """
        if not market.no_token_id:
            return market

        try:
            no_orderbook = self.fetch_orderbook(market.no_token_id)
            market.best_bid_no = no_orderbook["best_bid"]
            market.best_ask_no = no_orderbook["best_ask"]
        except Exception as e:
            logger.warning(f"获取NO订单簿失败: {e}")

        return market

    def get_events_by_tag(
        self,
        tag_id: str,
        active: bool = True,
        limit: int = 100,
        max_results: int = None,
        page_size: int = 100
    ) -> List[Dict]:
        """
        按tag_id获取events（支持分页）

        Args:
            tag_id: Tag ID (e.g., "21" for crypto)
            active: 是否只返回活跃事件
            limit: 返回数量限制（旧行为兼容，当max_results=None时使用）
            max_results: 最大结果数（None=旧行为用limit，0=全量获取，>0=指定数量）
            page_size: 每页大小（默认100）

        Returns:
            Event字典列表
        """
        # 默认行为：max_results=None 时，使用 limit 作为最大数量
        if max_results is None:
            max_results = limit
        elif max_results == 0:
            # 0 表示全量获取，设置一个很大的数
            max_results = float('inf')

        all_events = []
        offset = 0

        while True:
            # 终止条件1: 已达到最大结果数
            if len(all_events) >= max_results:
                break

            # 计算本次请求需要获取的数量
            current_limit = min(page_size, max_results - len(all_events))

            try:
                # 速率限制
                self.rate_limiter.wait()

                params = {
                    "tag_id": tag_id,
                    "limit": current_limit,
                    "offset": offset,
                    "closed": "false"  # 在API层面过滤已关闭的事件
                }
                if active is not None:
                    params["active"] = str(active).lower()

                url = f"{self.base_url}/events"
                response = self.session.get(url, params=params, timeout=10)
                response.raise_for_status()
                events = response.json()

                # 终止条件2: 返回空数组（没有更多数据）
                if not events:
                    break

                all_events.extend(events)

                # 全量获取模式：输出进度日志
                if max_results == float('inf'):
                    logger.info(f"  [tag_id={tag_id}] 已获取 {len(all_events)} 个events")

                # 终止条件3: 返回数量 < 请求数量（最后一页）
                if len(events) < current_limit:
                    break

                offset += current_limit

            except requests.RequestException as e:
                logger.error(f"获取events失败 (tag_id={tag_id}, offset={offset}): {e}")
                break

        return all_events

    def get_markets_by_tag(
        self,
        tag_id: str,
        active: bool = True,
        limit: int = 100,
        min_liquidity: float = 0,
        max_results: int = None,
        page_size: int = 100
    ) -> List[Market]:
        """
        按tag_id获取所有相关markets

        这是从events端点获取的，因此每个market都会包含
        event_description和tags信息。

        Args:
            tag_id: Tag ID (e.g., "21" for crypto)
            active: 是否只返回活跃市场
            limit: 返回数量限制（旧行为兼容）
            min_liquidity: 最小流动性过滤
            max_results: 最大结果数（None=旧行为，0=全量，>0=指定数量）
            page_size: 每页大小

        Returns:
            Market列表（包含event_description和tags）
        """
        markets = []

        events = self.get_events_by_tag(
            tag_id,
            active=active,
            limit=limit,
            max_results=max_results,
            page_size=page_size
        )

        for event in events:
            event_data = {
                "id": event.get("id"),
                "title": event.get("title"),
                "description": event.get("description", ""),
                "tags": event.get("tags", []),
                "resolutionSource": event.get("resolutionSource", "")
            }

            for market_data in event.get("markets", []):
                market = self._parse_market(market_data, event_data)
                if market:
                    # 过期市场过滤
                    if market.is_expired:
                        continue
                    # 流动性过滤
                    if min_liquidity > 0 and market.liquidity < min_liquidity:
                        continue
                    markets.append(market)

        return markets

    def get_markets_by_tag_slug(
        self,
        slug: str,
        active: bool = True,
        limit: int = 100,
        min_liquidity: float = 0,
        max_results: int = None,
        page_size: int = 100
    ) -> List[Market]:
        """
        按tag slug获取所有相关markets（便捷方法）

        Args:
            slug: Tag slug (e.g., "crypto", "politics")
            active: 是否只返回活跃市场
            limit: 返回数量限制（旧行为兼容）
            min_liquidity: 最小流动性过滤
            max_results: 最大结果数（None=旧行为，0=全量，>0=指定数量）
            page_size: 每页大小

        Returns:
            Market列表
        """
        # 首先获取tag_id
        try:
            self.rate_limiter.wait()
            url = f"{self.base_url}/tags/slug/{slug}"
            response = self.session.get(url, timeout=10)
            if response.status_code != 200:
                logger.error(f"Tag not found: {slug}")
                return []
            tag_data = response.json()
            tag_id = tag_data.get("id")
            if not tag_id:
                logger.error(f"Tag ID not found for: {slug}")
                return []
        except Exception as e:
            logger.error(f"Error fetching tag {slug}: {e}")
            return []

        return self.get_markets_by_tag(
            tag_id,
            active=active,
            limit=limit,
            min_liquidity=min_liquidity,
            max_results=max_results,
            page_size=page_size
        )

    # ============================================================
    # ✅ 新增: 按Event Slug获取Event及其Markets
    # ============================================================

    def get_event_by_slug(self, slug: str) -> Optional[Dict]:
        """
        通过slug获取单个event及其所有市场

        Args:
            slug: Event slug (e.g., "bitcoin-price-on-january-6")

        Returns:
            Event字典，包含markets数组；如果未找到返回None

        Example:
            event = client.get_event_by_slug("bitcoin-price-on-january-6")
            markets = event.get("markets", [])
        """
        try:
            url = f"{self.base_url}/events"
            params = {"slug": slug}
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            events = response.json()
            return events[0] if events else None
        except requests.RequestException as e:
            logger.error(f"获取event失败 (slug={slug}): {e}")
            return None

    def get_markets_in_event(
        self,
        event_slug: str,
        min_liquidity: float = 0
    ) -> List[Market]:
        """
        获取一个event下的所有市场并解析为Market对象

        这是检测跨Event套利的关键方法。例如：
        - "bitcoin-price-on-january-6" event有11个区间市场
        - "bitcoin-above-on-january-6" event有10个阈值市场
        - 可以对比两个event中的等价市场（如">98,000"）

        Args:
            event_slug: Event slug
            min_liquidity: 最小流动性过滤

        Returns:
            Market列表
        """
        event = self.get_event_by_slug(event_slug)
        if not event:
            return []

        markets = []
        event_data = {
            "id": event.get("id"),
            "title": event.get("title"),
            "description": event.get("description", ""),
            "slug": event.get("slug"),
            "tags": event.get("tags", []),
            "resolutionSource": event.get("resolutionSource", "")
        }

        for market_data in event.get("markets", []):
            market = self._parse_market(market_data, event_data)
            if market:
                # 过期市场过滤
                if market.is_expired:
                    continue
                if min_liquidity > 0 and market.liquidity < min_liquidity:
                    continue
                markets.append(market)

        return markets

    # ============================================================
    # 原有方法
    # ============================================================

    def get_markets_with_orderbook(self, limit: int = 100, active: bool = True,
                                   min_liquidity: float = 0, fetch_orderbook: bool = True) -> List[Market]:
        """
        获取市场列表并可选地补充订单簿数据

        Args:
            limit: 返回数量限制
            active: 是否只返回活跃市场
            min_liquidity: 最小流动性过滤
            fetch_orderbook: 是否获取订单簿数据 (会增加API调用)

        Returns:
            Market 列表
        """
        markets = self.get_markets(limit, active, min_liquidity)

        if fetch_orderbook:
            print(f"正在获取 {len(markets)} 个市场的订单簿数据...")
            for i, market in enumerate(markets):
                self.enrich_market_with_orderbook(market)
                if (i + 1) % 20 == 0:
                    print(f"  已处理 {i + 1}/{len(markets)} 个市场")

        return markets

    def fetch_crypto_markets(
        self,
        min_liquidity: float = 1000,
        search_queries: Optional[List[str]] = None
    ) -> List[Market]:
        """
        获取所有加密货币相关市场（多关键词组合策略）

        策略：
        1. 使用多个关键词搜索（Bitcoin, BTC, Ethereum等）
        2. 合并去重
        3. 按流动性排序

        Args:
            min_liquidity: 最小流动性过滤
            search_queries: 搜索关键词列表（默认使用加密货币关键词）

        Returns:
            去重后的加密货币市场列表
        """
        if search_queries is None:
            search_queries = [
                "Bitcoin", "BTC", "bitcoin", "btc",
                "Ethereum", "ETH", "ethereum", "eth",
                "crypto", "cryptocurrency", "Crypto"
            ]

        all_markets = []
        seen_ids = set()

        logging.info(f"🔍 使用 {len(search_queries)} 个关键词搜索加密货币市场...")

        for query in search_queries:
            # 使用关键词搜索市场
            # 注意：Gamma API可能不支持直接的关键词搜索参数
            # 这里我们获取大量市场，然后通过客户端过滤
            markets_batch = self.get_markets(
                limit=200,  # 每次获取200个
                active=True,
                min_liquidity=min_liquidity
            )

            # 客户端过滤：关键词匹配
            query_lower = query.lower()
            filtered = [
                m for m in markets_batch
                if (query_lower in m.question.lower() or
                    query_lower in m.description.lower() or
                    query_lower in m.event_title.lower())
            ]

            # 去重
            for m in filtered:
                if m.id not in seen_ids:
                    all_markets.append(m)
                    seen_ids.add(m.id)

            logging.info(f"  关键词 '{query}': 找到 {len(filtered)} 个市场")

        # 按流动性排序（降序）
        all_markets.sort(key=lambda m: m.liquidity, reverse=True)

        logging.info(f"[OK] 总共找到 {len(all_markets)} 个加密货币市场（去重后）")

        return all_markets


# ============================================================
# 市场领域分类器
# ============================================================

class MarketDomainClassifier:
    """
    市场领域分类器

    根据市场问题、描述、事件标题判断市场所属领域
    """

    CRYPTO_KEYWORDS = [
        'bitcoin', 'btc', 'ethereum', 'eth', 'crypto', 'cryptocurrency',
        'solana', 'sol', 'cardano', 'ada', 'polkadot', 'dot',
        'dogecoin', 'doge', 'chainlink', 'link', 'ripple', 'xrp',
        'polygon', 'matic', 'avalanche', 'avax', 'binance', 'bnb'
    ]

    POLITICS_KEYWORDS = [
        'election', 'congress', 'senate', 'president', 'trump', 'biden',
        'republican', 'democrat', 'vote', 'ballot', 'policy'
    ]

    SPORTS_KEYWORDS = [
        'nba', 'nfl', 'mlb', 'world cup', 'super bowl', 'championship',
        'game', 'team', 'player', 'score', 'match', 'tournament'
    ]

    def classify(self, market: Market) -> str:
        """
        判断市场所属领域

        Args:
            market: Market 对象

        Returns:
            领域标识: 'crypto', 'politics', 'sports', 'other'
        """
        # 合并所有文本字段进行判断
        text = (
            f"{market.question} {market.description} "
            f"{market.event_title}".lower()
        )

        # 加密货币
        if any(kw in text for kw in self.CRYPTO_KEYWORDS):
            return 'crypto'

        # 政治
        if any(kw in text for kw in self.POLITICS_KEYWORDS):
            return 'politics'

        # 体育
        if any(kw in text for kw in self.SPORTS_KEYWORDS):
            return 'sports'

        return 'other'


# ============================================================
# 市场数据缓存
# ============================================================

class MarketCache:
    """
    市场数据缓存管理器

    避免重复API调用，加速数据加载
    """

    def __init__(self, cache_dir: str = "./cache", cache_ttl: int = 3600):
        """
        Args:
            cache_dir: 缓存目录
            cache_ttl: 缓存有效期（秒），默认1小时
        """
        self.cache_dir = cache_dir
        self.cache_ttl = cache_ttl

        # 确保缓存目录存在
        os.makedirs(cache_dir, exist_ok=True)

    def _get_cache_file(self, domain: str) -> str:
        """获取缓存文件路径"""
        return os.path.join(self.cache_dir, f"{domain}_markets.json")

    def _is_cache_valid(self, cache_file: str) -> bool:
        """检查缓存是否有效"""
        if not os.path.exists(cache_file):
            return False

        # 检查文件修改时间
        file_mtime = os.path.getmtime(cache_file)
        current_time = datetime.now().timestamp()
        age = current_time - file_mtime

        return age < self.cache_ttl

    def _load_cache(self, cache_file: str) -> List[Market]:
        """从缓存文件加载市场数据"""
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            markets = []
            for item in data:
                try:
                    market = Market(**item)
                    markets.append(market)
                except Exception as e:
                    logging.warning(f"缓存数据解析失败: {e}")
                    continue

            return markets

        except Exception as e:
            logging.warning(f"缓存加载失败: {e}")
            return []

    def _save_cache(self, cache_file: str, markets: List[Market]):
        """保存市场数据到缓存文件"""
        try:
            data = [json_serialize(m) for m in markets]
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logging.info(f"💾 已保存缓存: {cache_file}")

        except Exception as e:
            logging.warning(f"缓存保存失败: {e}")

    def load_or_fetch(self, domain: str, fetcher, force_refresh: bool = False) -> List[Market]:
        """
        加载缓存或获取新数据

        Args:
            domain: 领域标识（'crypto', 'politics'等）
            fetcher: 数据获取函数（返回 List[Market]）
            force_refresh: 强制刷新，跳过缓存

        Returns:
            市场列表
        """
        cache_file = self._get_cache_file(domain)

        # 🆕 强制刷新时跳过缓存（v2.1新增）
        if force_refresh:
            logging.info(f"[REFRESH] 强制刷新 {domain} 市场数据，跳过缓存")
            markets = fetcher()
            # 保存到缓存
            if markets:
                self._save_cache(cache_file, markets)
            return markets

        # 尝试从缓存加载
        if self._is_cache_valid(cache_file):
            logging.info(f"[CACHE] 从缓存加载 {domain} 市场数据")
            markets = self._load_cache(cache_file)
            if markets:
                return markets

        # 缓存无效或不存在，重新获取
        logging.info(f"🌐 从API获取 {domain} 市场数据")
        markets = fetcher()

        # 保存到缓存
        if markets:
            self._save_cache(cache_file, markets)

        return markets

    def clear_cache(self, domain: Optional[str] = None):
        """
        清除缓存

        Args:
            domain: 领域标识，None表示清除所有缓存
        """
        if domain:
            cache_file = self._get_cache_file(domain)
            if os.path.exists(cache_file):
                os.remove(cache_file)
                logging.info(f"🗑️ 已清除 {domain} 缓存")
        else:
            # 清除所有缓存
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('_markets.json'):
                    file_path = os.path.join(self.cache_dir, filename)
                    os.remove(file_path)
            logging.info(f"🗑️ 已清除所有缓存")


# ============================================================
# LLM分析器（支持多种提供商）
# ============================================================

# 旧版Prompt（保留用于兼容）
ANALYSIS_PROMPT_LEGACY = """你是一个专门分析预测市场逻辑关系的专家。

请分析以下两个Polymarket预测市场之间的逻辑关系：

**市场A:**
- 问题: {question_a}
- 描述: {description_a}
- YES价格: ${price_a:.3f}
- 结算来源: {source_a}

**市场B:**
- 问题: {question_b}
- 描述: {description_b}
- YES价格: ${price_b:.3f}
- 结算来源: {source_b}

请判断逻辑关系类型（6选1）：
1. IMPLIES_AB: A发生→B必发生，约束P(B)≥P(A)
2. IMPLIES_BA: B发生→A必发生，约束P(A)≥P(B)
3. EQUIVALENT: A≡B，约束P(A)≈P(B)
4. MUTUAL_EXCLUSIVE: A⊕B，约束P(A)+P(B)≤1
5. EXHAUSTIVE: 完备集的一部分
6. UNRELATED: 无逻辑关系

请严格按以下JSON格式回答（不要有任何其他内容）：
```json
{{
  "relationship": "类型",
  "confidence": 0.0-1.0,
  "reasoning": "分析理由",
  "probability_constraint": "约束表达式",
  "edge_cases": ["边界情况"],
  "resolution_compatible": true或false
}}
```"""

# 使用新版Prompt（从prompts.py导入）
ANALYSIS_PROMPT = RELATIONSHIP_ANALYSIS_PROMPT_V2


class LLMAnalyzer:
    """LLM分析器 - 支持多种提供商"""

    def __init__(self, config: AppConfig = None, profile_name: str = None, model_override: str = None):
        self.config = config
        self.use_llm = True
        self.client: Optional[BaseLLMClient] = None
        self.profile_name = profile_name
        self.model_name = model_override

        try:
            # 方式1: 命令行指定 --profile
            if profile_name:
                self._init_from_profile(profile_name, model_override)

            # 方式2: config.json 中指定了 provider（优先于自动检测）
            elif config and config.llm.provider and config.llm.provider != "openai":
                # 注意：openai是默认值，如果没改过就跳过
                self._init_from_config(config, model_override)

            # 方式3: config.json 中指定了 api_key 或 api_base
            elif config and (config.llm.api_key or config.llm.api_base):
                self._init_from_config(config, model_override)

            # 方式4: 自动检测已配置的API Key
            else:
                self._init_from_auto_detect(model_override)

        except ValueError as e:
            print(f"[WARNING] LLM初始化失败: {e}")
            print("   将使用规则匹配替代LLM分析")
            self.use_llm = False
        except Exception as e:
            print(f"[WARNING] LLM初始化异常: {e}")
            self.use_llm = False

    def _init_from_profile(self, profile_name: str, model_override: str = None):
        """从profile配置初始化"""
        from llm_config import get_llm_config_by_name, LLMScenario
        profile = get_llm_config_by_name(profile_name)
        if not profile:
            raise ValueError(f"未找到配置: {profile_name}")

        if not profile.is_configured():
            raise ValueError(f"配置 {profile_name} 未设置API Key (需要: {profile.api_key_env})")

        # 如果没有指定模型覆盖，使用策略扫描场景的模型
        if model_override is None:
            model = profile.get_model_for_scenario(LLMScenario.STRATEGY_SCAN)
        else:
            model = model_override

        self.client = create_llm_client(
            provider=profile.provider,
            api_base=profile.api_base,
            api_key=profile.get_api_key(),
            model=model,
            max_tokens=profile.max_tokens,
            temperature=profile.temperature,
        )
        self.profile_name = profile_name
        self.model_name = model
        print(f"[OK] LLM已初始化 (--profile): {profile_name} / {model}")

    def _init_from_config(self, config: AppConfig, model_override: str = None):
        """从config.json初始化"""
        provider = config.llm.provider
        model = model_override or config.llm.model or None
        api_key = config.llm.api_key or None
        api_base = config.llm.api_base or None

        # 如果config没有api_key，尝试从环境变量读取
        if not api_key:
            env_key_map = {
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "deepseek": "DEEPSEEK_API_KEY",
                "aliyun": "DASHSCOPE_API_KEY",
                "zhipu": "ZHIPU_API_KEY",
                "siliconflow": "SILICONFLOW_API_KEY",
                "openai_compatible": "LLM_API_KEY",
            }
            env_var = env_key_map.get(provider, "LLM_API_KEY")
            api_key = os.getenv(env_var)

        self.client = create_llm_client(
            provider=provider,
            model=model,
            api_key=api_key,
            api_base=api_base,
            max_tokens=config.llm.max_tokens,
            temperature=config.llm.temperature,
        )
        self.model_name = self.client.config.model
        print(f"[OK] LLM已初始化 (config.json): {provider} / {self.client.config.model}")

    def _init_from_auto_detect(self, model_override: str = None):
        """自动检测可用的LLM配置"""
        from llm_config import get_llm_config, LLMScenario
        profile = get_llm_config()

        if not profile:
            raise ValueError(
                "未检测到可用的LLM配置。请选择以下方式之一:\n"
                "  1. 设置环境变量 (如 DEEPSEEK_API_KEY)\n"
                "  2. 使用 --profile 参数 (如 --profile deepseek)\n"
                "  3. 在 config.json 中配置 llm.provider 和 llm.api_key"
            )

        # 如果没有指定模型覆盖，使用策略扫描场景的模型
        if model_override is None:
            model = profile.get_model_for_scenario(LLMScenario.STRATEGY_SCAN)
        else:
            model = model_override

        self.client = create_llm_client(
            provider=profile.provider,
            api_base=profile.api_base,
            api_key=profile.get_api_key(),
            model=model,
            max_tokens=profile.max_tokens,
            temperature=profile.temperature,
        )
        self.profile_name = profile.name
        self.model_name = model
        print(f"[OK] LLM已初始化 (自动检测): {profile.name} / {model}")
    
    def analyze(self, market_a: Market, market_b: Market) -> Dict:
        """分析两个市场的逻辑关系"""
        if self.use_llm and self.client:
            return self._analyze_with_llm(market_a, market_b)
        else:
            return self._analyze_with_rules(market_a, market_b)
    
    def _analyze_with_llm(self, market_a: Market, market_b: Market) -> Dict:
        """使用LLM分析"""
        # 将Market对象转换为字典格式
        market_a_dict = {
            "question": market_a.question,
            "description": market_a.description or "",
            "yes_price": market_a.yes_price,
            "end_date": market_a.end_date or "未指定",
            "event_id": market_a.event_id or "未指定",
            "resolution_source": market_a.resolution_source or "未指定",
        }
        market_b_dict = {
            "question": market_b.question,
            "description": market_b.description or "",
            "yes_price": market_b.yes_price,
            "end_date": market_b.end_date or "未指定",
            "event_id": market_b.event_id or "未指定",
            "resolution_source": market_b.resolution_source or "未指定",
        }

        # 使用新版Prompt格式化函数
        prompt = format_analysis_prompt(
            market_a_dict,
            market_b_dict,
            PromptConfig(version="v2")
        )

        try:
            response = self.client.chat(prompt)
            content = response.content

            # 提取JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            result = json.loads(content.strip())

            # 标准化输出格式（兼容新旧格式）
            normalized = self._normalize_llm_response(result)
            return normalized

        except json.JSONDecodeError as e:
            # 保存完整LLM响应用于调试
            self._save_llm_error_response(market_a, market_b, response.content, content, str(e))

            error_msg = (
                f"JSON解析失败\n"
                f"  错误信息: {e}\n"
                f"  市场A: {market_a.question[:50]}...\n"
                f"  市场B: {market_b.question[:50]}...\n"
                f"  完整响应已保存到: output/llm_errors/"
            )
            logger.error(error_msg)
            print(f"    JSON解析失败: {e} (完整响应已保存)")
            return self._analyze_with_rules(market_a, market_b)
        except Exception as e:
            error_msg = (
                f"LLM分析失败\n"
                f"  错误类型: {type(e).__name__}\n"
                f"  错误信息: {e}\n"
                f"  市场A: {market_a.question[:50]}...\n"
                f"  市场B: {market_b.question[:50]}...\n"
                f"  堆栈跟踪:\n{traceback.format_exc()}"
            )
            logger.error(error_msg)
            print(f"    LLM分析失败: {e}")
            return self._analyze_with_rules(market_a, market_b)

    def _normalize_llm_response(self, result: Dict) -> Dict:
        """标准化LLM响应格式"""
        # 处理嵌套的reasoning结构
        reasoning = result.get("reasoning", "")
        if isinstance(reasoning, dict):
            reasoning = reasoning.get("conclusion", "") or reasoning.get("logical_analysis", "")

        relationship = result.get("relationship", "UNRELATED").upper()
        confidence = result.get("confidence", 0.5)

        # 构建临时结果用于一致性检查
        temp_result = {
            'relationship': relationship,
            'reasoning': reasoning,
            'confidence': confidence
        }

        # ✅ 调用一致性检查方法
        is_consistent, consistency_error = self._validate_llm_response_consistency(temp_result)

        if not is_consistent:
            print(f"    [WARNING] LLM输出一致性检查失败: {consistency_error}")
            print(f"       降级为 INDEPENDENT 以防止假套利")
            # 降级为 INDEPENDENT
            relationship = "INDEPENDENT"
            confidence = 0.0

        # 一致性检查: 检测 relationship 与 reasoning 是否矛盾（保留原有逻辑作为双重检查）
        reasoning_upper = reasoning.upper() if isinstance(reasoning, str) else ""
        inconsistency_detected = False

        if relationship == "IMPLIES_AB" and "IMPLIES_BA" in reasoning_upper:
            print(f"    [WARNING] LLM响应不一致: relationship={relationship}, 但reasoning提到IMPLIES_BA")
            inconsistency_detected = True
        elif relationship == "IMPLIES_BA" and "IMPLIES_AB" in reasoning_upper and "IMPLIES_BA" not in reasoning_upper:
            print(f"    [WARNING] LLM响应不一致: relationship={relationship}, 但reasoning提到IMPLIES_AB")
            inconsistency_detected = True

        # 如果检测到不一致，降低置信度
        if inconsistency_detected:
            confidence = min(confidence, 0.5)  # 降低到最多0.5

        # 提取关键字段
        normalized = {
            "relationship": relationship,
            "confidence": confidence,
            "reasoning": reasoning,
            "probability_constraint": result.get("probability_constraint"),
            "edge_cases": result.get("edge_cases", []),
            "resolution_compatible": result.get("resolution_check", {}).get("rules_compatible", True)
                                      if isinstance(result.get("resolution_check"), dict)
                                      else result.get("resolution_compatible", True),
            "constraint_violated": result.get("constraint_violated", False),
            "violation_amount": result.get("violation_amount", 0),
            "arbitrage_viable": result.get("arbitrage_viable", False),
            "inconsistency_detected": inconsistency_detected,  # 标记不一致
            "is_consistent": is_consistent,  # ✅ 新增：一致性检查结果
            "consistency_error": consistency_error if not is_consistent else None  # ✅ 新增：错误信息
        }

        return normalized

    
    def _analyze_with_rules(self, market_a: Market, market_b: Market) -> Dict:
        """使用规则匹配分析（备用方案）"""
        q_a = market_a.question.lower()
        q_b = market_b.question.lower()
        
        # 规则1: 个人候选人 vs 政党
        candidates = ["trump", "biden", "harris", "desantis", "haley", "newsom", "vance"]
        parties = ["republican", "democrat", "gop", "dem"]
        
        candidate_in_a = any(c in q_a for c in candidates)
        candidate_in_b = any(c in q_b for c in candidates)
        party_in_a = any(p in q_a for p in parties)
        party_in_b = any(p in q_b for p in parties)
        
        if candidate_in_a and party_in_b and not candidate_in_b:
            if ("republican" in q_b and any(c in q_a for c in ["trump", "desantis", "haley", "vance"])) or \
               ("democrat" in q_b and any(c in q_a for c in ["biden", "harris", "newsom"])):
                return {
                    "relationship": "IMPLIES_AB",
                    "confidence": 0.9,
                    "reasoning": "个人候选人获胜意味着其政党获胜",
                    "probability_constraint": "P(Party) >= P(Candidate)",
                    "edge_cases": ["候选人可能退出", "独立参选"],
                    "resolution_compatible": True,
                }
        
        # 规则2: 夺冠 vs 进季后赛
        if "champion" in q_a and "playoff" in q_b:
            return {
                "relationship": "IMPLIES_AB",
                "confidence": 0.99,
                "reasoning": "夺冠必须先进入季后赛",
                "probability_constraint": "P(Playoffs) >= P(Championship)",
                "edge_cases": [],
                "resolution_compatible": True,
            }
        
        if "playoff" in q_a and "champion" in q_b:
            return {
                "relationship": "IMPLIES_BA",
                "confidence": 0.99,
                "reasoning": "夺冠必须先进入季后赛",
                "probability_constraint": "P(Playoffs) >= P(Championship)",
                "edge_cases": [],
                "resolution_compatible": True,
            }
        
        # 规则3: 同一事件的互斥结果
        if market_a.event_id and market_a.event_id == market_b.event_id:
            return {
                "relationship": "MUTUAL_EXCLUSIVE",
                "confidence": 0.8,
                "reasoning": "同一事件下的不同结果通常互斥",
                "probability_constraint": "可能是完备集的一部分",
                "edge_cases": ["需要检查是否构成完备集"],
                "resolution_compatible": True,
            }
        
        # 默认
        return {
            "relationship": "UNRELATED",
            "confidence": 0.5,
            "reasoning": "未能通过规则匹配识别逻辑关系",
            "probability_constraint": None,
            "edge_cases": ["需要人工分析"],
            "resolution_compatible": None,
        }
    
    def _validate_llm_response_consistency(self, llm_result: dict) -> tuple[bool, str]:
        """
        验证 LLM 输出的 consistency

        检查 reasoning 字段是否与 relationship 分类矛盾

        Args:
            llm_result: LLM 返回的分析结果
                {
                    'relationship': 'IMPLIES_AB',
                    'reasoning': '...',
                    'confidence': 0.95
                }

        Returns:
            (is_valid, error_message)
            - is_valid: True 表示一致，False 表示发现矛盾
            - error_message: 矛盾描述

        Examples:
             # 矛盾案例：reasoning 说互斥，但 relationship 是 IMPLIES
             result = {
            ...     'relationship': 'IMPLIES_AB',
            ...     'reasoning': 'These markets are mutually exclusive'
            ... }
             is_valid, msg = analyzer._validate_llm_response_consistency(result)
             assert not is_valid
             assert 'mutual' in msg.lower()
        """
        relationship = llm_result.get('relationship', '')
        reasoning = llm_result.get('reasoning', '').lower()

        # 定义矛盾模式
        contradictions = {
            'IMPLIES_AB': [
                'mutual', 'exclusive', 'independent', 'unrelated',
                '矛盾', '互斥', '无关', '独立'
            ],
            'IMPLIES_BA': [
                'mutual', 'exclusive', 'independent', 'unrelated',
                '矛盾', '互斥', '无关', '独立'
            ],
            'EQUIVALENT': [
                'different', 'exclusive', 'independent', 'opposite',
                '不同', '互斥', '矛盾', '相反'
            ],
            'MUTUAL_EXCLUSIVE': [
                'implies', 'equivalent', 'same event', 'identical',
                '蕴含', '等价', '相同', '一致'
            ],
        }

        # 检查是否矛盾
        if relationship in contradictions:
            forbidden_terms = contradictions[relationship]
            for term in forbidden_terms:
                if term in reasoning:
                    return False, (
                        f"LLM 输出矛盾: relationship={relationship}, "
                        f"但 reasoning 包含 '{term}'"
                    )

        return True, ""

    def _save_llm_error_response(self, market_a: Market, market_b: Market,
                                 raw_response: str, extracted_content: str,
                                 error_msg: str):
        """
        保存LLM解析失败的完整响应用于调试

        Args:
            market_a: 市场A
            market_b: 市场B
            raw_response: LLM原始完整响应
            extracted_content: 提取出的JSON内容（可能是错误的）
            error_msg: JSON解析错误信息
        """
        import os
        from datetime import datetime

        # 创建错误目录
        error_dir = "output/llm_errors"
        os.makedirs(error_dir, exist_ok=True)

        # 生成文件名（包含时间戳和市场ID）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        safe_id_a = market_a.question[:30].replace(" ", "_").replace("/", "_") if market_a.question else "unknown"
        safe_id_b = market_b.question[:30].replace(" ", "_").replace("/", "_") if market_b.question else "unknown"
        filename = f"{timestamp}_{safe_id_a}_{safe_id_b}.txt"
        filepath = os.path.join(error_dir, filename)

        # 准备日志内容
        log_content = f"""=== LLM JSON解析错误日志 ===
时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
错误信息: {error_msg}

=== 市场A ===
ID: {market_a.id or 'N/A'}
问题: {market_a.question}
YES价格: {market_a.yes_price}
Event ID: {market_a.event_id or 'N/A'}

=== 市场B ===
ID: {market_b.id or 'N/A'}
问题: {market_b.question}
YES价格: {market_b.yes_price}
Event ID: {market_b.event_id or 'N/A'}

=== LLM原始响应 ===
{raw_response}

=== 提取的JSON内容（解析失败） ===
{extracted_content}

=== 结束 ===
"""

        # 写入文件
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(log_content)
        except Exception as write_error:
            logger.warning(f"无法保存LLM错误日志: {write_error}")

    def analyze_cluster(self, cluster_id: str, markets: List[Any]) -> Dict[str, Any]:
        """
        [Phase 5.2] 批量分析语义聚类簇
        """
        if not self.use_llm or not self.client:
            return {"relationships": [], "synthetic_opportunities": []}

        from prompts import CLUSTER_ANALYSIS_PROMPT

        # 1. 准备市场列表摘要 (Phase 5.4 性能优化：大型簇采样)
        max_analyze_size = 25
        if len(markets) > max_analyze_size:
            logging.info(f"簇规模过大 ({len(markets)})，仅分析前 {max_analyze_size} 个核心市场")
            # 尝试按流动性排序（如果属性存在）
            try:
                target_markets = sorted(markets, key=lambda x: getattr(x, 'liquidity', 0), reverse=True)[:max_analyze_size]
            except Exception:
                target_markets = markets[:max_analyze_size]
        else:
            target_markets = markets

        market_list_str = ""
        avg_liquidity = 0
        for m in target_markets:
            market_list_str += f"- ID: {m.id} | Question: {m.question} | Price: ${m.yes_price:.3f} | End: {m.end_date}\n"
            avg_liquidity += getattr(m, 'liquidity', 0)

        avg_liquidity /= len(target_markets) if target_markets else 1

        # 2. 填充并发送 Prompt
        prompt = CLUSTER_ANALYSIS_PROMPT.format(
            cluster_id=cluster_id,
            cluster_size=len(target_markets),
            avg_liquidity=avg_liquidity,
            market_list=market_list_str
        )

        try:
            # ✅ 修正：使用 chat 方法 (Phase 5.4 修复)
            response = self.client.chat(prompt)
            # 提取 JSON 内容
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            return json.loads(content)
        except Exception as e:
            logger.error(f"批量聚类分析失败: {e}")
            return {"relationships": [], "synthetic_opportunities": []}

    def close(self):
        """关闭LLM客户端"""
        if self.client:
            self.client.close()


# ============================================================
# 套利检测器
# ============================================================

class ArbitrageDetector:
    """套利机会检测器"""

    def __init__(self, config: AppConfig, llm_analyzer: 'LLMAnalyzer' = None):
        self.min_profit_pct = config.scan.min_profit_pct
        self.min_confidence = config.scan.min_confidence

        # ✅ 新增：初始化数学验证器
        self.math_validator = MathValidator()
        print(f"[OK] MathValidator 已初始化")

        # ✅ 新增：LLM 分析器引用（用于完备集验证）
        self.llm_analyzer = llm_analyzer

    def verify_exhaustive_set_with_llm(self, markets: List[Market]) -> Dict:
        """
        使用 LLM 验证市场组是否构成完备集

        Args:
            markets: 待验证的市场列表

        Returns:
            验证结果字典：
            {
                "is_valid": bool,
                "is_mutually_exclusive": bool,
                "is_complete": bool,
                "missing_options": [],
                "overlap_risks": [],
                "confidence": float,
                "reasoning": str
            }
        """
        if not self.llm_analyzer or not self.llm_analyzer.use_llm:
            # 没有 LLM，返回默认通过（依赖规则验证）
            return {
                "is_valid": True,
                "confidence": 0.5,
                "reasoning": "未配置LLM，跳过语义验证"
            }

        # 构建验证 Prompt
        from prompts import format_exhaustive_prompt

        event_title = markets[0].event_title or markets[0].event_id or "未知事件"
        markets_dict = [
            {"question": m.question, "yes_price": m.yes_price}
            for m in markets
        ]
        total_price = sum(m.yes_price for m in markets)

        prompt = format_exhaustive_prompt(event_title, markets_dict, total_price)

        try:
            response = self.llm_analyzer.client.chat(prompt)
            content = response.content

            # 提取 JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            result = json.loads(content.strip())

            # 标准化结果
            return {
                "is_valid": result.get("is_valid_exhaustive_set", False),
                "is_mutually_exclusive": result.get("is_mutually_exclusive", False),
                "is_complete": result.get("is_complete", False),
                "missing_options": result.get("missing_options", []),
                "overlap_risks": result.get("overlap_risks", []),
                "confidence": result.get("confidence", 0.5),
                "reasoning": result.get("reasoning", ""),
                "arbitrage_safe": result.get("arbitrage_safe", False)
            }

        except json.JSONDecodeError as e:
            market_questions = [m.question[:30] + "..." for m in markets[:3]]
            error_msg = (
                f"LLM完备集验证JSON解析失败\n"
                f"  错误信息: {e}\n"
                f"  事件: {event_title}\n"
                f"  市场数量: {len(markets)}\n"
                f"  市场样例: {market_questions}\n"
                f"  原始响应: {content[:200] if 'content' in dir() else 'N/A'}..."
            )
            logger.error(error_msg)
            print(f"    [WARNING] LLM完备集验证JSON解析失败: {e}")
            return {
                "is_valid": False,
                "confidence": 0.0,
                "reasoning": f"JSON解析失败: {e}"
            }
        except Exception as e:
            market_questions = [m.question[:30] + "..." for m in markets[:3]]
            error_msg = (
                f"LLM完备集验证失败\n"
                f"  错误类型: {type(e).__name__}\n"
                f"  错误信息: {e}\n"
                f"  事件: {event_title}\n"
                f"  市场数量: {len(markets)}\n"
                f"  市场样例: {market_questions}\n"
                f"  堆栈跟踪:\n{traceback.format_exc()}"
            )
            logger.error(error_msg)
            print(f"    [WARNING] LLM完备集验证失败: {e}")
            return {
                "is_valid": False,
                "confidence": 0.0,
                "reasoning": f"验证失败: {e}"
            }



# ============================================================
# 主扫描器
# ============================================================

class ArbitrageScanner:
    """
    主扫描器 - 向量化驱动版本

    支持两种模式：
    1. 向量化模式（新）：按领域获取市场 → 语义聚类 → 聚类内全自动分析
    2. 传统模式（兼容）：关键词搜索 → Jaccard相似度 → LLM分析
    """

    def __init__(
        self,
        config: AppConfig,
        profile_name: str = None,
        model_override: str = None,
        run_mode: RunMode = RunMode.PRODUCTION
    ):
        """
        Args:
            config: 配置对象
            profile_name: LLM配置名称
            model_override: 模型覆盖
            run_mode: 运行模式 (DEBUG=暂停确认, PRODUCTION=自动保存)
        """
        self.config = config
        self.profile_name = profile_name
        self.model_override = model_override

        # 运行模式
        self.run_mode = run_mode

        # 成员变量
        self.false_positive_log = []   # 误报日志
        self.opportunity_counter = 0    # 机会计数器
        self.discovered_opportunities = []  # 发现的所有机会（用于自动保存）

        # 基础组件
        self.client = PolymarketClient()
        self.analyzer = LLMAnalyzer(config, profile_name=profile_name, model_override=model_override)
        # ✅ 传入 LLM 分析器，用于完备集语义验证
        self.detector = ArbitrageDetector(config, llm_analyzer=self.analyzer)

        # 市场缓存和分类组件（策略系统需要）
        self.market_cache = MarketCache(
            cache_dir=config.output.cache_dir,
            cache_ttl=getattr(config.scan, 'cache_ttl', 3600)
        )
        self.domain_classifier = MarketDomainClassifier()

        # ✅ 新增：语义聚类器 (Phase 2.6)
        try:
            self.clusterer = SemanticClusterer()
        except Exception as e:
            logging.warning(f"无法初始化语义聚类器: {e}，将禁用语义聚类功能")
            self.clusterer = None

        # ✅ 新增：动态分类组件 (v3.1)
        self.category_discovery = None
        self.use_dynamic_categories = getattr(config.scan, 'use_dynamic_categories', False)

        # ✅ 新增：验证引擎 (v2.5)
        self.validation_engine = ValidationEngine(config)

        # ✅ 新增：通知系统 (Phase 3.3)
        self.notifier = ArbitrageNotifier(config)

        # ✅ 新增：时间序列数据记录器 (Phase 6.1)
        self.recorder = TimeSeriesRecorder(
            db_path=Path(self.config.output.output_dir) / "market_history.db"
        )

        # ✅ 新增：WebSocket 实时客户端 (Phase 8)
        self.ws_client = PolymarketWSClient()
        self._ws_task = None

        # ✅ 新增：执行引擎 (Phase 4.1)
        # 🆕 传入 recorder 和 WebSocket 缓存 (Phase 8)
        self.execution_engine = ExecutionEngine(self.client, config, self.recorder, self.ws_client.cache)

        logging.info("✅ 策略系统组件、验证引擎、通知器、执行引擎、聚类器、记录器与 WS 客户端已初始化")

    def start_websocket(self, token_ids: List[str] = None):
        """
        [Phase 8] 启动 WebSocket 实时监听任务
        """
        import threading
        import asyncio

        if self._ws_task and not self._ws_task.done():
            if token_ids:
                asyncio.run_coroutine_threadsafe(self.ws_client.subscribe(token_ids), self._loop)
            return

        def run_ws_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            if token_ids:
                self.ws_client.assets_ids.extend(token_ids)
            self._loop.run_until_complete(self.ws_client.connect())

        self._ws_thread = threading.Thread(target=run_ws_loop, daemon=True)
        self._ws_thread.start()
        logging.info(f"WebSocket 监听线程已启动，预订阅 {len(token_ids) if token_ids else 0} 个资产")

    def stop_websocket(self):
        """停止 WebSocket 监听"""
        self.ws_client.stop()
        if hasattr(self, '_loop'):
            self._loop.stop()
        logging.info("WebSocket 监听已停止")

    def _load_tag_categories(self) -> Dict[str, List[str]]:
        """
        加载标签分类文件

        Returns:
            字典，key为类别名，value为tag slug列表
        """
        tag_categories_file = Path(__file__).parent / "data" / "tag_categories.json"
        if not tag_categories_file.exists():
            logging.warning(f"[WARNING] 标签分类文件不存在: {tag_categories_file}")
            return {}

        try:
            with open(tag_categories_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("categories", {})
        except Exception as e:
            logging.error(f"[ERROR] 加载标签分类失败: {e}")
            return {}

    def _expand_subcategory(self, subcat: str, all_tags: List[str]) -> List[str]:
        """
        扩展子类别，自动包含相关标签

        例如: bitcoin -> [bitcoin, bitcoin-prices, bitcoin-volatility, strategic-bitcoin-reserve, ...]

        Args:
            subcat: 子类别名称（如 "bitcoin"）
            all_tags: 该领域所有可用的tag列表

        Returns:
            包含该子类别的所有相关tag列表
        """
        # 查找所有包含子类别名称的标签（不区分大小写）
        subcat_lower = subcat.lower()
        related = [tag for tag in all_tags if subcat_lower in tag.lower()]

        # 如果没有找到相关标签，至少返回原始输入（可能是无效的，后续会验证）
        return related if related else [subcat]

    # ============================================================
    # 🆕 动态分类管理方法 (v3.1新增)
    # ============================================================

    def get_category_discovery(self) -> CategoryDiscovery:
        """
        获取或初始化分类发现引擎

        Returns:
            CategoryDiscovery 实例
        """
        if self.category_discovery is None:
            self.category_discovery = CategoryDiscovery(
                polymarket_client=self.client,
                llm_profile_name=self.profile_name,
                output=ScannerOutput() if CLI_AVAILABLE else None
            )
        return self.category_discovery

    def get_available_categories(self, force_refresh: bool = False) -> List[CategoryInfo]:
        """
        获取所有可用的扫描类别

        Args:
            force_refresh: 是否强制重新发现

        Returns:
            CategoryInfo 对象列表
        """
        if self.use_dynamic_categories:
            try:
                discovery = self.get_category_discovery()
                cache = discovery.discover_categories(
                    max_categories=getattr(self.config.scan, 'category_discovery_max', 12),
                    min_tags_per_category=getattr(self.config.scan, 'category_discovery_min_tags', 5),
                    force_refresh=force_refresh
                )

                # 转换为 CategoryInfo 对象列表
                categories = []
                for cat_dict in cache.categories:
                    # 处理从 JSON 加载时的 set/list 转换
                    included_tags = cat_dict.get('included_tags', set())
                    if isinstance(included_tags, list):
                        included_tags = set(included_tags)

                    categories.append(CategoryInfo(
                        id=cat_dict['id'],
                        name_zh=cat_dict['name_zh'],
                        name_en=cat_dict['name_en'],
                        description=cat_dict['description'],
                        representative_tags=cat_dict['representative_tags'],
                        market_count=cat_dict['market_count'],
                        discovery_confidence=cat_dict['discovery_confidence'],
                        created_at=cat_dict['created_at'],
                        included_tags=included_tags,
                        icon=cat_dict.get('icon', ''),
                        priority=cat_dict.get('priority', 999)
                    ))
                return sorted(categories, key=lambda x: x.priority)
            except Exception as e:
                logging.error(f"[ERROR] 动态分类发现失败: {e}")
                logging.info("回退到固定分类模式")
                return self._get_fixed_domain_categories()
        else:
            return self._get_fixed_domain_categories()

    def _get_fixed_domain_categories(self) -> List[CategoryInfo]:
        """
        获取硬编码的固定分类（用于向后兼容）

        Returns:
            CategoryInfo 列表
        """
        tag_categories = self._load_tag_categories()
        if not tag_categories:
            return []

        # 映射中文名称和图标
        meta = {
            "crypto": ("加密货币", "Cryptocurrency", "₿", 1),
            "politics": ("政治", "Politics", "🏛️", 2),
            "sports": ("体育", "Sports", "🏀", 3),
            "economics": ("经济", "Economics", "📈", 4),
            "entertainment": ("娱乐", "Entertainment", "🎬", 5),
            "other": ("其他", "Other", "📦", 999)
        }

        categories = []
        for domain, tags in tag_categories.items():
            name_zh, name_en, icon, priority = meta.get(domain, (domain, domain.capitalize(), "📁", 100))
            categories.append(CategoryInfo(
                id=domain,
                name_zh=name_zh,
                name_en=name_en,
                description=f"{name_zh}相关的预测市场",
                representative_tags=tags[:10],
                included_tags=set(tags),
                market_count=0, # 固定模式不统计
                discovery_confidence=1.0,
                created_at=datetime.now(UTC).isoformat(),
                icon=icon,
                priority=priority
            ))

        return sorted(categories, key=lambda x: x.priority)

    def fetch_markets_for_category(
        self,
        category: CategoryInfo,
        limit: int = 500,
        force_refresh: bool = False
    ) -> List[Market]:
        """
        为指定类别获取市场数据

        Args:
            category: 类别对象
            limit: 最大获取数量
            force_refresh: 是否强制刷新缓存

        Returns:
            市场列表
        """
        # 如果是固定域，尝试使用现有的缓存机制
        if not self.use_dynamic_categories:
            return self._fetch_domain_markets(category.id, force_refresh=force_refresh)

        # 动态分类的市场获取策略
        def fetcher():
            # 优先使用代表性标签获取
            tag_slugs = category.representative_tags
            if not tag_slugs:
                # 如果没有代表性标签，使用全部标签的前20个（避免请求过多）
                tag_slugs = sorted(list(category.included_tags))[:20]

            logging.info(f"[FETCH] 正在获取动态分类 '{category.name_zh}' 的市场 (Tags: {len(tag_slugs)})")

            all_markets = []
            seen_ids = set()

            for i, slug in enumerate(tag_slugs):
                try:
                    markets = self.client.get_markets_by_tag_slug(
                        slug,
                        active=True,
                        limit=100,
                        min_liquidity=self.config.scan.min_liquidity
                    )
                    for m in markets:
                        if m.id not in seen_ids:
                            all_markets.append(m)
                            seen_ids.add(m.id)

                    if (i + 1) % 5 == 0:
                        logging.info(f"  进度: {i+1}/{len(tag_slugs)} tags, 已获取 {len(all_markets)} 个市场")
                except Exception as e:
                    logging.debug(f"  获取 tag '{slug}' 失败: {e}")
                    continue

            # 按流动性排序并截断
            all_markets.sort(key=lambda x: x.liquidity, reverse=True)
            return all_markets[:limit]

        # 使用类别 ID 作为缓存键
        cache_key = f"dynamic_cat_{category.id}"
        return self.market_cache.load_or_fetch(cache_key, fetcher, force_refresh)

    def _fetch_domain_markets(self, domain: str, subcategories: List[str] = None, force_refresh: bool = False) -> List[Market]:
        """
        获取指定领域的所有市场（带缓存）

        使用分类后的tags来获取市场，确保获取该领域的所有市场。

        Args:
            domain: 领域标识 ("crypto", "politics", "sports", "economics", "entertainment", "other")
            subcategories: 子类别筛选 (如 ["bitcoin", "ethereum"])，None表示获取全部
            force_refresh: 强制刷新缓存，重新获取数据

        Returns:
            市场列表
        """
        # 加载标签分类
        tag_categories = self._load_tag_categories()

        if not tag_categories or domain not in tag_categories:
            logging.warning(f"[WARNING] 域 '{domain}' 的标签分类不存在")
            # 回退到原始方法
            if domain == "crypto":
                fetcher = lambda: self.client.fetch_crypto_markets(
                    min_liquidity=self.config.scan.min_liquidity
                )
            else:
                def fetcher():
                    all_markets = self.client.get_markets(
                        limit=500,
                        min_liquidity=self.config.scan.min_liquidity
                    )
                    return [m for m in all_markets if self.domain_classifier.classify(m) == domain]
            return self.market_cache.load_or_fetch(domain, fetcher)

        # 使用分类后的tags获取市场
        def fetcher():
            tag_slugs = tag_categories.get(domain, [])
            if not tag_slugs:
                logging.warning(f"[WARNING] 域 '{domain}' 没有关联的tags")
                return []

            # 🆕 子类别筛选和扩展（v2.1新增）
            if subcategories:
                all_tags = set(tag_slugs)
                expanded_tags = set()

                for subcat in subcategories:
                    # 使用模糊匹配查找相关标签
                    related = self._expand_subcategory(subcat, tag_slugs)
                    if related and related != [subcat]:
                        # 找到了相关标签，添加到扩展集合
                        expanded_tags.update(related)
                    elif subcat in all_tags:
                        # 精确匹配，直接添加
                        expanded_tags.add(subcat)
                    else:
                        logging.warning(f"[WARNING] 未找到匹配的标签: {subcat}")

                tag_slugs = list(expanded_tags)

                if not tag_slugs:
                    logging.warning(f"[WARNING] 没有有效的子类别")
                    return []

                subcat_info = f", 子类别: {', '.join(sorted(set(subcategories)))}"
                logging.info(f"[FETCH] 域 '{domain}'{subcat_info}")
                logging.info(f"[FETCH] 扩展为 {len(tag_slugs)} 个tags: {', '.join(sorted(tag_slugs)[:5])}{'...' if len(tag_slugs) > 5 else ''}")
            else:
                logging.info(f"[FETCH] 域 '{domain}' 有 {len(tag_slugs)} 个tags")

            all_markets = []
            for i, slug in enumerate(tag_slugs):
                try:
                    # 根据配置决定是否启用全量获取
                    max_results = (
                        self.config.scan.fetch_max_per_tag
                        if getattr(self.config.scan, 'enable_full_fetch', False)
                        else None
                    )
                    page_size = getattr(self.config.scan, 'fetch_page_size', 100)

                    markets = self.client.get_markets_by_tag_slug(
                        slug,
                        active=True,
                        limit=100,
                        min_liquidity=self.config.scan.min_liquidity,
                        max_results=max_results,
                        page_size=page_size
                    )
                    all_markets.extend(markets)
                    if (i + 1) % 20 == 0:
                        logging.info(f"  进度: {i+1}/{len(tag_slugs)} tags, 已获取 {len(all_markets)} 个市场")
                except Exception as e:
                    logging.debug(f"  获取tag '{slug}' 失败: {e}")
                    continue

            # 去重（基于market ID）
            seen_ids = set()
            unique_markets = []
            for m in all_markets:
                if m.id not in seen_ids:
                    # 🆕 市场状态和到期时间过滤 (Phase 2)
                    if getattr(self.config.scan, 'exclude_resolved', True):
                        # 如果没有状态字段，我们至少检查到期时间
                        try:
                            if m.end_date:
                                end_dt = datetime.fromisoformat(m.end_date.replace('Z', '+00:00'))
                                now_dt = datetime.now(UTC)
                                hours_left = (end_dt - now_dt).total_seconds() / 3600
                                if hours_left < getattr(self.config.scan, 'min_hours_to_expiration', 1):
                                    continue
                        except Exception:
                            pass

                    seen_ids.add(m.id)
                    unique_markets.append(m)

            # 🆕 批量补充订单簿数据 (Phase 1) - 异步并发版
            if getattr(self.config.scan, 'enable_orderbook', True):
                logging.info(f"[ORDERBOOK] 正在为 {len(unique_markets)} 个市场并发获取实时订单簿数据...")

                def fetch_task(market):
                    try:
                        # 获取 YES 订单簿
                        self.client.enrich_market_with_orderbook(market)
                        # 获取 NO 订单簿 (对单调性套利至关重要)
                        self.client.enrich_with_no_orderbook(market)
                        return True
                    except Exception as e:
                        logging.debug(f"获取订单簿失败 {market.id}: {e}")
                        return False

                # 使用线程池并发执行，RateLimiter (线程安全) 会控制实际请求频率
                max_workers = 5
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(fetch_task, m): m for m in unique_markets}

                    completed = 0
                    for _ in as_completed(futures):
                        completed += 1
                        if completed % 50 == 0:
                            logging.info(f"  进度: {completed}/{len(unique_markets)} 订单簿已同步")

            logging.info(f"[DONE] 域 '{domain}' 获取到 {len(unique_markets)} 个有效市场")

            # 🆕 启动 WebSocket 实时订阅 (Phase 8)
            token_ids = []
            for m in unique_markets:
                if m.token_id: token_ids.append(m.token_id)
                if m.no_token_id: token_ids.append(m.no_token_id)

            if token_ids:
                self.start_websocket(token_ids)

            return unique_markets

        # 🆕 构建缓存键：domain + subcategories（v2.1新增）
        cache_key = domain
        if subcategories:
            # 将subcategories排序后加入缓存键，确保顺序不影响缓存
            subcat_suffix = "_".join(sorted(subcategories))
            cache_key = f"{domain}_{subcat_suffix}"

        return self.market_cache.load_or_fetch(cache_key, fetcher, force_refresh)


    def _generate_polymarket_links(self, markets: List[Dict]) -> List[str]:
        """
        生成 Polymarket 市场链接

        Args:
            markets: 市场列表（从 ArbitrageOpportunity.markets 获取）

        Returns:
            链接列表
        """
        links = []
        for market in markets:
            # Polymarket URL 格式
            # https://polymarket.com/event/{event_slug}?market={market_id}
            market_id = market.get('id', '')
            # 使用 event_id 或简单的市场 ID
            url = f"https://polymarket.com/event/market?market={market_id}"
            links.append(url)

        return links

    def _save_report(
        self,
        opportunities: List[ArbitrageOpportunity],
        domain: str = "default"
    ):
        """
        保存报告

        Args:
            opportunities: 套利机会列表
            domain: 市场领域（用于文件名）
        """
        os.makedirs(self.config.output.output_dir, exist_ok=True)

        output_file = os.path.join(
            self.config.output.output_dir,
            f"scan_{domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        report = {
            "scan_time": datetime.now().isoformat(),
            "domain": domain,
            "config": {
                "llm_provider": self.config.llm.provider,
                "min_profit_pct": self.config.scan.min_profit_pct,
                "min_liquidity": self.config.scan.min_liquidity,
                "min_confidence": self.config.scan.min_confidence
            },
            "opportunities_count": len(opportunities),
            "opportunities": [json_serialize(opp) for opp in opportunities]
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logging.info(f"[OK] 报告已保存到 {output_file}")
        print(f"      [OK] 报告已保存到 {output_file}")

    def _analyze_cluster_fully(self, cluster: List[Market]) -> List[ArbitrageOpportunity]:
        """
        [Phase 5.2] 批量分析语义聚类簇并提取机会
        """
        if len(cluster) < 2:
            return []

        cluster_id = f"cluster_{cluster[0].id[:8]}"
        results = self.analyzer.analyze_cluster(cluster_id, cluster)

        valid_opportunities = []
        market_map = {m.id: m for m in cluster}

        # 1. 处理点对点关系 (蕴含、等价、互斥)
        for rel in results.get("relationships", []):
            m_a = market_map.get(rel.get("market_a_id"))
            m_b = market_map.get(rel.get("market_b_id"))

            if not m_a or not m_b:
                continue

            # 构造基础机会对象
            relationship = rel.get("relationship", "unknown")
            tmp_opp = {
                "id": f"batch_{m_a.id}_{m_b.id}",
                "type": f"BATCH_{relationship}",
                "relationship": relationship,
                "markets": [
                    {"question": m_a.question, "id": m_a.id, "yes_price": m_a.yes_price},
                    {"question": m_b.question, "id": m_b.id, "yes_price": m_b.yes_price}
                ],
                "confidence": rel.get("confidence", 0.8),
                "reasoning": rel.get("reasoning", ""),
                "action": "执行套利",
                "edge_cases": [],
                "needs_review": ["批量分析识别", "请人工核实逻辑"]
            }

            # 调用已有的深度验证流程
            # 注意：我们需要模拟一个 ArbitrageOpportunity 对象结构
            class SimpleNamespace:
                def __init__(self, **kwargs):
                    self.__dict__.update(kwargs)

            validated_opp = self._validate_and_enrich_opportunity(SimpleNamespace(**tmp_opp), cluster)
            if validated_opp:
                valid_opportunities.append(validated_opp)

        # 2. 处理组合/合成机会 (完备集等)
        for sync_opp in results.get("synthetic_opportunities", []):
            involved_ids = sync_opp.get("market_ids", [])
            involved_markets = [market_map[mid] for mid in involved_ids if mid in market_map]

            if len(involved_markets) < 2:
                continue

            # 特殊处理完备集
            if sync_opp.get("type") == "EXHAUSTIVE_SET":
                from datetime import datetime
                # 使用 MathValidator 验证完备集
                math_report = self.validation_engine.math_validator.validate_exhaustive_set(
                    [MarketData(id=m.id, question=m.question, yes_price=m.yes_price, no_price=m.no_price,
                                liquidity=m.liquidity, end_date=m.end_date, best_ask=m.best_ask)
                     for m in involved_markets]
                )

                if math_report.is_valid():
                    final_opp = ArbitrageOpportunity(
                        id=f"sync_{datetime.now().strftime('%H%M%S')}",
                        type="BATCH_EXHAUSTIVE_SET",
                        relationship="exhaustive",
                        markets=[{"question": m.question, "id": m.id, "yes_price": m.yes_price} for m in involved_markets],
                        confidence=0.9,
                        total_cost=math_report.total_cost,
                        guaranteed_return=1.0,
                        profit=math_report.expected_profit,
                        profit_pct=math_report.profit_pct,
                        action=sync_opp.get("action", "买入全集"),
                        reasoning=sync_opp.get("logic", ""),
                        edge_cases=[],
                        needs_review=["验证完备性", "检查结算规则"],
                        timestamp=datetime.now().isoformat(),
                        apy=self.validation_engine.apy_calculator.calculate_apy(
                            math_report.profit_pct,
                            self.validation_engine.apy_calculator.calculate_days_to_resolution(involved_markets[0].end_date)
                        )
                    )
                    valid_opportunities.append(final_opp)

        return valid_opportunities

    def _validate_and_enrich_opportunity(self, opp: Any, markets: List[Market]) -> Optional[ArbitrageOpportunity]:
        """
        使用 ValidationEngine 对发现的机会执行深度验证并补充字段
        支持 MonotonicityViolation 和标准的 ArbitrageOpportunity
        """
        try:
            involved_markets = []
            relationship = "unknown"

            # 1. 识别并提取涉及的市场对象 (Phase 4 兼容性增强)
            if hasattr(opp, 'low_market') and hasattr(opp, 'high_market'):
                # 处理单调性策略的 MonotonicityViolation 对象
                involved_markets = [opp.low_market.market, opp.high_market.market]
                if getattr(opp, 'violation_type', '') == "temporal":
                    relationship = "IMPLIES_AB"
                else:
                    dir_val = opp.direction.value if hasattr(opp.direction, 'value') else str(opp.direction)
                    relationship = "IMPLIES_BA" if dir_val == "above" else "IMPLIES_AB"
            elif hasattr(opp, 'markets') and isinstance(opp.markets, list):
                # 处理已包装好的机会对象
                involved_questions = [m.get('question', '') if isinstance(m, dict) else getattr(m, 'question', '') for m in opp.markets]
                involved_markets = [m for m in markets if m.question in involved_questions]
                relationship = getattr(opp, 'relationship', 'unknown')

            if len(involved_markets) < 2:
                return opp if isinstance(opp, ArbitrageOpportunity) else None

            # 🆕 [Phase 8] 注入 WebSocket 实时价格
            # 在验证前，优先使用 WS 缓存中的盘口数据覆盖旧的 REST API 数据
            for m in involved_markets:
                if m.token_id:
                    ws_price = self.ws_client.cache.get_price(m.token_id)
                    if ws_price:
                        m.best_bid = ws_price["best_bid"]
                        m.best_ask = ws_price["best_ask"]
                if m.no_token_id:
                    ws_price_no = self.ws_client.cache.get_price(m.no_token_id)
                    if ws_price_no:
                        m.best_bid_no = ws_price_no["best_bid"]
                        m.best_ask_no = ws_price_no["best_ask"]

            # 2. 执行五层验证 (Layer 2-4)
            target_size = getattr(self.config.scan, 'target_size_usd', 500.0)
            v_result = self.validation_engine.validate_all_layers(
                involved_markets,
                relationship,
                target_size_usd=target_size
            )

            # 如果深度验证未通过，过滤掉该机会
            if not v_result["passed"]:
                logging.info(f"[REJECTED] {v_result['rejection_layer']}: {v_result['reason']}")
                return None

            # 3. 构造或更新标准 ArbitrageOpportunity 对象 (Phase 4 核心转换)
            if not isinstance(opp, ArbitrageOpportunity):
                # 从违背对象转换为标准机会格式，包含执行引擎需要的 token_id
                opp = ArbitrageOpportunity(
                    id=getattr(opp, 'id', f"opp_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"),
                    type=getattr(opp, 'type', 'MONOTONICITY_VIOLATION'),
                    relationship=relationship,
                    markets=[{
                        "question": m.question,
                        "id": m.id,
                        "yes_price": m.yes_price,
                        "token_id": getattr(m, 'token_id', ''),
                        "no_token_id": getattr(m, 'no_token_id', '')
                    } for m in involved_markets],
                    confidence=getattr(opp, 'confidence', 1.0),
                    total_cost=v_result["metrics"].get("total_cost", 0.0),
                    guaranteed_return=1.0,
                    profit=v_result["metrics"].get("expected_profit", 0.0),
                    profit_pct=v_result["metrics"].get("profit_pct", 0.0),
                    action=getattr(opp, 'action', "执行对冲套利"),
                    reasoning=getattr(opp, 'reasoning', v_result["reason"]),
                    edge_cases=getattr(opp, 'edge_cases', []),
                    needs_review=getattr(opp, 'needs_review', ["验证逻辑关系", "检查结算规则"]),
                    timestamp=datetime.now().isoformat()
                )

            # 4. 填充 11 个风控字段 (Phase 2.5)
            metrics = v_result.get("metrics", {})
            opp.oracle_alignment = metrics.get("oracle_alignment", "UNKNOWN")
            opp.days_to_resolution = metrics.get("days_to_resolution", 0)
            opp.apy = metrics.get("apy", 0.0)
            opp.apy_rating = metrics.get("apy_rating", "N/A")

            # 利润与滑点度量
            opp.mid_price_profit = getattr(opp, 'profit', 0.0)
            opp.effective_profit = metrics.get("expected_profit", 0.0)
            opp.slippage_cost = metrics.get("slippage_estimate", 0.0) * target_size / 100

            # 资金容量与 Gas 估算
            liquidity_list = [m.liquidity for m in involved_markets if hasattr(m, 'liquidity')]
            opp.max_position_usd = min(liquidity_list) * 0.1 if liquidity_list else 0.0
            opp.gas_estimate = 0.5  # 预估 Polygon 链执行成本

            opp.validation_results = v_result

            # 5. 生成复核清单 (Layer 5)
            checklist_content = self.validation_engine.generate_human_checklist(opp)
            checklist_dir = Path(self.config.output.output_dir) / "checklists"
            checklist_dir.mkdir(parents=True, exist_ok=True)
            checklist_path = checklist_dir / f"checklist_{opp.id}.md"

            with open(checklist_path, "w", encoding="utf-8") as f:
                f.write(checklist_content)

            opp.checklist_path = str(checklist_path)
            logging.info(f"[VALIDATED] 机会 {opp.id} 通过深度验证，APY: {opp.apy:.1f}%")

            # ✅ 触发实时推送 (Phase 3.3)
            if hasattr(self, 'notifier'):
                self.notifier.send_notification(opp)

            return opp
        except Exception as e:
            logging.error(f"验证机会时出错: {e}")
            traceback.print_exc()
            return opp if isinstance(opp, ArbitrageOpportunity) else None

    def sync_settlements(self):
        """
        [Phase 4.8] 同步已完成交易的结算状态并计算实际 PnL
        """
        print("\n" + "=" * 65)
        print("[SETTLEMENT] 正在同步交易结算状态...")
        print("=" * 65)

        pending = self.recorder.get_pending_settlements()
        if not pending:
            print("  暂无待结算的交易记录。")
            return

        print(f"  发现 {len(pending)} 条待处理记录。")

        updated_count = 0
        for exec_rec in pending:
            exec_id = exec_rec['exec_id']
            opp_id = exec_rec['opp_id']
            details = json.loads(exec_rec['details_json'] or '{}')
            instructions = details.get('instructions', [])

            if not instructions:
                continue

            all_resolved = True
            total_return = 0.0
            results_summary = []

            print(f"\n  检查执行 ID: {exec_id[:8]}... (机会: {opp_id})")

            for inst in instructions:
                market_id = inst.get('market_id') or inst.get('id') # 兼容不同格式
                if not market_id:
                    # 尝试从问题描述反查 (保底)
                    continue

                market_data = self.client.get_market_details(market_id)
                if not market_data:
                    all_resolved = False
                    break

                # 检查市场是否已结算
                # Polymarket API: status="closed" 或 "resolved"
                status = market_data.get('status', '').lower()
                if status not in ['closed', 'resolved']:
                    all_resolved = False
                    print(f"    - 市场尚未结算: {inst.get('market')[:40]}...")
                    break

                # 获取中奖结果
                winning_outcome = market_data.get('winningOutcome')
                if winning_outcome is None:
                    all_resolved = False
                    print(f"    - 市场已关闭但尚未公布结果: {inst.get('market')[:40]}...")
                    break

                # 计算该笔订单的收益
                # 我们假设目前只处理 YES 合约买入 (instructions 中 token="YES")
                is_win = False
                if inst.get('token') == "YES" and winning_outcome == "0": # 0 通常是 YES
                    is_win = True
                elif inst.get('token') == "NO" and winning_outcome == "1": # 1 通常是 NO
                    is_win = True

                leg_return = 1.0 if is_win else 0.0
                total_return += leg_return
                results_summary.append({
                    "market": inst.get('market'),
                    "outcome": winning_outcome,
                    "is_win": is_win,
                    "return": leg_return
                })
                print(f"    - {'[WIN]' if is_win else '[LOSS]'} {inst.get('market')[:40]}...")

            if all_resolved:
                # 计算 realized PnL
                # PnL = Total Return - Total Cost
                # 注意: total_cost_usd 在数据库中存的是组合总成本
                realized_pnl = total_return - exec_rec['total_cost_usd']

                # 更新数据库
                self.recorder.update_execution(exec_id, "SETTLED", {
                    "settlement_details": results_summary,
                    "total_return": total_return,
                    "realized_pnl": realized_pnl,
                    "settled_at": datetime.now(timezone.utc).isoformat()
                })

                # 同时更新 realizes_pnl 专用字段
                try:
                    with sqlite3.connect(self.recorder.db_path) as conn:
                        conn.execute(
                            "UPDATE execution_history SET realized_pnl = ?, settled_at = ? WHERE exec_id = ?",
                            (realized_pnl, datetime.now(timezone.utc).isoformat(), exec_id)
                        )
                except Exception as e:
                    logging.error(f"更新结算字段失败: {e}")

                print(f"  [OK] 结算完成! PnL: ${realized_pnl:.4f} USD")
                updated_count += 1

        print(f"\n  同步结束，已更新 {updated_count} 条记录。")
        print("=" * 65 + "\n")

    def _on_opportunity_found(
        self,
        opp: ArbitrageOpportunity,
        opportunities: List[ArbitrageOpportunity]
    ) -> bool:
        """处理发现的套利机会

        统一处理机会发现时的逻辑：
        - DEBUG 模式：暂停等待用户确认
        - PRODUCTION 模式：自动收集所有机会

        Args:
            opp: 发现的套利机会
            opportunities: 机会列表（用于最终报告）

        Returns:
            True if scanning should continue, False to exit
        """
        # 始终收集到 discovered_opportunities（用于自动保存）
        self.discovered_opportunities.append(opp)

        if self.run_mode == RunMode.DEBUG:
            # DEBUG 模式：暂停确认
            return self._handle_opportunity_verification(opp, opportunities)
        else:
            # PRODUCTION 模式：自动添加到结果列表
            opportunities.append(opp)
            return True

    def _print_summary(self, opportunities: List[ArbitrageOpportunity]):
        """打印摘要"""
        print("\n" + "=" * 65)
        print("扫描结果摘要")
        print("=" * 65)

        if not opportunities:
            print("\n暂未发现符合条件的套利机会")
            print("这很正常——好机会不是时时都有\n")
            return

        print(f"\n[RESULT] 发现 {len(opportunities)} 个潜在套利机会:\n")

        for i, opp in enumerate(opportunities, 1):
            print(f"{'─' * 60}")
            print(f"机会 #{i}: {opp.type}")
            print(f"{'─' * 60}")

            # 🔥 显示核心风控度量 (Phase 2.5/3.5 增强)
            apy_val = getattr(opp, 'apy', 0.0)
            rating = getattr(opp, 'apy_rating', 'N/A')
            apy_str = f"{apy_val:.1f}% ({rating})"

            print(f"🔥 年化收益 (APY): {apy_str:25} 🎯 置信度: {opp.confidence:.0%}")
            print(f"💰 预期净利润: {opp.profit_pct:.2f}% ({opp.profit:.4f} USD)   ⏳ 预估锁仓: {getattr(opp, 'days_to_resolution', 0)} 天")
            print(f"📡 预言机对齐: {getattr(opp, 'oracle_alignment', 'UNKNOWN'):25} 🛡️ 滑点损失: {getattr(opp, 'slippage_cost', 0):.4f} USD")
            print(f"📈 建议最大仓位: ${getattr(opp, 'max_position_usd', 0):,.0f} USD")
            print(f"\n操作:")
            for line in opp.action.split('\n'):
                print(f"  {line}")

            # ✅ 新增：Polymarket 链接
            links = self._generate_polymarket_links(opp.markets)
            print(f"\n[Polymarket 链接:]")
            for j, (market, link) in enumerate(zip(opp.markets, links), 1):
                question = market.get('question', '')[:60]
                print(f"  {j}. {question}...")
                print(f"     {link}")

            # ✅ 新增：人工验证清单
            print(f"\n[WARNING] 人工验证清单:")
            print(f"  [ ] 验证逻辑关系是否正确: {opp.type}")
            print(f"  [ ] 检查结算规则是否兼容")

            # 如果有两个市场，显示结算时间对比
            if len(opp.markets) >= 2:
                market_1 = opp.markets[0]
                market_2 = opp.markets[1]
                print(f"  [ ] 在 Polymarket 上确认当前价格")
                print(f"  [ ] 检查流动性: ${market_1.get('yes_price', 0):.2f} vs ${market_2.get('yes_price', 0):.2f}")
            print(f"  [ ] 检查是否有特殊规则（如提前结算）")
            print(f"  [ ] 验证 LLM 分析的合理性")

            # 原有的 needs_review 内容
            if opp.needs_review:
                print(f"\n[NOTE] 额外注意事项:")
                for item in opp.needs_review:
                    print(f"  • {item}")

            print()

    # ============================================================
    # 🆕 验证模式相关方法
    # ============================================================

    def _print_opportunity_detailed(self, opp: ArbitrageOpportunity) -> None:
        """
        打印套利机会的完整详细信息（验证模式）

        Args:
            opp: 套利机会对象
        """
        self.opportunity_counter += 1

        print("\n" + "=" * 60)
        print(f"[套利机会 #{self.opportunity_counter}] {opp.type}")
        print("=" * 60)

        # 【市场信息】
        print("\n[市场信息]")
        print("-" * 60)
        links = self._generate_polymarket_links(opp.markets)

        for i, (market, link) in enumerate(zip(opp.markets, links), 1):
            role = f"市场 {chr(64+i)}"  # A, B, C...
            print(f"{role}:")
            print(f"  问题: {market.get('question', '')}")
            print(f"  YES价格: ${market.get('yes_price', 0):.4f} (ask: ${market.get('best_ask', 0):.4f})")
            print(f"  NO价格:  ${market.get('no_price', 0):.4f} (bid: ${market.get('best_bid', 0):.4f})")
            print(f"  流动性:  ${market.get('liquidity', 0):,.0f} USDC")
            end_date = market.get('end_date', 'N/A')
            if end_date and end_date != 'N/A':
                end_date = end_date[:10] if 'T' in end_date else end_date
            print(f"  结算:   {end_date}")
            print(f"  链接:   {link}")
            print()

        # 【套利详情】
        print("[套利详情]")
        print("-" * 60)
        print(f"逻辑关系: {opp.relationship}")
        print(f"置信度:   {opp.confidence:.0%}")
        print(f"利润率:   {opp.profit_pct:.2f}%")
        print(f"\n操作:")
        for line in opp.action.split('\n'):
            print(f"  {line}")

        # 【LLM 完整推理】
        if opp.reasoning:
            print("\n[LLM 完整推理]")
            print("-" * 60)
            # 限制推理长度，避免输出过长
            reasoning = opp.reasoning
            if len(reasoning) > 2000:
                reasoning = reasoning[:2000] + "\n... (推理内容过长，已截断)"
            print(reasoning)

        # 【风险提示】
        print("\n[风险提示]")
        print("-" * 60)
        for item in opp.needs_review:
            print(f"  - {item}")

        if opp.edge_cases:
            print("\nEdge Cases:")
            for case in opp.edge_cases:
                print(f"  - {case}")

        print("=" * 60)

    def _handle_opportunity_verification(
        self,
        opp: ArbitrageOpportunity,
        opportunities: List[ArbitrageOpportunity]
    ) -> bool:
        """
        处理套利机会的验证流程（交互式）

        Args:
            opp: 发现的套利机会
            opportunities: 机会列表（用于保存）

        Returns:
            True if scanning should continue, False to exit
        """
        # 注意：机会已在 _on_opportunity_found 中添加到 discovered_opportunities

        # 打印详细信息
        self._print_opportunity_detailed(opp)

        while True:
            try:
                choice = input(
                    "\n[验证模式] 操作 (Enter=继续,s=保存,e=执行(MOCK),f=误报,q=退出,d=详情,r=阈值,l=流动性,j=存文件,?=帮助): "
                ).strip().lower()

                if not choice or choice == 'enter':
                    print("  -> 跳过此机会，继续扫描...")
                    return True

                elif choice == 's':
                    opportunities.append(opp)
                    print("  -> 已保存到结果列表，继续扫描...")
                    return True

                elif choice == 'e':
                    # ✅ 执行 Layer 6 终极验证与模拟执行 (Phase 4)
                    check = self.execution_engine.pre_flight_check(opp)
                    if check["can_execute"]:
                        print(f"  [OK] Layer 6 验证通过: {check['reason']}")
                        log_path = self.execution_engine.execute_mock(opp, check["instructions"])
                        print(f"  🚀 模拟执行成功! 日志: {log_path}")
                    else:
                        print(f"  [REJECTED] Layer 6 验证失败: {check['reason']}")
                    continue

                elif choice == 'f':
                    reason = input("  -> 请输入误报原因: ").strip()
                    self.false_positive_log.append({
                        'opportunity': json_serialize(opp),
                        'reason': reason,
                        'timestamp': datetime.now().isoformat()
                    })
                    print("  -> 已记录为误报，继续扫描...")
                    return True

                elif choice == 'q':
                    print("  -> 退出扫描...")
                    return False

                elif choice == 'd':
                    # 显示更多调试信息
                    print("\n[调试详情]")
                    print(f"  ID: {opp.id}")
                    print(f"  总成本: ${opp.total_cost:.4f}")
                    print(f"  保证回报: ${opp.guaranteed_return:.4f}")
                    print(f"  时间戳: {opp.timestamp}")
                    if opp.edge_cases:
                        print(f"  边界情况: {opp.edge_cases}")
                    continue

                elif choice == 'r':
                    new_threshold = input(f"  -> 当前利润率阈值={self.config.scan.min_profit_pct:.1%}，新阈值: ").strip()
                    try:
                        self.config.scan.min_profit_pct = float(new_threshold)
                        print(f"  -> 阈值已更新为 {self.config.scan.min_profit_pct:.1%}")
                    except ValueError:
                        print("  -> 无效输入")
                    continue

                elif choice == 'l':
                    new_liquidity = input(f"  -> 当前最小流动性=${self.config.scan.min_liquidity:,.0f}，新值: ").strip()
                    try:
                        self.config.scan.min_liquidity = float(new_liquidity)
                        print(f"  -> 流动性阈值已更新为 ${self.config.scan.min_liquidity:,.0f}")
                    except ValueError:
                        print("  -> 无效输入")
                    continue

                elif choice == 'j':
                    filename = f"opportunity_{opp.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    filepath = Path(self.config.output.output_dir) / filename
                    filepath.parent.mkdir(parents=True, exist_ok=True)
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(json_serialize(opp), f, indent=2, ensure_ascii=False)
                    print(f"  -> 已保存到 {filepath}")
                    continue

                elif choice == '?':
                    print("\n[命令帮助]")
                    print("  Enter - 继续扫描（不保存此机会）")
                    print("  s    - 保存此机会到结果列表")
                    print("  f    - 标记为误报并记录原因")
                    print("  q    - 退出扫描")
                    print("  d    - 显示更多调试详情")
                    print("  r    - 调整最小利润率阈值")
                    print("  l    - 调整最小流动性阈值")
                    print("  j    - 保存此机会到单独JSON文件")
                    print("  ?    - 显示此帮助")
                    continue

                else:
                    print("  -> 未知命令，输入 ? 查看帮助")
                    continue

            except KeyboardInterrupt:
                print("\n  -> 检测到 Ctrl+C，退出扫描...")
                return False
            except EOFError:
                print("\n  -> 检测到 EOF，退出扫描...")
                return False

    def _show_execution_stats(self):
        """
        [Phase 4.6/4.7/4.8] 显示交易执行统计和 PnL 数据
        """
        stats = self.recorder.get_execution_stats()

        print("\n" + "=" * 65)
        print("[STATS] 交易执行与收益统计 (PnL Dashboard)")
        print("=" * 65)

        if stats["total_count"] == 0:
            print("\n暂无历史执行记录。")
            return

        # 1. 规模统计
        print(f"\n[规模统计]")
        print(f"  总执行尝试: {stats['total_count']} (MOCK: {stats['mock_count']}, REAL: {stats['real_count']})")
        print(f"  Layer 6 拦截: {stats['rejected_l6_count']} (价格变动导致拒绝)")
        print(f"  已结算交易: {stats['settled_count']}")

        success_color = "\033[92m" if stats['success_rate'] > 80 else "\033[93m"
        reset_color = "\033[0m"
        print(f"  执行成功率: {success_color}{stats['success_rate']:.1f}%{reset_color} (不含 L6 拦截)")

        # 2. 收益统计
        print(f"\n[收益统计]")
        print(f"  累计投入本金: ${stats['total_cost_usd']:.2f} USD")
        print(f"  预期总利润:   ${stats['total_expected_profit_usd']:.2f} USD")

        pnl_color = "\033[92m" if stats['realized_pnl_usd'] > 0 else ("\033[91m" if stats['realized_pnl_usd'] < 0 else "")
        print(f"\n  已实现净损益 (Realized): {pnl_color}${stats['realized_pnl_usd']:.4f} USD{reset_color}")

        pending_color = "\033[94m" # Blue for pending
        print(f"  待结算预估 (Pending):  {pending_color}${stats['pending_pnl_usd']:.4f} USD{reset_color}")

        if stats['total_cost_usd'] > 0:
            total_pnl = stats['realized_pnl_usd'] + stats['pending_pnl_usd']
            roi = (total_pnl / stats['total_cost_usd']) * 100
            print(f"  综合投资回报 (ROI):    {pnl_color}{roi:.2f}%{reset_color}")

        print("\n" + "=" * 65 + "\n")

    def _save_false_positive_log(self) -> None:
        """保存误报日志到文件"""
        if self.run_mode == RunMode.DEBUG and self.false_positive_log:
            false_positive_file = Path(self.config.output.output_dir) / f"false_positives_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            false_positive_file.parent.mkdir(parents=True, exist_ok=True)
            with open(false_positive_file, 'w', encoding='utf-8') as f:
                json.dump(self.false_positive_log, f, indent=2, ensure_ascii=False)
            print(f"\n[OK] 误报日志已保存: {false_positive_file}")

    def _save_discovered_opportunities(self) -> None:
        """保存所有发现的机会

        - PRODUCTION 模式：自动保存所有机会
        - DEBUG 模式：不自动保存
        """
        should_save = self.run_mode == RunMode.PRODUCTION

        if should_save and self.discovered_opportunities:
            filename = f"discovered_opportunities_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = Path(self.config.output.output_dir) / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump([json_serialize(opp) for opp in self.discovered_opportunities], f, indent=2, ensure_ascii=False)
            print(f"\n[OK] 所有发现的机会已保存: {filepath}")

    def close(self):
        """清理资源"""
        self.analyzer.close()


# ============================================================
# 主程序入口
# ============================================================

def main():
    """主程序"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="Polymarket组合套利扫描系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础扫描（向量化模式）
  python local_scanner_v2.py --domain crypto

  # 使用特定策略扫描
  python local_scanner_v2.py --domain crypto --strategies monotonicity
  python local_scanner_v2.py -d crypto --strategies monotonicity,exhaustive --subcat btc,eth

  # 使用特定LLM配置
  python local_scanner_v2.py --profile siliconflow
  python local_scanner_v2.py --profile deepseek --model deepseek-reasoner

  # 使用指定策略
  python local_scanner_v2.py --strategies monotonicity,interval
  python local_scanner_v2.py --list-strategies  # 查看所有可用策略

查看所有可用配置:
  python llm_config.py --list
        """
    )
    parser.add_argument(
        "--profile", "-p",
        type=str,
        help="LLM配置名称 (如: siliconflow, deepseek, ollama, openai)"
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        help="覆盖默认模型 (如: Qwen/Qwen2.5-72B-Instruct)"
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        help="配置文件路径"
    )
    parser.add_argument(
        "--min-profit",
        type=float,
        help="最小利润百分比 (默认: 2.0)"
    )
    parser.add_argument(
        "--min-apy",
        type=float,
        help="最小年化收益率门槛 (默认: 15.0)"
    )
    parser.add_argument(
        "--target-size",
        type=float,
        help="模拟交易规模 USD (默认: 500.0)"
    )
    parser.add_argument(
        "--show-stats",
        action="store_true",
        help="显示历史交易执行统计和收益数据 (PnL)"
    )
    parser.add_argument(
        "--sync-settlements",
        action="store_true",
        help="同步已完成交易的结算状态并更新 PnL"
    )
    parser.add_argument(
        "--sensitivity-analysis",
        action="store_true",
        help="运行灵敏度分析，测试不同利润阈值对收益的影响 (Phase 5.1)"
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="以守护进程模式运行，持续监控并推送通知 (Phase 9)"
    )
    parser.add_argument(
        "--market-limit",
        type=int,
        help="获取市场数量 (默认: 200)"
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="列出所有可用的LLM配置"
    )

    parser.add_argument(
        "--domain", "-d",
        type=str,
        default="crypto",
        choices=["crypto", "politics", "sports", "other"],
        help="市场领域 (默认: crypto)"
    )
    # 🆕 动态分类控制 (v3.1新增)
    parser.add_argument(
        "--use-dynamic-categories",
        action="store_true",
        help="启用 LLM 动态分类发现"
    )
    parser.add_argument(
        "--list-categories",
        action="store_true",
        help="列出所有已发现的市场分类"
    )
    # 🆕 子类别筛选参数（v2.1新增）
    parser.add_argument(
        "--subcat",
        type=str,
        help="子类别筛选 (逗号分隔，如: btc,eth 或 bitcoin,ethereum)。支持简写，如btc→bitcoin"
    )
    parser.add_argument(
        "--list-subcats",
        action="store_true",
        help="列出指定领域的所有可用子类别"
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="禁用交互式菜单，直接使用默认配置"
    )

    # 🆕 回测参数 (Phase 6.3)
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="运行历史回测模式 (使用本地数据库)"
    )
    parser.add_argument(
        "--date",
        type=str,
        help="回测指定日期 (YYYY-MM-DD)，默认全部"
    )

    # 🆕 缓存控制参数（v2.1新增）
    parser.add_argument(
        "--refresh", "-r",
        action="store_true",
        help="强制刷新缓存，重新获取市场数据"
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="明确指定使用缓存（如果缓存有效）"
    )

    # 🆕 运行模式参数（v2.2新增）
    parser.add_argument(
        "--mode",
        type=str,
        choices=["debug", "production"],
        help="运行模式 (debug=暂停确认, production=自动保存)"
    )

    # 🆕 策略选择参数（v3.1新增）
    parser.add_argument(
        "--strategies",
        type=str,
        help="选择套利策略（逗号分隔），如: monotonicity,exhaustive,implication,equivalent,interval。默认: 全部"
    )
    # 🆕 高频模式参数 (Phase 5.3)
    parser.add_argument(
        "--loop",
        action="store_true",
        help="启用持续扫描模式"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="两次扫描之间的间隔秒数 (默认: 300)"
    )
    parser.add_argument(
        "--list-strategies",
        action="store_true",
        help="列出所有可用的套利策略"
    )

    # 🆕 Tag分类管理参数（v3.2新增）
    parser.add_argument(
        "--refine-other",
        action="store_true",
        help="细分Other分类（对已标记为other的tags进行二次分类到finance/tech/entertainment/science/weather/misc）"
    )

    args = parser.parse_args()

    # ============================================================
    # 🆕 列出可用策略（v3.1新增）
    # ============================================================
    if args.list_strategies:
        if CLI_AVAILABLE and StrategyRegistry:
            print("\n=== 可用的套利策略 ===\n")
            all_strategies = StrategyRegistry.get_all()
            for s in all_strategies:
                risk_str = s.risk_level.value if hasattr(s.risk_level, 'value') else s.risk_level
                llm_str = "是" if s.requires_llm else "否"
                domains_str = ", ".join(s.domains)
                print(f"  ID: {s.id}")
                print(f"    名称: {s.name} ({s.name_en})")
                print(f"    描述: {s.description}")
                print(f"    优先级: {s.priority} | 需要LLM: {llm_str} | 风险: {risk_str.upper()}")
                print(f"    适用领域: {domains_str}")
                print(f"    最低利润: {s.min_profit_threshold}%")
                print()
            print(f"共 {len(all_strategies)} 个策略可用")
            print("\n使用 --strategies 参数选择策略，如:")
            print("  python local_scanner_v2.py --strategies monotonicity,exhaustive")
            return 0
        else:
            print("[ERROR] CLI 模块不可用，无法列出策略")
            print("       请确保已安装 rich 和 questionary: pip install -r requirements.txt")
            return 1

    # ============================================================
    # 🆕 细分Other分类 (v3.2新增)
    # ============================================================
    if args.refine_other:
        try:
            from cli.tag_classifier import classify_tags_interactive
            print("\n=== 细分Other分类 ===\n")
            print("将other类别的tags重新分类到细分类别：")
            print("  - finance (传统金融)")
            print("  - tech (科技/AI)")
            print("  - entertainment (娱乐/文化)")
            print("  - science (科学/研究)")
            print("  - weather (天气/自然)")
            print("  - misc (杂项)")
            print()

            success = classify_tags_interactive(
                menu=None,
                llm_profile=args.profile,
                mode='refine'  # 传入refine模式
            )
            return 0 if success else 1
        except Exception as e:
            print(f"[ERROR] 细分分类失败: {e}")
            import traceback
            traceback.print_exc()
            return 1

    # ============================================================
    # 🆕 列出已发现分类 (v3.1新增)
    # ============================================================
    if args.list_categories:
        # 加载配置
        config = AppConfig.load(args.config)
        scanner = ArbitrageScanner(config, profile_name=args.profile)
        # 强制启用动态分类以便加载/发现
        scanner.use_dynamic_categories = True
        categories = scanner.get_available_categories()

        print("\n=== 已发现的市场分类 ===\n")
        if not categories:
            print("  [提示] 尚未发现任何动态分类。请运行扫描并启用 --use-dynamic-categories。")
        else:
            for i, cat in enumerate(categories, 1):
                icon = cat.icon or "📁"
                print(f"  {i:2d}. {icon} {cat.name_zh} ({cat.name_en})")
                print(f"      描述: {cat.description}")
                print(f"      市场数: {cat.market_count} | 置信度: {cat.discovery_confidence:.0%}")
                print(f"      Tags: {', '.join(cat.representative_tags)}")
                print()
            print(f"共 {len(categories)} 个分类可用")
        return 0

    # ============================================================
    # 🆕 显示交易执行统计（Phase 4.6/4.7 新增）
    # ============================================================
    if getattr(args, 'show_stats', False):
        config = AppConfig.load(args.config)
        scanner = ArbitrageScanner(config, profile_name=args.profile)
        scanner._show_execution_stats()
        return 0

    # ============================================================
    # 🆕 守护进程模式 (Phase 9)
    # ============================================================
    if getattr(args, 'daemon', False):
        print("[INFO] 启动守护进程模式 (Daemon Mode)...")
        print("按 Ctrl+C 停止")

        try:
            config = AppConfig.load(args.config)
            scanner = ArbitrageScanner(config, profile_name=args.profile)

            # 启动 WebSocket (如果配置允许)
            # 在全自动模式下，我们默认订阅热门资产或全部发现的资产
            # 这里先执行一次全量扫描来初始化订阅列表
            print("[DAEMON] 执行初始全量扫描...")
            scanner.scan_semantic(
                domain=args.domain,
                subcategories=args.subcat.split(",") if args.subcat else None
            )

            print(f"[DAEMON] 进入持续监控循环 (间隔: {config.scan.scan_interval}s)...")

            while True:
                time.sleep(config.scan.scan_interval)
                print(f"\n[DAEMON] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 开始定期扫描...")

                # 重新扫描以发现新市场
                scanner.scan_semantic(
                    domain=args.domain,
                    subcategories=args.subcat.split(",") if args.subcat else None
                )

        except KeyboardInterrupt:
            print("\n[DAEMON] 接收到停止信号，正在退出...")
            if hasattr(scanner, 'stop_websocket'):
                scanner.stop_websocket()
        except Exception as e:
            logging.error(f"[DAEMON] 发生严重错误: {e}")
            traceback.print_exc()
            return 1

        return 0

    # ============================================================
    # 🆕 灵敏度分析（Phase 5.1 新增）
    # ============================================================
    if getattr(args, 'sensitivity_analysis', False):
        config = AppConfig.load(args.config)
        scanner = ArbitrageScanner(config, profile_name=args.profile)
        engine = BacktestEngine(scanner)

        # 确定时间范围（默认回测最近 24 小时）
        ts = engine.get_available_timestamps()
        if not ts:
            print("[ERROR] 数据库为空，无法进行灵敏度分析。请先运行扫描积累数据。")
            return 1

        end_time = ts[-1]
        start_time = (datetime.fromisoformat(end_time) - timedelta(days=1)).isoformat()

        # 定义测试阈值列表
        thresholds = [0.005, 0.01, 0.015, 0.02, 0.03, 0.05]

        engine.run_sensitivity_analysis(start_time, end_time, thresholds)
        return 0

    # ============================================================
    # 🆕 同步结算状态（Phase 4.8 新增）
    # ============================================================
    if getattr(args, 'sync_settlements', False):
        config = AppConfig.load(args.config)
        scanner = ArbitrageScanner(config, profile_name=args.profile)
        scanner.sync_settlements()
        return 0

    # ============================================================
    # 🆕 列出子类别（v2.1新增）- 需要在交互式选择之前处理
    # ============================================================
    if args.list_subcats:
        # 直接读取tag_categories.json
        tag_categories_file = Path(__file__).parent / "data" / "tag_categories.json"
        if tag_categories_file.exists():
            with open(tag_categories_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            print(f"[ERROR] 标签分类文件不存在: {tag_categories_file}")
            return 1

        # 优先显示分组
        groups = data.get("groups", {}).get(args.domain, {})
        if groups:
            print(f"\n=== {args.domain.upper()} 子类别分组 ===\n")
            for group_name, tags in groups.items():
                print(f"[{group_name}] ({len(tags)}个标签):")
                for tag in sorted(tags):
                    print(f"   - {tag}")
                print()

            all_tags = data.get("categories", {}).get(args.domain, [])
            print(f"共 {len(all_tags)} 个标签，已分为 {len(groups)} 个分组")

            print("\n提示: 在交互模式中选择分组后，会自动包含该分组下的所有标签")
            print("      CLI模式可使用: --subcat bitcoin,ethereum")
        elif args.domain in data.get("categories", {}):
            print(f"\n=== {args.domain.upper()} 可用子类别 ===")
            subcats = sorted(data["categories"][args.domain])
            print(f"共 {len(subcats)} 个子类别:\n")
            for i, subcat in enumerate(subcats, 1):
                print(f"  {i:2d}. {subcat}")
            print("\n提示: 可使用简写，如 btc→bitcoin、eth→ethereum")
            print("      使用 --subcat 参数进行筛选，如: --subcat bitcoin,ethereum")
        else:
            print(f"[ERROR] 领域 '{args.domain}' 没有可用的子类别")
            return 1
        return 0

    # ============================================================
    # 🆕 交互式配置收集（v3.1重构）
    # ============================================================
    # 确定是否使用新的交互式菜单
    use_new_menu = CLI_AVAILABLE and not args.no_interactive and not getattr(args, 'backtest', False)

    # 初始化输出
    if use_new_menu:
        output = ScannerOutput()
        output.welcome("v3.1")
    else:
        output = None

    # 确定要扫描的领域
    domain = args.domain  # 默认为 "crypto"

    if use_new_menu:
        # 创建持久的菜单对象（整个会话共享，保存LLM配置等状态）
        menu = InteractiveMenu()

        # 🆕 显示当前LLM配置（v3.3新增）
        menu.display_current_llm_config()

        # 使用新的交互式菜单（循环处理，支持连续操作）
        while True:
            action = menu.main_menu()
            if action == "exit":
                print("[INFO] 退出程序")
                return 0
            elif action == "help":
                menu.show_help()
                # 继续循环，显示主菜单
                continue
            elif action == "classify_tags":
                # Tags智能分类（会使用menu中保存的LLM配置）
                menu.tags_classify_menu()
                # 继续循环，显示主菜单
                continue
            elif action == "config":
                # TODO: 实现配置菜单
                print("[INFO] 配置菜单功能待实现")
                # 继续循环，显示主菜单
                continue
            elif action == "llm_config":
                # 处理LLM配置选择
                llm_config_result = menu.select_llm_profile()

                if llm_config_result:
                    selected_profile = llm_config_result.get('profile', 'unknown')
                    selected_model = llm_config_result.get('model', 'default')
                    print(f"[green]✓ 已选择LLM配置: {selected_profile} - {selected_model}[/green]")
                    print("[dim]提示: 本次会话将使用此配置[/dim]")
                else:
                    print("[yellow]⚠ 未选择LLM配置，使用默认配置[/yellow]")

                # 继续循环，显示主菜单
                continue
            elif action == "sensitivity_analysis":
                # 运行灵敏度分析
                try:
                    app_config = AppConfig.load(args.config)
                    scanner = ArbitrageScanner(app_config, profile_name=args.profile)
                    engine = BacktestEngine(scanner)

                    ts = engine.get_available_timestamps()
                    if not ts:
                        print("[ERROR] 数据库为空，无法进行灵敏度分析。请先运行扫描积累数据。")
                        input("\n按回车键返回主菜单...")
                        continue

                    # 默认最近 24 小时
                    end_time = ts[-1]
                    start_time = (datetime.fromisoformat(end_time.replace('Z', '+00:00')) - timedelta(days=1)).isoformat()

                    # 提示用户确认时间范围或使用默认
                    print(f"\n[INFO] 灵敏度分析时间范围: {start_time} -> {end_time}")
                    confirm = input("是否以此范围运行? (y=是, n=进入回测菜单自定义, 直接回车=y): ").strip().lower()

                    if confirm == 'n':
                        print("  -> 请在 '历史回测' 菜单中自定义高级参数。")
                        input("\n按回车键返回主菜单...")
                        continue

                    thresholds = [0.005, 0.01, 0.015, 0.02, 0.03, 0.05]
                    engine.run_sensitivity_analysis(start_time, end_time, thresholds)
                    input("\n按回车键返回主菜单...")
                except Exception as e:
                    print(f"[ERROR] 灵敏度分析执行失败: {e}")
                    import traceback
                    traceback.print_exc()
                    input("\n按回车键返回主菜单...")
                continue
            elif action == "sync_settlements":
                # 同步结算状态
                try:
                    app_config = AppConfig.load(args.config)
                    scanner = ArbitrageScanner(app_config, profile_name=args.profile)
                    scanner.sync_settlements()
                    input("\n按回车键返回主菜单...")
                except Exception as e:
                    print(f"[ERROR] 同步结算状态失败: {e}")
                    input("\n按回车键返回主菜单...")
                continue
            elif action == "stats":
                # 显示 PnL 统计数据
                try:
                    app_config = AppConfig.load(args.config)
                    scanner = ArbitrageScanner(app_config, profile_name=args.profile)
                    scanner._show_execution_stats()
                    input("\n按回车键返回主菜单...")
                except Exception as e:
                    print(f"[ERROR] 获取统计数据失败: {e}")
                    input("\n按回车键返回主菜单...")
                continue
            elif action == "backtest":
                # 收集回测配置
                bt_config = menu.gather_backtest_config()
                if not bt_config:
                    continue
                
                # 临时加载配置用于回测
                try:
                    # 加载基础配置
                    app_config = AppConfig.load(args.config)
                    
                    # 确定使用的 LLM Profile (优先使用菜单选择的，其次是命令行的)
                    profile_to_use = args.profile
                    model_to_use = args.model
                    
                    if menu.current_llm_profile:
                        profile_to_use = menu.current_llm_profile.get("profile")
                        model_to_use = menu.current_llm_profile.get("model")
                        
                    # 初始化扫描器
                    scanner = ArbitrageScanner(
                        app_config,
                        profile_name=profile_to_use,
                        model_override=model_to_use
                    )
                    
                    # 初始化回测引擎
                    engine = BacktestEngine(scanner)
                    
                    # 运行回测
                    engine.run_backtest(
                        start_time=bt_config["start_time"],
                        end_time=bt_config["end_time"],
                        strategies=bt_config["strategies"]
                    )
                    
                    input("\n按回车键返回主菜单...")
                except Exception as e:
                    print(f"[ERROR] 回测启动失败: {e}")
                    import traceback
                    traceback.print_exc()
                    input("\n按回车键返回主菜单...")
                
                continue
            elif action == "scan":
                # 开始扫描流程，跳出循环
                break
            else:
                print(f"[WARNING] 未知操作: {action}")
                return 0

        # action == "scan" 继续，稍后在初始化 scanner 后选择类别
        pass

    # 列出配置
    if args.list_profiles:
        from llm_config import LLMConfigManager, print_profiles_table
        manager = LLMConfigManager()
        print_profiles_table(manager.list_profiles())
        return 0

    # 加载配置
    config = AppConfig.load(args.config)

    # 覆盖配置
    if args.min_profit:
        config.scan.min_profit_pct = args.min_profit
    if hasattr(args, 'min_apy') and args.min_apy:
        config.scan.min_apy = args.min_apy
    if hasattr(args, 'target_size') and args.target_size:
        config.scan.target_size_usd = args.target_size
    if args.market_limit:
        config.scan.market_limit = args.market_limit

    # 确定最终使用的 profile_name
    # 优先级: 1. 交互菜单中选择的 (menu.current_llm_profile)
    #        2. 命令行参数 (args.profile)
    #        3. 配置文件中的 active_profile (config.active_profile)
    final_profile_name = args.profile
    final_model_override = args.model

    if use_new_menu:
        if menu.current_llm_profile:
            final_profile_name = menu.current_llm_profile
        if menu.current_llm_model:
            final_model_override = menu.current_llm_model

    # 如果仍为空，回退到配置文件的 active_profile
    if not final_profile_name and config.active_profile:
        final_profile_name = config.active_profile
        # 如果使用了 config.active_profile，也检查一下是否有对应的 model 配置
        # (ArbitrageScanner 内部会处理，但这里为了明确性可以不做)

    # 运行模式选择
    run_mode = None
    if args.mode:
        # 命令行明确指定模式
        run_mode = RunMode(args.mode)
        print(f"[INFO] 运行模式: {args.mode.upper()}")
    elif use_new_menu:
        # 使用新的交互式菜单选择模式
        run_mode_str = menu.select_run_mode()
        run_mode = RunMode(run_mode_str)

    if run_mode is None:
        # 默认：生产模式
        run_mode = RunMode.PRODUCTION
        print("[INFO] 运行模式: PRODUCTION (默认)")

    # 初始化扫描器
    scanner = ArbitrageScanner(
        config,
        profile_name=final_profile_name,
        model_override=final_model_override,
        run_mode=run_mode
    )

    # 🆕 回测模式入口 (Phase 6.3)
    if getattr(args, 'backtest', False):
        try:
            print("[INFO] 启动历史回测模式...")
            engine = BacktestEngine(scanner)

            # 确定回测时间范围
            target_date = getattr(args, 'date', None)
            if target_date:
                start_time = f"{target_date}T00:00:00"
                end_time = f"{target_date}T23:59:59"
            else:
                # 默认涵盖所有记录
                start_time = "2024-01-01T00:00:00"
                end_time = datetime.now().isoformat()

            engine.run_backtest(start_time, end_time)
            return 0
        except Exception as e:
            logging.error(f"回测执行失败: {e}")
            import traceback
            traceback.print_exc()
            return 1

    # ✅ 启用动态分类 (v3.1新增)
    scanner.use_dynamic_categories = args.use_dynamic_categories or getattr(config.scan, 'use_dynamic_categories', False)

    # ============================================================
    # 🆕 类别选择 (v3.1重构)
    # ============================================================
    selected_category = None
    available_categories = scanner.get_available_categories()

    if use_new_menu:
        # 使用新的交互式菜单选择类别
        selected_category = menu.select_category(scanner)
    else:
        # 非交互模式：通过 ID 匹配命令行指定的 domain
        selected_category = next((c for c in available_categories if c.id == domain), None)
        if not selected_category:
            # 如果没找到匹配的，使用第一个（通常是 crypto）
            selected_category = available_categories[0]
            print(f"[INFO] 未找到匹配类别 '{domain}'，使用默认: {selected_category.name_zh}")

    # 更新 domain 变量为最终选定的类别 ID，以保持后续逻辑兼容
    domain = selected_category.id
    try:
        print(f"[INFO] 扫描类别: {selected_category.icon} {selected_category.name_zh} ({selected_category.name_en})")
    except UnicodeEncodeError:
        # Fallback for environments that don't support special icons/characters
        print(f"[INFO] 扫描类别: {selected_category.name_zh} ({selected_category.name_en})")

    # ============================================================
    # 策略选择
    # ============================================================
    # 确定要执行的套利策略
    selected_strategy_ids = None

    if args.strategies:
        # 命令行指定策略
        selected_strategy_ids = [s.strip() for s in args.strategies.split(",")]
        print(f"[INFO] 使用指定策略: {', '.join(selected_strategy_ids)}")
    elif use_new_menu:
        # 使用新的交互式菜单选择策略
        selected_strategy_ids = menu.select_strategies(domain)
        print(f"[INFO] 已选择策略: {', '.join(selected_strategy_ids)}")

    # 如果没有选择策略，使用该领域的所有可用策略
    if selected_strategy_ids is None:
        available = StrategyRegistry.get_for_domain(domain)
        selected_strategy_ids = [m.id for m in available]
        print(f"[INFO] 使用默认策略: {', '.join(selected_strategy_ids)}")

    # 子类别选择
    subcategories = None
    if args.subcat:
        # 使用命令行参数指定的子类别
        raw_subcats = [s.strip() for s in args.subcat.split(",")]

        # 应用简写映射
        expanded = []
        for s in raw_subcats:
            mapped = SUBCATEGORY_ALIASES.get(s.lower(), s)
            expanded.append(mapped)

        # 🆕 改进的验证逻辑：允许不存在的子类别（会自动扩展为相关标签）
        tag_categories_file = Path(__file__).parent / "data" / "tag_categories.json"
        if tag_categories_file.exists():
            with open(tag_categories_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                tag_categories = data.get("categories", {})

            all_tags = tag_categories.get(domain, [])

            # 检查每个子类别是否能扩展为有效标签
            final_subcats = []
            for subcat in expanded:
                # 检查是否直接有效
                if subcat in all_tags:
                    final_subcats.append(subcat)
                else:
                    # 尝试扩展为相关标签
                    related = [t for t in all_tags if subcat.lower() in t.lower()]
                    if related:
                        print(f"[INFO] '{subcat}' 扩展为: {', '.join(related)}")
                        final_subcats.extend(related)
                    else:
                        print(f"[WARNING] 无效的子类别将被忽略: {subcat} (没有相关标签)")

            expanded = final_subcats

        if expanded:
            subcategories = expanded
            print(f"[INFO] 子类别筛选: {', '.join(sorted(set(expanded)))}")
    elif use_new_menu:
        # 使用新的交互式菜单选择子类别
        subcategories = menu.select_subcategories(domain)
        if subcategories:
            print(f"[INFO] 已选择子类别: {', '.join(subcategories)}")

    # ============================================================
    # 🆕 缓存选择（v3.1重构）
    # ============================================================
    force_refresh = False

    if args.refresh:
        # CLI参数明确指定刷新
        force_refresh = True
        print("[INFO] 强制刷新模式，将重新获取市场数据")
    elif args.use_cache:
        # CLI参数明确指定使用缓存
        force_refresh = False
        print("[INFO] 使用缓存模式")
    elif use_new_menu:
        # 使用新的交互式菜单选择缓存选项
        force_refresh = menu.select_cache_option()
        if output:
            if force_refresh:
                output.print_info("将重新获取市场数据")
            else:
                output.print_info("使用缓存数据")

    # ============================================================
    # 🆕 配置确认（v3.1新增）
    # ============================================================
    if use_new_menu:
        config_dict = {
            "domain": domain,
            "strategies": selected_strategy_ids or ["全部"],
            "subcategories": subcategories or ["全部"],
            "mode": run_mode.value,
            "force_refresh": force_refresh
        }
        if not menu.confirm_config(config_dict):
            print("[INFO] 取消扫描")
            return 0

    # ============================================================
    # 🆕 扫描执行 (v3.1重构 / Phase 5.3 高频模式)
    # ============================================================
    import time

    def perform_scan_task():
        """执行单次扫描任务"""
        start_time = time.time()
        opportunities = []
        try:
            if output:
                output.print_step(1, 2, "获取市场数据...")

            # 获取市场数据
            if scanner.use_dynamic_categories:
                markets = scanner.fetch_markets_for_category(selected_category, limit=config.scan.market_limit, force_refresh=force_refresh)
            else:
                markets = scanner._fetch_domain_markets(domain, subcategories, force_refresh)

            if output:
                output.print_market_fetch(len(markets), domain, subcategories)

            # ✅ 记录市场价格快照 (Phase 6.1)
            if hasattr(scanner, 'recorder'):
                scanner.recorder.record_markets(markets)

            if output:
                output.print_step(2, 2, "执行套利策略...")

            # ✅ 执行语义聚类发现关联市场 (Phase 5.1)
            clusters = []
            if getattr(config.scan, 'use_semantic_clustering', True) and scanner.clusterer:
                try:
                    # 仅对流动性达标的市场进行聚类以节省计算资源
                    cluster_candidates = [m for m in markets if m.liquidity >= getattr(config.scan, 'min_liquidity', 1000)]
                    if len(cluster_candidates) >= 2:
                        clusters = scanner.clusterer.cluster_markets(
                            cluster_candidates,
                            similarity_threshold=getattr(config.scan, 'semantic_threshold', 0.85)
                        )
                        if output:
                            output.print_info(f"语义聚类发现 {len(clusters)} 个关联簇")
                except Exception as e:
                    logging.warning(f"语义聚类失败: {e}")

            # ✅ 批量聚类深度分析 (Phase 5.2 优化)
            # 如果启用了聚类且选择了逻辑类策略，则执行批量分析以节省 Token 并提升召回率
            logic_strategy_ids = ['implication', 'equivalent']
            logic_strategy_active = any(s_id in selected_strategy_ids for s_id in logic_strategy_ids)

            if clusters and logic_strategy_active:
                if output:
                    output.print_step(2, 2, f"正在对 {len(clusters)} 个语义簇进行批量逻辑挖掘...")

                for i, cluster in enumerate(clusters):
                    if len(cluster) < 2:
                        continue

                    try:
                        batch_opps = scanner._analyze_cluster_fully(cluster)
                        if batch_opps:
                            # 排除掉已经通过策略发现的重复机会
                            for b_opp in batch_opps:
                                if not any(o.id == b_opp.id for o in opportunities):
                                    opportunities.append(b_opp)
                                    if output:
                                        output.print_opportunity(b_opp)
                    except Exception as e:
                        logging.debug(f"批量分析簇 {i+1} 失败: {e}")

            # 按优先级获取策略并执行
            strategies = StrategyRegistry.get_by_ids(selected_strategy_ids)

            for strategy in strategies:
                # ✅ 修正：使用 strategy.metadata.id (Phase 5.2 修复)
                if strategy.metadata.id in logic_strategy_ids and clusters:
                    continue

                if output:
                    output.print_strategy_start(strategy.metadata.name)

                try:
                    opps = strategy.scan(
                        markets,
                        {
                            "min_profit_pct": config.scan.min_profit_pct,
                            "domain": domain,
                            "subcategories": subcategories,
                            "scan": config.scan,  # 传入完整配置
                            "analyzer": scanner.analyzer,  # 传入 LLM 分析器
                            "clusters": clusters  # 🆕 传入语义聚类结果 (Phase 5.1)
                        },
                        progress_callback=lambda curr, total, msg: (
                            output.print_step(1, len(strategies), msg) if output else None
                        ) if output else None
                    )

                    # ✅ 执行五层验证与风控填充 (Phase 2.5)
                    valid_opps = []
                    for opp in opps:
                        validated_opp = scanner._validate_and_enrich_opportunity(opp, markets)
                        if validated_opp:
                            valid_opps.append(validated_opp)

                    opportunities.extend(valid_opps)

                    if output:
                        output.print_strategy_result(strategy.metadata.name, len(valid_opps))

                except Exception as e:
                    if output:
                        output.print_error(f"{strategy.metadata.name} 执行失败: {e}")

            # 保存报告
            if opportunities:
                scanner._save_report(opportunities, domain)

                # ✅ 记录套利机会存续历史 (Phase 6.1)
                if hasattr(scanner, 'recorder'):
                    scanner.recorder.record_opportunities(opportunities)

                if output:
                    output.print_report_saved(
                        Path(scanner.config.output.output_dir) / f"scan_{domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    )

            # 显示结果摘要
            elapsed_time = time.time() - start_time
            if output:
                output.print_summary(opportunities, elapsed_time)
            else:
                print("\n" + "=" * 65)
                print("扫描完成！")
                print("=" * 65)

            if opportunities:
                print("\n下一步行动:")
                print("  1. 仔细阅读每个机会的复核项目")
                print("  2. 在Polymarket上验证当前价格")
                print("  3. 阅读市场的结算规则")
                print("  4. 小额测试（$10-50）")

            return len(opportunities)

        except Exception as e:
            import traceback
            logging.error(f"扫描执行过程中出现异常: {e}")
            traceback.print_exc()
            return -1

    # 逻辑控制：单次扫描 vs 高频循环模式 (Phase 5.3)
    if not getattr(args, 'loop', False):
        try:
            return perform_scan_task()
        finally:
            scanner.close()
    else:
        # 进入高频循环模式
        iteration = 1
        interval = getattr(args, 'interval', 300)
        print(f"\n[🚀 START] 进入高频扫描模式 | 间隔: {interval}s")
        try:
            while True:
                print(f"\n{'='*60}")
                print(f"迭代 #{iteration} | 开始时间: {datetime.now().strftime('%H:%M:%S')}")
                print(f"{'='*60}")

                perform_scan_task()

                print(f"\n[WAIT] 扫描完成，等待 {interval} 秒进入下一次迭代...")
                time.sleep(interval)
                iteration += 1
        except KeyboardInterrupt:
            print("\n[STOP] 用户中断，退出高频模式")
            return 0
        finally:
            scanner.close()


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)