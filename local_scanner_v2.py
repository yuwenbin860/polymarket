#!/usr/bin/env python3
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

import requests
import json
import os
import sys
import argparse
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Tuple
from datetime import datetime
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


@dataclass
class Market:
    id: str
    condition_id: str
    question: str
    description: str
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
    token_id: str = ""            # CLOB token ID (用于获取订单簿)

    def __repr__(self):
        return f"Market('{self.question[:50]}...', YES=${self.yes_price:.2f}, spread={self.spread:.3f})"

    @property
    def effective_buy_price(self) -> float:
        """实际买入价格 - 套利计算时使用 best_ask"""
        return self.best_ask if self.best_ask > 0 else self.yes_price

    @property
    def effective_sell_price(self) -> float:
        """实际卖出价格 - 套利计算时使用 best_bid"""
        return self.best_bid if self.best_bid > 0 else self.yes_price


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


# ============================================================
# Polymarket API客户端
# ============================================================

class PolymarketClient:
    """Polymarket API客户端"""
    
    def __init__(self, api_base: str = "https://gamma-api.polymarket.com"):
        self.base_url = api_base
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "PolymarketArbitrageScanner/2.0"
        })
    
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
                    if market and market.liquidity >= min_liquidity:
                        markets.append(market)
                except Exception as e:
                    continue
            
            return markets
            
        except requests.RequestException as e:
            print(f"API请求失败: {e}")
            return []
    
    def _parse_market(self, data: Dict) -> Optional[Market]:
        """解析市场数据"""
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
            # YES token 是第一个
            yes_token_id = token_ids[0] if token_ids else ""

            return Market(
                id=data.get('id', ''),
                condition_id=data.get('conditionId', ''),
                question=data.get('question', ''),
                description=data.get('description', ''),
                yes_price=yes_price,
                no_price=1 - yes_price,
                volume=float(data.get('volume', 0) or 0),
                liquidity=float(data.get('liquidity', 0) or 0),
                end_date=data.get('endDate', ''),
                event_id=data.get('eventSlug', '') or data.get('groupItemTitle', '') or '',
                event_title=data.get('groupItemTitle', '') or data.get('eventSlug', '') or '',
                resolution_source=data.get('resolutionSource', ''),
                outcomes=outcomes,
                token_id=yes_token_id
            )
        except Exception:
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

        return market

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
            print(f"⚠️ LLM初始化失败: {e}")
            print("   将使用规则匹配替代LLM分析")
            self.use_llm = False
        except Exception as e:
            print(f"⚠️ LLM初始化异常: {e}")
            self.use_llm = False

    def _init_from_profile(self, profile_name: str, model_override: str = None):
        """从profile配置初始化"""
        from llm_config import get_llm_config_by_name
        profile = get_llm_config_by_name(profile_name)
        if not profile:
            raise ValueError(f"未找到配置: {profile_name}")

        if not profile.is_configured():
            raise ValueError(f"配置 {profile_name} 未设置API Key (需要: {profile.api_key_env})")

        model = model_override or profile.model
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
        print(f"✅ LLM已初始化 (--profile): {profile_name} / {model}")

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
        print(f"✅ LLM已初始化 (config.json): {provider} / {self.client.config.model}")

    def _init_from_auto_detect(self, model_override: str = None):
        """自动检测可用的LLM配置"""
        from llm_config import get_llm_config
        profile = get_llm_config()

        if not profile:
            raise ValueError(
                "未检测到可用的LLM配置。请选择以下方式之一:\n"
                "  1. 设置环境变量 (如 DEEPSEEK_API_KEY)\n"
                "  2. 使用 --profile 参数 (如 --profile deepseek)\n"
                "  3. 在 config.json 中配置 llm.provider 和 llm.api_key"
            )

        model = model_override or profile.model
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
        print(f"✅ LLM已初始化 (自动检测): {profile.name} / {model}")
    
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
            print(f"    JSON解析失败: {e}")
            return self._analyze_with_rules(market_a, market_b)
        except Exception as e:
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
            print(f"    ⚠️ LLM输出一致性检查失败: {consistency_error}")
            print(f"       降级为 INDEPENDENT 以防止假套利")
            # 降级为 INDEPENDENT
            relationship = "INDEPENDENT"
            confidence = 0.0

        # 一致性检查: 检测 relationship 与 reasoning 是否矛盾（保留原有逻辑作为双重检查）
        reasoning_upper = reasoning.upper() if isinstance(reasoning, str) else ""
        inconsistency_detected = False

        if relationship == "IMPLIES_AB" and "IMPLIES_BA" in reasoning_upper:
            print(f"    ⚠️ LLM响应不一致: relationship={relationship}, 但reasoning提到IMPLIES_BA")
            inconsistency_detected = True
        elif relationship == "IMPLIES_BA" and "IMPLIES_AB" in reasoning_upper and "IMPLIES_BA" not in reasoning_upper:
            print(f"    ⚠️ LLM响应不一致: relationship={relationship}, 但reasoning提到IMPLIES_AB")
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
            >>> # 矛盾案例：reasoning 说互斥，但 relationship 是 IMPLIES
            >>> result = {
            ...     'relationship': 'IMPLIES_AB',
            ...     'reasoning': 'These markets are mutually exclusive'
            ... }
            >>> is_valid, msg = analyzer._validate_llm_response_consistency(result)
            >>> assert not is_valid
            >>> assert 'mutual' in msg.lower()
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

    def close(self):
        """关闭LLM客户端"""
        if self.client:
            self.client.close()


