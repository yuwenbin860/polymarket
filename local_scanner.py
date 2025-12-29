#!/usr/bin/env python3
"""
Polymarket 组合套利系统 - 本地完整版
====================================

这个版本用于在你的本地环境运行，包含：
1. 真实的Polymarket API调用
2. 完整的Claude LLM分析
3. 更详细的报告输出

使用方法：
1. pip install requests anthropic
2. export ANTHROPIC_API_KEY="your-key"
3. python local_scanner.py
"""

import requests
import json
import os
import sys
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Tuple
from datetime import datetime
from enum import Enum

# ============================================================
# 配置
# ============================================================

class Config:
    # API配置
    POLYMARKET_API = "https://gamma-api.polymarket.com"
    CLOB_API = "https://clob.polymarket.com"
    
    # LLM配置
    LLM_MODEL = "claude-sonnet-4-20250514"
    LLM_MAX_TOKENS = 1500
    
    # 扫描配置
    MARKET_LIMIT = 200  # 获取市场数量
    SIMILARITY_THRESHOLD = 0.3  # 相似度阈值
    MIN_PROFIT_PCT = 2.0  # 最小利润百分比
    MIN_LIQUIDITY = 10000  # 最小流动性要求
    MIN_CONFIDENCE = 0.8  # 最小LLM置信度
    
    # 输出配置
    OUTPUT_FILE = "arbitrage_opportunities.json"
    DETAILED_LOG = True


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
    
    def __init__(self):
        self.base_url = Config.POLYMARKET_API
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "PolymarketArbitrageScanner/1.0"
        })
    
    def get_markets(self, limit: int = 100, active: bool = True) -> List[Market]:
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
                    if market and market.liquidity >= Config.MIN_LIQUIDITY:
                        markets.append(market)
                except Exception as e:
                    print(f"  解析市场失败: {e}")
                    continue
            
            return markets
            
        except requests.RequestException as e:
            print(f"API请求失败: {e}")
            return []
    
    def get_events(self, limit: int = 50) -> List[Dict]:
        """获取事件列表"""
        url = f"{self.base_url}/events"
        params = {
            "limit": limit,
            "active": "true",
            "closed": "false",
            "order": "volume",
            "ascending": "false"
        }
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"获取事件失败: {e}")
            return []
    
    def get_markets_by_event(self, event_slug: str) -> List[Market]:
        """获取某事件下的所有市场"""
        url = f"{self.base_url}/markets"
        params = {
            "event_slug": event_slug,
            "limit": 100
        }
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            markets = []
            for item in data:
                try:
                    market = self._parse_market(item)
                    if market:
                        markets.append(market)
                except:
                    continue
            
            return markets
        except Exception as e:
            print(f"获取事件市场失败: {e}")
            return []
    
    def _parse_market(self, data: Dict) -> Optional[Market]:
        """解析市场数据"""
        try:
            # 解析价格
            outcome_prices = data.get('outcomePrices', '["0.5","0.5"]')
            if isinstance(outcome_prices, str):
                prices = json.loads(outcome_prices)
            else:
                prices = outcome_prices
            
            yes_price = float(prices[0]) if prices else 0.5
            
            # 解析outcomes
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
        except Exception as e:
            return None


# ============================================================
# LLM分析器
# ============================================================

ANALYSIS_PROMPT = """你是一个专门分析预测市场逻辑关系的专家。

请分析以下两个Polymarket预测市场之间的逻辑关系：

**市场A:**
- 问题: {question_a}
- 描述: {description_a}
- 当前YES价格: ${price_a:.3f}
- 结算来源: {source_a}
- 结算日期: {end_a}

**市场B:**
- 问题: {question_b}
- 描述: {description_b}
- 当前YES价格: ${price_b:.3f}
- 结算来源: {source_b}
- 结算日期: {end_b}

请判断它们之间的逻辑关系，必须是以下类型之一：

1. **IMPLIES_AB**: A发生必然导致B发生（A → B）
   - 概率约束: P(B) >= P(A)
   - 如果 P(B) < P(A)，则存在套利
   
2. **IMPLIES_BA**: B发生必然导致A发生（B → A）  
   - 概率约束: P(A) >= P(B)
   - 如果 P(A) < P(B)，则存在套利

3. **EQUIVALENT**: A和B本质上是同一问题的不同表述
   - 概率约束: P(A) ≈ P(B)
   - 如果价差超过3%，则存在套利

4. **MUTUAL_EXCLUSIVE**: A和B不能同时发生（但可能都不发生）
   - 概率约束: P(A) + P(B) <= 1
   - 如果总和超过1，可能存在套利（做空）

5. **EXHAUSTIVE**: A和B是覆盖所有可能结果的完备集的一部分
   - 如果能收集完整集合，检查总和是否<1

6. **UNRELATED**: 没有明确的逻辑关系

请特别注意：
- 结算规则是否相同或兼容
- 是否有可能出现两边都赢或都输的情况
- 第三方候选人、意外事件等边界情况

请严格按以下JSON格式回答（不要有任何其他内容）：
```json
{{
  "relationship": "类型",
  "confidence": 0.0-1.0,
  "reasoning": "详细分析理由",
  "probability_constraint": "约束表达式，如 P(B) >= P(A)",
  "current_prices_valid": true或false,
  "arbitrage_exists": true或false,
  "edge_cases": ["可能导致判断出错的边界情况"],
  "resolution_compatible": true或false,
  "resolution_notes": "结算规则兼容性说明"
}}
```"""


