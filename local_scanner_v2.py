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
    yes_price: float
    no_price: float
    volume: float
    liquidity: float
    end_date: str
    event_id: str
    event_title: str
    resolution_source: str
    outcomes: List[str]
    
    def __repr__(self):
        return f"Market('{self.question[:50]}...', YES=${self.yes_price:.2f})"


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
                outcomes=outcomes
            )
        except Exception:
            return None


# ============================================================
# LLM分析器（支持多种提供商）
# ============================================================

ANALYSIS_PROMPT = """你是一个专门分析预测市场逻辑关系的专家。

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


class LLMAnalyzer:
    """LLM分析器 - 支持多种提供商"""
    
    def __init__(self, config: AppConfig = None, profile_name: str = None, model_override: str = None):
        self.config = config
        self.use_llm = True
        self.client: Optional[BaseLLMClient] = None
        self.profile_name = profile_name
        self.model_name = model_override
        
        try:
            # 方式1: 使用profile配置
            if profile_name:
                from llm_config import get_llm_config_by_name
                profile = get_llm_config_by_name(profile_name)
                if profile:
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
                    self.model_name = model
                    print(f"✅ LLM已初始化: {profile_name} / {model}")
                else:
                    raise ValueError(f"未找到配置: {profile_name}")
            
            # 方式2: 自动检测profile
            elif not config or not config.llm.provider:
                from llm_config import get_llm_config
                profile = get_llm_config()
                if profile:
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
                else:
                    raise ValueError("未检测到可用的LLM配置，请设置API Key或使用 --profile 参数")
            
            # 方式3: 使用config配置
            else:
                self.client = create_llm_client(
                    provider=config.llm.provider,
                    model=model_override or config.llm.model or None,
                    api_key=config.llm.api_key or None,
                    api_base=config.llm.api_base or None,
                    max_tokens=config.llm.max_tokens,
                    temperature=config.llm.temperature,
                )
                self.model_name = self.client.config.model
                print(f"✅ LLM已初始化: {config.llm.provider} / {self.client.config.model}")
                
        except ValueError as e:
            print(f"⚠️ LLM初始化失败: {e}")
            print("   将使用规则匹配替代LLM分析")
            self.use_llm = False
        except Exception as e:
            print(f"⚠️ LLM初始化异常: {e}")
            self.use_llm = False
    
    def analyze(self, market_a: Market, market_b: Market) -> Dict:
        """分析两个市场的逻辑关系"""
        if self.use_llm and self.client:
            return self._analyze_with_llm(market_a, market_b)
        else:
            return self._analyze_with_rules(market_a, market_b)
    
    def _analyze_with_llm(self, market_a: Market, market_b: Market) -> Dict:
        """使用LLM分析"""
        prompt = ANALYSIS_PROMPT.format(
            question_a=market_a.question,
            description_a=(market_a.description or "")[:500],
            price_a=market_a.yes_price,
            source_a=market_a.resolution_source or "未指定",
            question_b=market_b.question,
            description_b=(market_b.description or "")[:500],
            price_b=market_b.yes_price,
            source_b=market_b.resolution_source or "未指定",
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
            return result
            
        except json.JSONDecodeError as e:
            print(f"    JSON解析失败: {e}")
            return self._analyze_with_rules(market_a, market_b)
        except Exception as e:
            print(f"    LLM分析失败: {e}")
            return self._analyze_with_rules(market_a, market_b)
    
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
        
        total = sum(m.yes_price for m in markets)
        
        if total < 0.98:
            profit = 1.0 - total
            profit_pct = (profit / total) * 100
            
            if profit_pct < self.min_profit_pct:
                return None
            
            action_lines = [
                f"买 '{m.question[:60]}...' YES @ ${m.yes_price:.3f}"
                for m in markets
            ]
            
            return ArbitrageOpportunity(
                id=f"exhaustive_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                type="EXHAUSTIVE_SET_UNDERPRICED",
                markets=[{"id": m.id, "question": m.question, "yes_price": m.yes_price} for m in markets],
                relationship="exhaustive",
                confidence=0.85,
                total_cost=total,
                guaranteed_return=1.0,
                profit=profit,
                profit_pct=profit_pct,
                action="\n".join(action_lines),
                reasoning="完备集市场总价小于1，买入所有选项可锁定利润",
                edge_cases=["需确认这些选项真的构成完备集"],
                needs_review=[
                    "确认所有选项互斥且覆盖全部可能",
                    "检查结算规则是否一致",
                    "确认没有遗漏的选项"
                ],
                timestamp=datetime.now().isoformat()
            )
        
        return None
    
    def _check_implication(self, implying: Market, implied: Market,
                           analysis: Dict, direction: str) -> Optional[ArbitrageOpportunity]:
        """检查包含关系套利"""
        if implied.yes_price >= implying.yes_price - 0.01:
            return None
        
        cost = implied.yes_price + implying.no_price
        profit = 1.0 - cost
        profit_pct = (profit / cost) * 100 if cost > 0 else 0
        
        if profit_pct < self.min_profit_pct:
            return None
        
        if analysis.get("confidence", 0) < self.min_confidence:
            return None
        
        return ArbitrageOpportunity(
            id=f"impl_{direction}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            type="IMPLICATION_VIOLATION",
            markets=[
                {"id": implied.id, "question": implied.question, "yes_price": implied.yes_price},
                {"id": implying.id, "question": implying.question, "yes_price": implying.yes_price}
            ],
            relationship=f"implies_{direction.lower().replace('→', '_')}",
            confidence=analysis.get("confidence", 0.5),
            total_cost=cost,
            guaranteed_return=1.0,
            profit=profit,
            profit_pct=profit_pct,
            action=f"买 '{implied.question[:60]}...' YES @ ${implied.yes_price:.3f}\n"
                   f"买 '{implying.question[:60]}...' NO @ ${implying.no_price:.3f}",
            reasoning=analysis.get("reasoning", ""),
            edge_cases=analysis.get("edge_cases", []),
            needs_review=[
                "验证逻辑关系确实成立",
                "检查结算规则是否兼容",
            ],
            timestamp=datetime.now().isoformat()
        )
    
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
        
        cost = cheap.yes_price + expensive.no_price
        profit = 1.0 - cost
        profit_pct = (profit / cost) * 100 if cost > 0 else 0
        
        if profit_pct < self.min_profit_pct:
            return None
        
        return ArbitrageOpportunity(
            id=f"equiv_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            type="EQUIVALENT_MISPRICING",
            markets=[
                {"id": cheap.id, "question": cheap.question, "yes_price": cheap.yes_price},
                {"id": expensive.id, "question": expensive.question, "yes_price": expensive.yes_price}
            ],
            relationship="equivalent",
            confidence=analysis.get("confidence", 0.5),
            total_cost=cost,
            guaranteed_return=1.0,
            profit=profit,
            profit_pct=profit_pct,
            action=f"买 '{cheap.question[:60]}...' YES @ ${cheap.yes_price:.3f}\n"
                   f"买 '{expensive.question[:60]}...' NO @ ${expensive.no_price:.3f}",
            reasoning="等价市场存在显著价差",
            edge_cases=analysis.get("edge_cases", []),
            needs_review=["确认两个市场真的等价", "检查结算规则"],
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
    
    def _group_by_event(self, markets: List[Market]) -> Dict[str, List[Market]]:
        """按事件分组"""
        groups = {}
        for m in markets:
            key = m.event_id or m.event_title
            if key:
                if key not in groups:
                    groups[key] = []
                groups[key].append(m)
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
            print(f"\n⚠️ 需要复核:")
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