# ============================================================
# 套利检测器
# ============================================================

class ArbitrageDetector:
    """套利机会检测器"""
    
    def __init__(self, config: AppConfig):
        self.min_profit_pct = config.scan.min_profit_pct
        self.min_confidence = config.scan.min_confidence

        # ✅ 新增：初始化数学验证器
        self.math_validator = MathValidator()
        print(f"✅ MathValidator 已初始化")
    
    def check_pair(self, market_a: Market, market_b: Market, 
                   analysis: Dict) -> Optional[ArbitrageOpportunity]:
        """检查市场对是否存在套利"""
        rel = analysis.get("relationship", "UNRELATED")
        
        if rel == "IMPLIES_AB":
            return self._check_implication(market_a, market_b, analysis, "A→B")
        elif rel == "IMPLIES_BA":
            return self._check_implication(market_b, market_a, analysis, "B→A")
        elif rel == "EQUIVALENT":
            return self._check_equivalent(market_a, market_b, analysis)
        
        return None
    
    def check_exhaustive_set(self, markets: List[Market]) -> Optional[ArbitrageOpportunity]:
        """检查完备集套利"""
        if len(markets) < 2:
            return None

        # 验证1: 检查结算来源一致性
        sources = set(m.resolution_source for m in markets if m.resolution_source)
        if len(sources) > 1:
            return None  # 结算来源不一致，可能不是真正的完备集

        # 验证2: 检查结算日期一致性（已在 _group_by_event 中处理，这里再次确认）
        dates = set()
        for m in markets:
            if m.end_date:
                date_part = m.end_date.split('T')[0] if 'T' in m.end_date else m.end_date
                dates.add(date_part)
        if len(dates) > 1:
            return None  # 结算日期不一致

        # 陷阱1修复: 使用真实的 best_ask 计算成本
        # 买入所有选项的 YES，使用各自的 best_ask
        real_total = sum(m.effective_buy_price for m in markets)
        mid_total = sum(m.yes_price for m in markets)

        if real_total < 0.98:
            real_profit = 1.0 - real_total
            real_profit_pct = (real_profit / real_total) * 100 if real_total > 0 else 0
            mid_profit_pct = ((1.0 - mid_total) / mid_total) * 100 if mid_total > 0 else 0

            if real_profit_pct < self.min_profit_pct:
                return None

            # 验证3: 利润率合理性检查
            needs_extra_review = []
            if real_profit_pct > 100:
                needs_extra_review.append("!! 利润率超过100%，请重点验证数据准确性")

            # 陷阱1修复: 检查是否有较大价差
            high_spread_markets = [m for m in markets if m.spread > 0.02]
            if high_spread_markets:
                spread_info = ", ".join([f"{m.question[:30]}:{m.spread:.1%}" for m in high_spread_markets[:3]])
                needs_extra_review.append(f"!! 部分市场价差较大: {spread_info}")

            action_lines = [
                f"买 '{m.question[:60]}...' YES @ ${m.effective_buy_price:.3f} (ask)"
                for m in markets
            ]

            return ArbitrageOpportunity(
                id=f"exhaustive_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                type="EXHAUSTIVE_SET_UNDERPRICED",
                markets=[{"id": m.id, "question": m.question, "yes_price": m.yes_price,
                          "best_ask": m.best_ask, "spread": m.spread} for m in markets],
                relationship="exhaustive",
                confidence=0.85,
                total_cost=real_total,
                guaranteed_return=1.0,
                profit=real_profit,
                profit_pct=real_profit_pct,
                action="\n".join(action_lines),
                reasoning="完备集市场总价小于1，买入所有选项可锁定利润",
                edge_cases=["需确认这些选项真的构成完备集"],
                needs_review=[
                    "确认所有选项互斥且覆盖全部可能",
                    "检查结算规则是否一致",
                    "确认没有遗漏的选项",
                    f"中间价利润: {mid_profit_pct:.1f}% vs 实际利润: {real_profit_pct:.1f}%",
                ] + needs_extra_review,
                timestamp=datetime.now().isoformat()
            )

        return None
    
    def _check_implication(self, implying: Market, implied: Market,
                           analysis: Dict, direction: str) -> Optional[ArbitrageOpportunity]:
        """检查包含关系套利"""

        # ✅ 新增：LLM 输出一致性检查
        if not analysis.get("is_consistent", True):
            print(f"    ⚠️ LLM 输出不一致，跳过套利检测")
            print(f"       错误: {analysis.get('consistency_error', 'Unknown')}")
            return None

        # ✅ 新增：数据有效性检查
        if not self._validate_market_data(implying, implied):
            print(f"    ❌ 数据有效性检查失败，跳过套利检测")
            return None

        # ✅ 新增：调用 MathValidator 验证数学约束
        relation_type = analysis.get("relationship", "")
        reasoning = analysis.get("reasoning", "")

        validation_result = self.math_validator.validate_implication(
            market_a=implying.__dict__,
            market_b=implied.__dict__,
            relation_type=relation_type,
            reasoning=reasoning
        )

        if not validation_result['is_valid']:
            print(f"    ❌ 数学验证失败: {validation_result['message']}")
            print(f"       验证详情: {validation_result.get('details', {})}")
            return None
        else:
            print(f"    ✅ 数学验证通过: {validation_result['message']}")

        # ✅ Priority 2: 时间一致性验证
        if relation_type in ['IMPLIES_AB', 'IMPLIES_BA']:
            # 导入 MarketData 用于类型转换
            from validators import MarketData

            # 转换 Market 对象为 MarketData
            market_a_data = MarketData(
                id=implying.id,
                question=implying.question,
                yes_price=implying.yes_price,
                no_price=implying.no_price,
                liquidity=implying.liquidity,
                volume=implying.volume,
                end_date=implying.end_date
            )

            market_b_data = MarketData(
                id=implied.id,
                question=implied.question,
                yes_price=implied.yes_price,
                no_price=implied.no_price,
                liquidity=implied.liquidity,
                volume=implied.volume,
                end_date=implied.end_date
            )

            time_validation = self.math_validator.validate_time_consistency(
                market_a=market_a_data,
                market_b=market_b_data,
                relation=relation_type
            )

            # 使用 .result.value 获取字符串值
            if time_validation.result.value == 'FAILED':
                print(f"    ❌ 时间一致性验证失败: {time_validation.reason}")
                print(f"       结算时间: {implying.end_date} vs {implied.end_date}")
                return None
            elif time_validation.result.value == 'NEEDS_REVIEW':
                print(f"    ⚠️  时间一致性验证: {time_validation.reason}")
                # 时间不一致的蕴含关系通常是误判，但仍返回 None
                return None
            else:
                print(f"    ✅ 时间一致性验证通过: {time_validation.reason}")

        # ✅ Priority 2: 语义验证
        is_semantically_valid, semantic_msg = self._validate_arbitrage_semantics(
            implying=implying,
            implied=implied,
            relation_type=relation_type
        )

        if not is_semantically_valid:
            print(f"    ⚠️  语义验证失败: {semantic_msg}")
            print(f"       建议: 人工复核此机会")
            # 语义验证失败时，降低置信度但不直接拒绝
            confidence = analysis.get("confidence", 0.8) * 0.7
            analysis["confidence"] = confidence
            analysis["semantic_warning"] = semantic_msg
        else:
            print(f"    ✅ 语义验证通过: {semantic_msg}")

        # 检查 LLM 响应是否存在不一致（原有逻辑，保留作为双重检查）
        if analysis.get("inconsistency_detected", False):
            return None  # 不一致的分析结果不可信，跳过

        # 蕴含关系约束检查：如果 A → B，则 P(B) >= P(A)
        # 套利条件：P(B) < P(A)（违反约束）
        if implied.yes_price >= implying.yes_price - 0.01:
            return None  # 约束满足，无套利

        # 陷阱1修复: 使用真实的 best_ask 计算买入成本
        # 买入 implied 的 YES: 使用 best_ask
        implied_buy_cost = implied.effective_buy_price
        # 买入 implying 的 NO: 使用 1 - best_bid (相当于卖出 YES)
        implying_no_cost = 1 - implying.effective_sell_price if implying.best_bid > 0 else implying.no_price

        # 使用真实成本计算利润
        real_cost = implied_buy_cost + implying_no_cost
        real_profit = 1.0 - real_cost
        real_profit_pct = (real_profit / real_cost) * 100 if real_cost > 0 else 0

        # 同时保留中间价计算（用于对比）
        mid_cost = implied.yes_price + implying.no_price
        mid_profit_pct = ((1.0 - mid_cost) / mid_cost) * 100 if mid_cost > 0 else 0

        if real_profit_pct < self.min_profit_pct:
            return None

        if analysis.get("confidence", 0) < self.min_confidence:
            return None

        # 利润率合理性检查
        needs_extra_review = []
        if real_profit_pct > 100:
            needs_extra_review.append("!! 利润率超过100%，请重点验证数据准确性和逻辑关系")

        # 陷阱1修复: 如果有价差数据，显示滑点警告
        if implied.spread > 0.02 or implying.spread > 0.02:
            needs_extra_review.append(f"!! 价差较大 (implied:{implied.spread:.1%}, implying:{implying.spread:.1%})，注意滑点风险")

        return ArbitrageOpportunity(
            id=f"impl_{direction}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            type="IMPLICATION_VIOLATION",
            markets=[
                {"id": implied.id, "question": implied.question, "yes_price": implied.yes_price,
                 "best_ask": implied.best_ask, "spread": implied.spread},
                {"id": implying.id, "question": implying.question, "yes_price": implying.yes_price,
                 "best_bid": implying.best_bid, "spread": implying.spread}
            ],
            relationship=f"implies_{direction.lower().replace('→', '_')}",
            confidence=analysis.get("confidence", 0.5),
            total_cost=real_cost,
            guaranteed_return=1.0,
            profit=real_profit,
            profit_pct=real_profit_pct,
            action=f"买 '{implied.question[:60]}...' YES @ ${implied_buy_cost:.3f} (ask)\n"
                   f"买 '{implying.question[:60]}...' NO @ ${implying_no_cost:.3f}",
            reasoning=analysis.get("reasoning", ""),
            edge_cases=analysis.get("edge_cases", []),
            needs_review=[
                "验证逻辑关系确实成立",
                "检查结算规则是否兼容",
                f"中间价利润: {mid_profit_pct:.1f}% vs 实际利润: {real_profit_pct:.1f}%",
            ] + needs_extra_review,
            timestamp=datetime.now().isoformat()
        )

    def _validate_market_data(
        self,
        market_a: Market,
        market_b: Market
    ) -> bool:
        """
        验证市场数据的有效性

        检查：
        1. 价格字段是否有效（非 0.0，非 None）
        2. 必需字段是否存在
        3. 价格范围是否合理（0-1）

        Args:
            market_a, market_b: 待验证的市场

        Returns:
            True 表示数据有效，False 表示无效
        """
        # 检查价格有效性
        for market, name in [(market_a, 'A'), (market_b, 'B')]:
            # YES 价格检查
            if market.yes_price == 0.0 or market.yes_price is None:
                print(f"    ❌ 市场 {name} YES 价格无效: {market.yes_price}")
                return False

            if not (0.0 <= market.yes_price <= 1.0):
                print(f"    ❌ 市场 {name} YES 价格超出范围: {market.yes_price}")
                return False

            # NO 价格检查
            if market.no_price == 0.0 or market.no_price is None:
                print(f"    ❌ 市场 {name} NO 价格无效: {market.no_price}")
                return False

            if not (0.0 <= market.no_price <= 1.0):
                print(f"    ❌ 市场 {name} NO 价格超出范围: {market.no_price}")
                return False

            # 流动性检查
            if market.liquidity <= 0:
                print(f"    ❌ 市场 {name} 流动性为 0: {market.liquidity}")
                return False

            # Question 检查
            if not market.question or market.question.strip() == '':
                print(f"    ❌ 市场 {name} question 为空")
                return False

        print(f"    ✅ 数据有效性检查通过")
        return True

    def _validate_arbitrage_semantics(
        self,
        implying: Market,
        implied: Market,
        relation_type: str
    ) -> tuple[bool, str]:
        """
        验证套利机会的语义合理性 (Priority 2)

        检查价格关系是否符合逻辑直觉：
        - 对于 IMPLIES_AB: 如果 P(A) = 0.9, P(B) = 0.1，这不太合理
          （因为 A→B 要求 P(B) >= P(A)）
        - 对于 EQUIVALENT: 价格应该接近，不应该差异巨大

        Args:
            implying: 蕴含市场（A）
            implied: 被蕴含市场（B）
            relation_type: 关系类型

        Returns:
            (is_valid, message)
        """
        p_a = implying.yes_price
        p_b = implied.yes_price

        if relation_type == 'IMPLIES_AB' or relation_type == 'IMPLIES_BA':
            # 蕴含关系：P(B) 应该 >= P(A)
            # 但我们检测的是 P(B) < P(A) 的情况
            price_gap = p_a - p_b

            # 如果价格差异过大（>50%），可能是误判
            if price_gap > 0.5:
                return False, (
                    f"蕴含关系价格差异过大: P(A)={p_a:.3f}, P(B)={p_b:.3f}, "
                    f"差距={price_gap:.1%}。这不太可能是真正的蕴含关系。"
                )

            # 如果 P(A) 极低但 P(B) 极高，也值得怀疑
            if p_a < 0.1 and p_b > 0.9:
                return False, (
                    f"蕴含关系价格极端: P(A)={p_a:.3f} (极低), P(B)={p_b:.3f} (极高)。"
                    f"请检查是否误判为蕴含关系。"
                )

        elif relation_type == 'EQUIVALENT':
            # 等价关系：价格应该接近
            price_diff = abs(p_a - p_b)

            if price_diff > 0.2:  # 20% 差异
                return False, (
                    f"等价市场价格差异过大: P(A)={p_a:.3f}, P(B)={p_b:.3f}, "
                    f"差异={price_diff:.1%}。等价市场应该有相似的价格。"
                )

        return True, "语义验证通过"

    def _check_equivalent(self, market_a: Market, market_b: Market,
                          analysis: Dict) -> Optional[ArbitrageOpportunity]:
        """检查等价市场套利"""
        spread = abs(market_a.yes_price - market_b.yes_price)

        if spread < 0.03:
            return None

        if market_a.yes_price < market_b.yes_price:
            cheap, expensive = market_a, market_b
        else:
            cheap, expensive = market_b, market_a

        # 陷阱1修复: 使用真实的 best_ask/best_bid 计算成本
        # 买入 cheap 的 YES: 使用 best_ask
        cheap_buy_cost = cheap.effective_buy_price
        # 买入 expensive 的 NO: 使用 1 - best_bid
        expensive_no_cost = 1 - expensive.effective_sell_price if expensive.best_bid > 0 else expensive.no_price

        # 使用真实成本计算利润
        real_cost = cheap_buy_cost + expensive_no_cost
        real_profit = 1.0 - real_cost
        real_profit_pct = (real_profit / real_cost) * 100 if real_cost > 0 else 0

        # 保留中间价计算（用于对比）
        mid_cost = cheap.yes_price + expensive.no_price
        mid_profit_pct = ((1.0 - mid_cost) / mid_cost) * 100 if mid_cost > 0 else 0

        if real_profit_pct < self.min_profit_pct:
            return None

        # 陷阱1修复: 价差警告
        needs_extra_review = []
        if cheap.spread > 0.02 or expensive.spread > 0.02:
            needs_extra_review.append(f"!! 价差较大 (cheap:{cheap.spread:.1%}, expensive:{expensive.spread:.1%})")

        return ArbitrageOpportunity(
            id=f"equiv_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            type="EQUIVALENT_MISPRICING",
            markets=[
                {"id": cheap.id, "question": cheap.question, "yes_price": cheap.yes_price,
                 "best_ask": cheap.best_ask, "spread": cheap.spread},
                {"id": expensive.id, "question": expensive.question, "yes_price": expensive.yes_price,
                 "best_bid": expensive.best_bid, "spread": expensive.spread}
            ],
            relationship="equivalent",
            confidence=analysis.get("confidence", 0.5),
            total_cost=real_cost,
            guaranteed_return=1.0,
            profit=real_profit,
            profit_pct=real_profit_pct,
            action=f"买 '{cheap.question[:60]}...' YES @ ${cheap_buy_cost:.3f} (ask)\n"
                   f"买 '{expensive.question[:60]}...' NO @ ${expensive_no_cost:.3f}",
            reasoning="等价市场存在显著价差",
            edge_cases=analysis.get("edge_cases", []),
            needs_review=[
                "确认两个市场真的等价",
                "检查结算规则",
                f"中间价利润: {mid_profit_pct:.1f}% vs 实际利润: {real_profit_pct:.1f}%",
            ] + needs_extra_review,
            timestamp=datetime.now().isoformat()
        )