class LLMAnalyzer:
    """Claude LLM分析器"""
    
    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            print("⚠️ 警告: 未设置ANTHROPIC_API_KEY环境变量")
            print("   将使用规则匹配替代LLM分析")
            self.use_llm = False
        else:
            self.use_llm = True
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                print("⚠️ 警告: 未安装anthropic库，请运行: pip install anthropic")
                self.use_llm = False
    
    def analyze(self, market_a: Market, market_b: Market) -> Dict:
        """分析两个市场的逻辑关系"""
        if self.use_llm:
            return self._analyze_with_llm(market_a, market_b)
        else:
            return self._analyze_with_rules(market_a, market_b)
    
    def _analyze_with_llm(self, market_a: Market, market_b: Market) -> Dict:
        """使用Claude API分析"""
        prompt = ANALYSIS_PROMPT.format(
            question_a=market_a.question,
            description_a=market_a.description[:500],
            price_a=market_a.yes_price,
            source_a=market_a.resolution_source,
            end_a=market_a.end_date,
            question_b=market_b.question,
            description_b=market_b.description[:500],
            price_b=market_b.yes_price,
            source_b=market_b.resolution_source,
            end_b=market_b.end_date
        )
        
        try:
            response = self.client.messages.create(
                model=Config.LLM_MODEL,
                max_tokens=Config.LLM_MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
            
            # 提取JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            result = json.loads(content.strip())
            return result
            
        except Exception as e:
            print(f"    LLM分析失败: {e}")
            return self._analyze_with_rules(market_a, market_b)
    
    def _analyze_with_rules(self, market_a: Market, market_b: Market) -> Dict:
        """使用规则匹配分析（备用方案）"""
        q_a = market_a.question.lower()
        q_b = market_b.question.lower()
        
        # 规则1: 个人候选人 vs 政党
        candidates = ["trump", "biden", "harris", "desantis", "haley", "newsom"]
        parties = ["republican", "democrat", "gop", "dem"]
        
        candidate_in_a = any(c in q_a for c in candidates)
        candidate_in_b = any(c in q_b for c in candidates)
        party_in_a = any(p in q_a for p in parties)
        party_in_b = any(p in q_b for p in parties)
        
        if candidate_in_a and party_in_b and not candidate_in_b:
            # A是个人，B是政党
            if ("republican" in q_b and any(c in q_a for c in ["trump", "desantis", "haley"])) or \
               ("democrat" in q_b and any(c in q_a for c in ["biden", "harris", "newsom"])):
                return {
                    "relationship": "IMPLIES_AB",
                    "confidence": 0.9,
                    "reasoning": "个人候选人获胜意味着其政党获胜",
                    "probability_constraint": "P(Party) >= P(Candidate)",
                    "current_prices_valid": market_b.yes_price >= market_a.yes_price,
                    "arbitrage_exists": market_b.yes_price < market_a.yes_price - 0.02,
                    "edge_cases": ["候选人可能退出", "独立参选"],
                    "resolution_compatible": True,
                    "resolution_notes": "需确认结算源一致"
                }
        
        # 规则2: 夺冠 vs 进季后赛
        if "champion" in q_a and "playoff" in q_b:
            return {
                "relationship": "IMPLIES_AB",
                "confidence": 0.99,
                "reasoning": "夺冠必须先进入季后赛",
                "probability_constraint": "P(Playoffs) >= P(Championship)",
                "current_prices_valid": market_b.yes_price >= market_a.yes_price,
                "arbitrage_exists": market_b.yes_price < market_a.yes_price - 0.02,
                "edge_cases": [],
                "resolution_compatible": True,
                "resolution_notes": "逻辑关系明确"
            }
        
        if "playoff" in q_a and "champion" in q_b:
            return {
                "relationship": "IMPLIES_BA",
                "confidence": 0.99,
                "reasoning": "夺冠必须先进入季后赛",
                "probability_constraint": "P(Playoffs) >= P(Championship)",
                "current_prices_valid": market_a.yes_price >= market_b.yes_price,
                "arbitrage_exists": market_a.yes_price < market_b.yes_price - 0.02,
                "edge_cases": [],
                "resolution_compatible": True,
                "resolution_notes": "逻辑关系明确"
            }
        
        # 规则3: 同一事件的互斥结果
        if market_a.event_id and market_a.event_id == market_b.event_id:
            return {
                "relationship": "MUTUAL_EXCLUSIVE",
                "confidence": 0.8,
                "reasoning": "同一事件下的不同结果通常互斥",
                "probability_constraint": "可能是完备集的一部分",
                "current_prices_valid": True,
                "arbitrage_exists": False,
                "edge_cases": ["需要检查是否构成完备集"],
                "resolution_compatible": True,
                "resolution_notes": "同一事件，结算规则应一致"
            }
        
        # 默认: 无法确定
        return {
            "relationship": "UNRELATED",
            "confidence": 0.5,
            "reasoning": "未能通过规则匹配识别逻辑关系",
            "probability_constraint": None,
            "current_prices_valid": True,
            "arbitrage_exists": False,
            "edge_cases": ["需要人工分析"],
            "resolution_compatible": None,
            "resolution_notes": "需要人工检查"
        }


# ============================================================
# 套利检测器
# ============================================================

class ArbitrageDetector:
    """套利机会检测器"""
    
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
        
        if total < 0.98:  # 留2%给滑点和手续费
            profit = 1.0 - total
            profit_pct = (profit / total) * 100
            
            if profit_pct < Config.MIN_PROFIT_PCT:
                return None
            
            action_lines = []
            for m in markets:
                action_lines.append(f"买 '{m.question[:60]}...' YES @ ${m.yes_price:.3f}")
            
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
        # implying → implied，所以 P(implied) >= P(implying)
        if implied.yes_price >= implying.yes_price - 0.01:
            return None  # 定价正确，无套利
        
        # 存在套利：买implied的YES，买implying的NO
        cost = implied.yes_price + implying.no_price
        profit = 1.0 - cost
        profit_pct = (profit / cost) * 100 if cost > 0 else 0
        
        if profit_pct < Config.MIN_PROFIT_PCT:
            return None
        
        if analysis.get("confidence", 0) < Config.MIN_CONFIDENCE:
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
                analysis.get("resolution_notes", "")
            ],
            timestamp=datetime.now().isoformat()
        )
    
    def _check_equivalent(self, market_a: Market, market_b: Market, 
                          analysis: Dict) -> Optional[ArbitrageOpportunity]:
        """检查等价市场套利"""
        spread = abs(market_a.yes_price - market_b.yes_price)
        
        if spread < 0.03:  # 价差小于3%
            return None
        
        if market_a.yes_price < market_b.yes_price:
            cheap, expensive = market_a, market_b
        else:
            cheap, expensive = market_b, market_a
        
        return ArbitrageOpportunity(
            id=f"equiv_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            type="EQUIVALENT_MISPRICING",
            markets=[
                {"id": cheap.id, "question": cheap.question, "yes_price": cheap.yes_price},
                {"id": expensive.id, "question": expensive.question, "yes_price": expensive.yes_price}
            ],
            relationship="equivalent",
            confidence=analysis.get("confidence", 0.5),
            total_cost=cheap.yes_price + expensive.no_price,
            guaranteed_return=1.0,
            profit=spread,
            profit_pct=(spread / cheap.yes_price) * 100,
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
    
    def find_similar_pairs(self, markets: List[Market]) -> List[Tuple[Market, Market, float]]:
        """找出相似的市场对"""
        pairs = []
        
        for i, m1 in enumerate(markets):
            for m2 in markets[i+1:]:
                score = self._calculate_similarity(m1, m2)
                if score >= Config.SIMILARITY_THRESHOLD:
                    pairs.append((m1, m2, score))
        
        pairs.sort(key=lambda x: x[2], reverse=True)
        return pairs
    
    def _calculate_similarity(self, m1: Market, m2: Market) -> float:
        """计算相似度"""
        # Jaccard相似度
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
        
        # 同一结算日加分
        if m1.end_date and m1.end_date == m2.end_date:
            jaccard = min(1.0, jaccard + 0.1)
        
        return jaccard


# ============================================================
# 主扫描器
# ============================================================

class ArbitrageScanner:
    """主扫描器"""
    
    def __init__(self):
        self.client = PolymarketClient()
        self.analyzer = LLMAnalyzer()
        self.detector = ArbitrageDetector()
        self.filter = SimilarityFilter()
    
    def scan(self) -> List[ArbitrageOpportunity]:
        """执行完整扫描"""
        opportunities = []
        
        self._print_header()
        
        # Step 1: 获取市场
        print("\n[1/4] 获取市场数据...")
        markets = self.client.get_markets(limit=Config.MARKET_LIMIT)
        print(f"      获取到 {len(markets)} 个高流动性市场")
        
        if not markets:
            print("      ❌ 无法获取市场数据，请检查网络连接")
            return []
        
        # Step 2: 检查完备集
        print("\n[2/4] 扫描完备集套利...")
        event_groups = self._group_by_event(markets)
        print(f"      发现 {len(event_groups)} 个事件组")
        
        for event_id, group in event_groups.items():
            if len(group) >= 2:
                total = sum(m.yes_price for m in group)
                if Config.DETAILED_LOG:
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
        for m1, m2, sim in similar_pairs:
            if analyzed >= 30:  # 限制LLM调用次数
                break
            
            # 跳过同一事件的（已在完备集检查中处理）
            if m1.event_id and m1.event_id == m2.event_id:
                continue
            
            analyzed += 1
            if Config.DETAILED_LOG:
                print(f"      分析 #{analyzed}: {m1.question[:40]}... vs {m2.question[:40]}...")
            
            analysis = self.analyzer.analyze(m1, m2)
            rel = analysis.get("relationship", "UNRELATED")
            conf = analysis.get("confidence", 0)
            
            if Config.DETAILED_LOG:
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
        print("""
╔═══════════════════════════════════════════════════════════════╗
║         Polymarket 组合套利扫描系统 v1.0                       ║
║                                                               ║
║  扫描模式: """ + ("LLM分析" if self.analyzer.use_llm else "规则匹配") + """                                         ║
║  最小利润: """ + f"{Config.MIN_PROFIT_PCT}%" + """                                              ║
║  最小流动性: $""" + f"{Config.MIN_LIQUIDITY:,}" + """                                       ║
╚═══════════════════════════════════════════════════════════════╝
        """)
    
    def _save_report(self, opportunities: List[ArbitrageOpportunity]):
        """保存报告"""
        report = {
            "scan_time": datetime.now().isoformat(),
            "config": {
                "min_profit_pct": Config.MIN_PROFIT_PCT,
                "min_liquidity": Config.MIN_LIQUIDITY,
                "min_confidence": Config.MIN_CONFIDENCE
            },
            "opportunities_count": len(opportunities),
            "opportunities": [asdict(opp) for opp in opportunities]
        }
        
        with open(Config.OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"      ✅ 报告已保存到 {Config.OUTPUT_FILE}")
    
    def _print_summary(self, opportunities: List[ArbitrageOpportunity]):
        """打印摘要"""
        print("\n" + "=" * 65)
        print("扫描结果摘要")
        print("=" * 65)
        
        if not opportunities:
            print("\n暂未发现符合条件的套利机会")
            print("这很正常——好机会不是时时都有\n")
            print("建议：")
            print("  1. 降低 MIN_PROFIT_PCT 阈值尝试")
            print("  2. 在重大事件（选举、比赛）前后扫描")
            print("  3. 设置定时任务定期扫描")
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
        
        print("=" * 65)
        print("下一步行动:")
        print("  1. 仔细阅读每个机会的复核项目")
        print("  2. 在Polymarket上验证当前价格")
        print("  3. 阅读市场的结算规则")
        print("  4. 小额测试（$10-50）")
        print("=" * 65)


# ============================================================
# 主程序入口
# ============================================================

def main():
    """主程序"""
    scanner = ArbitrageScanner()
    opportunities = scanner.scan()
    
    return len(opportunities)


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