# ============================================================
# 相似度筛选器
# ============================================================

class SimilarityFilter:
    """市场相似度筛选器"""
    
    def __init__(self, threshold: float = 0.3):
        self.threshold = threshold
    
    def find_similar_pairs(self, markets: List[Market]) -> List[Tuple[Market, Market, float]]:
        """找出相似的市场对"""
        pairs = []
        
        for i, m1 in enumerate(markets):
            for m2 in markets[i+1:]:
                score = self._calculate_similarity(m1, m2)
                if score >= self.threshold:
                    pairs.append((m1, m2, score))
        
        pairs.sort(key=lambda x: x[2], reverse=True)
        return pairs
    
    def _calculate_similarity(self, m1: Market, m2: Market) -> float:
        """计算相似度"""
        stop_words = {'will', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'by', 'be', 'is', 'are'}
        
        words1 = set(m1.question.lower().split()) - stop_words
        words2 = set(m2.question.lower().split()) - stop_words
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        jaccard = intersection / union if union > 0 else 0
        
        # 同一事件加分
        if m1.event_id and m1.event_id == m2.event_id:
            jaccard = min(1.0, jaccard + 0.4)
        
        # 同结算日加分
        if m1.end_date and m1.end_date == m2.end_date:
            jaccard = min(1.0, jaccard + 0.1)
        
        return jaccard


# ============================================================
# 主扫描器
# ============================================================

class ArbitrageScanner:
    """主扫描器"""
    
    def __init__(self, config: AppConfig, profile_name: str = None, model_override: str = None):
        self.config = config
        self.profile_name = profile_name
        self.model_override = model_override
        self.client = PolymarketClient()
        self.analyzer = LLMAnalyzer(config, profile_name=profile_name, model_override=model_override)
        self.detector = ArbitrageDetector(config)
        self.filter = SimilarityFilter(config.scan.similarity_threshold)
    
    def scan(self) -> List[ArbitrageOpportunity]:
        """执行完整扫描"""
        opportunities = []
        
        self._print_header()
        
        # Step 1: 获取市场
        print("\n[1/4] 获取市场数据...")
        markets = self.client.get_markets(
            limit=self.config.scan.market_limit,
            min_liquidity=self.config.scan.min_liquidity
        )
        print(f"      获取到 {len(markets)} 个高流动性市场")
        
        if not markets:
            print("      ❌ 无法获取市场数据")
            return []
        
        # Step 2: 检查完备集
        print("\n[2/4] 扫描完备集套利...")
        event_groups = self._group_by_event(markets)
        print(f"      发现 {len(event_groups)} 个事件组")
        
        for event_id, group in event_groups.items():
            if len(group) >= 2:
                total = sum(m.yes_price for m in group)
                if self.config.output.detailed_log:
                    print(f"      - {event_id}: {len(group)}个市场, Σ={total:.3f}")
                
                opp = self.detector.check_exhaustive_set(group)
                if opp:
                    opportunities.append(opp)
                    print(f"        🎯 发现套利! 利润={opp.profit_pct:.2f}%")
        
        # Step 3: 分析相似市场对
        print("\n[3/4] 分析逻辑关系...")
        similar_pairs = self.filter.find_similar_pairs(markets)
        print(f"      发现 {len(similar_pairs)} 对相似市场")
        
        analyzed = 0
        max_calls = self.config.scan.max_llm_calls
        
        for m1, m2, sim in similar_pairs:
            if analyzed >= max_calls:
                break
            
            # 跳过同一事件的（已在完备集检查中处理）
            if m1.event_id and m1.event_id == m2.event_id:
                continue
            
            analyzed += 1
            if self.config.output.detailed_log:
                print(f"      分析 #{analyzed}: {m1.question[:40]}... vs {m2.question[:40]}...")
            
            analysis = self.analyzer.analyze(m1, m2)
            rel = analysis.get("relationship", "UNRELATED")
            conf = analysis.get("confidence", 0)
            
            if self.config.output.detailed_log:
                print(f"        关系={rel}, 置信度={conf:.2f}")
            
            opp = self.detector.check_pair(m1, m2, analysis)
            if opp:
                opportunities.append(opp)
                print(f"        🎯 发现套利! 利润={opp.profit_pct:.2f}%")
        
        # Step 4: 生成报告
        print("\n[4/4] 生成报告...")
        self._save_report(opportunities)
        self._print_summary(opportunities)
        
        return opportunities
    
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

    def _group_by_event(self, markets: List[Market]) -> Dict[str, List[Market]]:
        """按事件分组（考虑结算日期，避免将不同日期的市场误归为完备集）"""
        groups = {}
        for m in markets:
            event_key = m.event_id or m.event_title
            if event_key:
                # 关键改进: 同时考虑 event_id 和 end_date
                # 确保只有同一天结算的市场才归为一组
                date_part = ""
                if m.end_date:
                    date_part = m.end_date.split('T')[0] if 'T' in m.end_date else m.end_date
                key = f"{event_key}_{date_part}" if date_part else event_key
                groups.setdefault(key, []).append(m)
        return groups
    
    def _print_header(self):
        """打印标题"""
        if self.analyzer.profile_name:
            llm_info = f"{self.analyzer.profile_name} / {self.analyzer.model_name or 'default'}"
        elif self.analyzer.client:
            llm_info = f"{self.config.llm.provider} / {self.analyzer.client.config.model}"
        else:
            llm_info = "规则匹配 (无LLM)"
        
        print(f"""
╔═══════════════════════════════════════════════════════════════╗
║         Polymarket 组合套利扫描系统 v2.0                       ║
║                                                               ║
║  LLM配置: {llm_info:<50}║
║  最小利润: {self.config.scan.min_profit_pct}%                                              ║
║  最小流动性: ${self.config.scan.min_liquidity:,.0f}                                       ║
╚═══════════════════════════════════════════════════════════════╝
        """)
    
    def _save_report(self, opportunities: List[ArbitrageOpportunity]):
        """保存报告"""
        os.makedirs(self.config.output.output_dir, exist_ok=True)
        
        output_file = os.path.join(
            self.config.output.output_dir,
            f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        
        report = {
            "scan_time": datetime.now().isoformat(),
            "config": {
                "llm_provider": self.config.llm.provider,
                "min_profit_pct": self.config.scan.min_profit_pct,
                "min_liquidity": self.config.scan.min_liquidity,
                "min_confidence": self.config.scan.min_confidence
            },
            "opportunities_count": len(opportunities),
            "opportunities": [asdict(opp) for opp in opportunities]
        }
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"      ✅ 报告已保存到 {output_file}")
    
    def _print_summary(self, opportunities: List[ArbitrageOpportunity]):
        """打印摘要"""
        print("\n" + "=" * 65)
        print("扫描结果摘要")
        print("=" * 65)

        if not opportunities:
            print("\n暂未发现符合条件的套利机会")
            print("这很正常——好机会不是时时都有\n")
            return

        print(f"\n🎯 发现 {len(opportunities)} 个潜在套利机会:\n")

        for i, opp in enumerate(opportunities, 1):
            print(f"{'─' * 60}")
            print(f"机会 #{i}: {opp.type}")
            print(f"{'─' * 60}")
            print(f"置信度: {opp.confidence:.0%}")
            print(f"总成本: ${opp.total_cost:.4f}")
            print(f"利润: ${opp.profit:.4f} ({opp.profit_pct:.2f}%)")
            print(f"\n操作:")
            for line in opp.action.split('\n'):
                print(f"  {line}")

            # ✅ 新增：Polymarket 链接
            links = self._generate_polymarket_links(opp.markets)
            print(f"\n🔗 Polymarket 链接:")
            for j, (market, link) in enumerate(zip(opp.markets, links), 1):
                question = market.get('question', '')[:60]
                print(f"  {j}. {question}...")
                print(f"     {link}")

            # ✅ 新增：人工验证清单
            print(f"\n⚠️  人工验证清单:")
            print(f"  ☐ 验证逻辑关系是否正确: {opp.type}")
            print(f"  ☐ 检查结算规则是否兼容")

            # 如果有两个市场，显示结算时间对比
            if len(opp.markets) >= 2:
                market_1 = opp.markets[0]
                market_2 = opp.markets[1]
                print(f"  ☐ 在 Polymarket 上确认当前价格")
                print(f"  ☐ 检查流动性: ${market_1.get('yes_price', 0):.2f} vs ${market_2.get('yes_price', 0):.2f}")
            print(f"  ☐ 检查是否有特殊规则（如提前结算）")
            print(f"  ☐ 验证 LLM 分析的合理性")

            # 原有的 needs_review 内容
            if opp.needs_review:
                print(f"\n📋 额外注意事项:")
                for item in opp.needs_review:
                    print(f"  • {item}")

            print()
    
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
  python local_scanner_v2.py --profile siliconflow
  python local_scanner_v2.py --profile deepseek --model deepseek-reasoner
  python local_scanner_v2.py --profile ollama --model llama3.1:70b
  
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
        "--market-limit",
        type=int,
        help="获取市场数量 (默认: 200)"
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="列出所有可用的LLM配置"
    )
    
    args = parser.parse_args()
    
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
    if args.market_limit:
        config.scan.market_limit = args.market_limit
    
    # 创建扫描器
    scanner = ArbitrageScanner(
        config,
        profile_name=args.profile,
        model_override=args.model
    )
    
    try:
        # 执行扫描
        opportunities = scanner.scan()
        
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
        
    finally:
        scanner.close()


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
