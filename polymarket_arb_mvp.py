#!/usr/bin/env python3
"""
Polymarket 组合套利系统 - MVP版本
=====================================

这是一个可以直接运行的完整原型，包含：
1. 数据获取层（支持真实API和模拟数据）
2. 语义相似度筛选层
3. LLM逻辑关系分析层
4. 定价违规检测层
5. 机会报告层

使用方法：
1. 本地运行时，设置 USE_MOCK_DATA = False
2. 设置环境变量 ANTHROPIC_API_KEY
3. 运行 python polymarket_arb_mvp.py

作者：Claude
日期：2025-12-29
"""

import json
import os
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum
from datetime import datetime
import hashlib

# ============================================================
# 配置
# ============================================================

# 在本地环境设为False以使用真实API
USE_MOCK_DATA = True

# LLM配置
LLM_MODEL = "claude-sonnet-4-20250514"
LLM_MAX_TOKENS = 1000

# 套利阈值
MIN_PROFIT_PCT = 2.0  # 最小利润百分比
MIN_CONFIDENCE = 0.8  # 最小LLM置信度


# ============================================================
# 数据结构定义
# ============================================================

class RelationType(Enum):
    """市场间逻辑关系类型"""
    IMPLIES_AB = "implies_ab"      # A发生 → B必发生
    IMPLIES_BA = "implies_ba"      # B发生 → A必发生
    EQUIVALENT = "equivalent"      # A和B等价
    MUTUAL_EXCLUSIVE = "mutual_exclusive"  # A和B互斥
    EXHAUSTIVE = "exhaustive"      # A和B是完备集的一部分
    UNRELATED = "unrelated"        # 无关


@dataclass
class Market:
    """市场数据"""
    id: str
    question: str
    description: str
    yes_price: float
    no_price: float
    volume: float
    liquidity: float
    end_date: str
    event_id: str
    resolution_source: str = ""
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class MarketPair:
    """市场对分析结果"""
    market_a: Market
    market_b: Market
    similarity_score: float
    relationship: RelationType
    confidence: float
    reasoning: str
    constraint: str
    has_arbitrage: bool
    arbitrage_details: Optional[Dict] = None


@dataclass 
class ArbitrageOpportunity:
    """套利机会"""
    opportunity_type: str
    markets: List[Market]
    relationship: RelationType
    total_cost: float
    guaranteed_return: float
    profit: float
    profit_pct: float
    action: str
    confidence: float
    needs_review: List[str]


# ============================================================
# 模拟数据（用于演示）
# ============================================================

MOCK_MARKETS = [
    # 美国大选相关 - 存在包含关系
    Market(
        id="m1",
        question="Will Donald Trump win the 2028 US Presidential Election?",
        description="Resolves YES if Trump wins the 2028 election",
        yes_price=0.35,
        no_price=0.65,
        volume=5000000,
        liquidity=500000,
        end_date="2028-11-05",
        event_id="2028-us-election",
        resolution_source="AP News"
    ),
    Market(
        id="m2", 
        question="Will the Republican candidate win the 2028 US Presidential Election?",
        description="Resolves YES if any Republican wins",
        yes_price=0.42,  # 应该 >= Trump的概率，这里设置为合理的
        no_price=0.58,
        volume=3000000,
        liquidity=400000,
        end_date="2028-11-05",
        event_id="2028-us-election",
        resolution_source="AP News"
    ),
    
    # 故意设置一个违反逻辑的定价用于演示
    Market(
        id="m3",
        question="Will Ron DeSantis win the 2028 US Presidential Election?",
        description="Resolves YES if DeSantis wins",
        yes_price=0.15,
        no_price=0.85,
        volume=2000000,
        liquidity=200000,
        end_date="2028-11-05",
        event_id="2028-us-election",
        resolution_source="AP News"
    ),
    
    # 完备集示例 - 故意设置总和 < 1
    Market(
        id="m4",
        question="2028 Election: Republican wins by 1-49 electoral votes",
        description="GOP margin 1-49",
        yes_price=0.18,
        no_price=0.82,
        volume=1000000,
        liquidity=100000,
        end_date="2028-11-05",
        event_id="2028-gop-margin",
        resolution_source="Official results"
    ),
    Market(
        id="m5",
        question="2028 Election: Republican wins by 50-99 electoral votes",
        description="GOP margin 50-99",
        yes_price=0.12,
        no_price=0.88,
        volume=800000,
        liquidity=80000,
        end_date="2028-11-05",
        event_id="2028-gop-margin",
        resolution_source="Official results"
    ),
    Market(
        id="m6",
        question="2028 Election: Republican wins by 100+ electoral votes",
        description="GOP margin 100+",
        yes_price=0.05,
        no_price=0.95,
        volume=500000,
        liquidity=50000,
        end_date="2028-11-05",
        event_id="2028-gop-margin",
        resolution_source="Official results"
    ),
    Market(
        id="m7",
        question="2028 Election: Democrat wins the election",
        description="Democrat wins",
        yes_price=0.58,  # 总和 = 0.18+0.12+0.05+0.58 = 0.93，存在套利！
        no_price=0.42,
        volume=4000000,
        liquidity=400000,
        end_date="2028-11-05",
        event_id="2028-gop-margin",
        resolution_source="Official results"
    ),
    
    # 体育示例
    Market(
        id="m8",
        question="Will the Lakers make the 2025 NBA Playoffs?",
        description="Lakers qualify for playoffs",
        yes_price=0.72,
        no_price=0.28,
        volume=500000,
        liquidity=50000,
        end_date="2025-04-15",
        event_id="nba-2025-playoffs",
        resolution_source="NBA official"
    ),
    Market(
        id="m9",
        question="Will the Lakers win the 2025 NBA Championship?",
        description="Lakers win finals",
        yes_price=0.08,
        no_price=0.92,
        volume=1000000,
        liquidity=100000,
        end_date="2025-06-20",
        event_id="nba-2025-champion",
        resolution_source="NBA official"
    ),
]


# ============================================================
# 第一层：数据获取
# ============================================================

class DataFetcher:
    """数据获取层"""
    
    def __init__(self, use_mock: bool = True):
        self.use_mock = use_mock
        
    def fetch_markets(self, limit: int = 100) -> List[Market]:
        """获取市场列表"""
        if self.use_mock:
            return MOCK_MARKETS[:limit]
        else:
            return self._fetch_real_markets(limit)
    
    def _fetch_real_markets(self, limit: int) -> List[Market]:
        """从真实API获取数据"""
        import requests
        
        url = "https://gamma-api.polymarket.com/markets"
        params = {
            "active": "true",
            "closed": "false",
            "limit": limit,
            "order": "volume",
            "ascending": "false"
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            markets = []
            for item in data:
                try:
                    prices = item.get('outcomePrices', '["0.5","0.5"]')
                    if isinstance(prices, str):
                        prices = json.loads(prices)
                    yes_price = float(prices[0]) if prices else 0.5
                    
                    market = Market(
                        id=item.get('id', ''),
                        question=item.get('question', ''),
                        description=item.get('description', ''),
                        yes_price=yes_price,
                        no_price=1 - yes_price,
                        volume=float(item.get('volume', 0) or 0),
                        liquidity=float(item.get('liquidity', 0) or 0),
                        end_date=item.get('endDate', ''),
                        event_id=item.get('eventSlug', '') or '',
                        resolution_source=item.get('resolutionSource', '')
                    )
                    markets.append(market)
                except Exception as e:
                    print(f"解析失败: {e}")
                    continue
            
            return markets
            
        except Exception as e:
            print(f"API请求失败: {e}")
            return []


# ============================================================
# 第二层：语义相似度筛选
# ============================================================

class SimilarityFilter:
    """语义相似度筛选层
    
    在真实使用时，这里会用sentence-transformers + 向量数据库
    MVP版本用简单的关键词匹配
    """
    
    def __init__(self):
        self.use_embeddings = False  # MVP版本不使用
        
    def find_similar_pairs(self, markets: List[Market], 
                           threshold: float = 0.5) -> List[Tuple[Market, Market, float]]:
        """找出相似的市场对"""
        pairs = []
        
        for i, m1 in enumerate(markets):
            for m2 in markets[i+1:]:
                score = self._calculate_similarity(m1, m2)
                if score >= threshold:
                    pairs.append((m1, m2, score))
        
        # 按相似度排序
        pairs.sort(key=lambda x: x[2], reverse=True)
        return pairs
    
    def _calculate_similarity(self, m1: Market, m2: Market) -> float:
        """计算两个市场的相似度（简化版）"""
        # 简单的关键词重叠计算
        words1 = set(m1.question.lower().split())
        words2 = set(m2.question.lower().split())
        
        # 移除常见词
        stop_words = {'will', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'by'}
        words1 = words1 - stop_words
        words2 = words2 - stop_words
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        jaccard = intersection / union if union > 0 else 0
        
        # 如果是同一个event，提高分数
        if m1.event_id and m1.event_id == m2.event_id:
            jaccard = min(1.0, jaccard + 0.3)
        
        # 如果结算日期相同，提高分数
        if m1.end_date and m1.end_date == m2.end_date:
            jaccard = min(1.0, jaccard + 0.1)
            
        return jaccard


# ============================================================
# 第三层：LLM逻辑关系分析
# ============================================================

# LLM分析的Prompt模板
RELATIONSHIP_ANALYSIS_PROMPT = """你是一个逻辑分析专家，专门分析预测市场之间的逻辑关系。

请分析以下两个预测市场之间的逻辑关系：

**市场A:**
- 问题: {question_a}
- 描述: {description_a}
- 结算来源: {source_a}

**市场B:**
- 问题: {question_b}
- 描述: {description_b}
- 结算来源: {source_b}

请判断它们之间的关系，必须是以下类型之一：

1. **IMPLIES_AB**: A发生必然导致B发生（A → B）
   例如："特朗普赢得总统" → "共和党赢得总统"

2. **IMPLIES_BA**: B发生必然导致A发生（B → A）

3. **EQUIVALENT**: A和B本质上是同一问题的不同表述

4. **MUTUAL_EXCLUSIVE**: A和B不能同时发生（但可能都不发生）
   例如："湖人夺冠" vs "凯尔特人夺冠"

5. **EXHAUSTIVE**: A和B是覆盖所有可能结果的完备集的一部分
   例如：选举人票的各个区间

6. **UNRELATED**: 没有明确的逻辑关系

请严格按以下JSON格式回答（不要有其他内容）：
```json
{{
  "relationship": "类型（上述6个之一）",
  "confidence": 0.0到1.0之间的数字,
  "reasoning": "你的分析理由，要具体",
  "constraint": "如果存在概率约束，写出来，如 P(B) >= P(A)；如果没有，写null",
  "edge_cases": ["可能导致判断出错的边界情况列表"]
}}
```
"""


class LLMAnalyzer:
    """LLM逻辑关系分析层"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.use_mock = not self.api_key
        
        if self.use_mock:
            print("⚠️ 未设置ANTHROPIC_API_KEY，使用模拟LLM响应")
    
    def analyze_pair(self, market_a: Market, market_b: Market) -> Dict:
        """分析两个市场的逻辑关系"""
        if self.use_mock:
            return self._mock_analysis(market_a, market_b)
        else:
            return self._real_analysis(market_a, market_b)
    
    def _mock_analysis(self, market_a: Market, market_b: Market) -> Dict:
        """模拟LLM分析（基于规则）"""
        q_a = market_a.question.lower()
        q_b = market_b.question.lower()
        
        # 规则1：个人 vs 政党
        if ("trump" in q_a or "desantis" in q_a) and "republican" in q_b:
            return {
                "relationship": "IMPLIES_AB",
                "confidence": 0.95,
                "reasoning": "如果特定共和党候选人获胜，则共和党必然获胜",
                "constraint": "P(Republican wins) >= P(Individual wins)",
                "edge_cases": ["候选人可能退出或更换党派"]
            }
        
        if "republican" in q_a and ("trump" in q_b or "desantis" in q_b):
            return {
                "relationship": "IMPLIES_BA",
                "confidence": 0.95,
                "reasoning": "如果特定共和党候选人获胜，则共和党必然获胜",
                "constraint": "P(Republican wins) >= P(Individual wins)",
                "edge_cases": ["候选人可能退出或更换党派"]
            }
        
        # 规则2：进入季后赛 vs 夺冠
        if "playoff" in q_a and "championship" in q_b:
            if market_a.event_id.split("-")[0] == market_b.event_id.split("-")[0]:  # 同一联赛
                return {
                    "relationship": "IMPLIES_BA",
                    "confidence": 0.99,
                    "reasoning": "夺冠必须先进入季后赛",
                    "constraint": "P(Playoffs) >= P(Championship)",
                    "edge_cases": []
                }
        
        if "championship" in q_a and "playoff" in q_b:
            return {
                "relationship": "IMPLIES_AB",
                "confidence": 0.99,
                "reasoning": "夺冠必须先进入季后赛",
                "constraint": "P(Playoffs) >= P(Championship)",
                "edge_cases": []
            }
        
        # 规则3：选举人票区间（完备集）
        if "electoral" in q_a and "electoral" in q_b:
            return {
                "relationship": "MUTUAL_EXCLUSIVE",
                "confidence": 0.95,
                "reasoning": "不同的选举人票区间互斥",
                "constraint": "这些区间应该构成完备集",
                "edge_cases": ["区间定义可能有重叠或遗漏"]
            }
        
        # 规则4：同一事件的不同结果
        if market_a.event_id and market_a.event_id == market_b.event_id:
            if "republican" in q_a and "democrat" in q_b:
                return {
                    "relationship": "MUTUAL_EXCLUSIVE",
                    "confidence": 0.90,
                    "reasoning": "共和党和民主党获胜互斥",
                    "constraint": "P(GOP) + P(DEM) <= 1.0",
                    "edge_cases": ["可能有第三方候选人"]
                }
        
        # 默认：无法确定关系
        return {
            "relationship": "UNRELATED",
            "confidence": 0.5,
            "reasoning": "未能识别出明确的逻辑关系",
            "constraint": None,
            "edge_cases": ["需要人工复核"]
        }
    
    def _real_analysis(self, market_a: Market, market_b: Market) -> Dict:
        """调用真实LLM API"""
        try:
            import anthropic
            
            client = anthropic.Anthropic(api_key=self.api_key)
            
            prompt = RELATIONSHIP_ANALYSIS_PROMPT.format(
                question_a=market_a.question,
                description_a=market_a.description,
                source_a=market_a.resolution_source,
                question_b=market_b.question,
                description_b=market_b.description,
                source_b=market_b.resolution_source
            )
            
            response = client.messages.create(
                model=LLM_MODEL,
                max_tokens=LLM_MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # 解析JSON响应
            content = response.content[0].text
            # 提取JSON部分
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            return json.loads(content.strip())
            
        except Exception as e:
            print(f"LLM API调用失败: {e}")
            return self._mock_analysis(market_a, market_b)


# ============================================================
# 第四层：定价违规检测
# ============================================================

class ArbitrageDetector:
    """套利机会检测层"""
    
    def __init__(self):
        self.min_profit_pct = MIN_PROFIT_PCT
    
    def check_implication(self, market_a: Market, market_b: Market, 
                          analysis: Dict) -> Optional[ArbitrageOpportunity]:
        """检查包含关系是否被违反"""
        rel = analysis.get("relationship", "")
        
        if rel == "IMPLIES_AB":
            # A → B，所以 P(B) >= P(A)
            if market_b.yes_price < market_a.yes_price - 0.01:
                return self._create_implication_opportunity(
                    market_a, market_b, analysis, "A→B"
                )
        
        elif rel == "IMPLIES_BA":
            # B → A，所以 P(A) >= P(B)
            if market_a.yes_price < market_b.yes_price - 0.01:
                return self._create_implication_opportunity(
                    market_b, market_a, analysis, "B→A"
                )
        
        return None
    
    def _create_implication_opportunity(self, implied_market: Market, 
                                        implying_market: Market,
                                        analysis: Dict, 
                                        direction: str) -> Optional[ArbitrageOpportunity]:
        """创建包含关系套利机会"""
        # 买implied市场的YES，买implying市场的NO
        cost = implied_market.yes_price + implying_market.no_price
        profit = 1.0 - cost
        profit_pct = (profit / cost) * 100 if cost > 0 else 0
        
        if profit_pct < self.min_profit_pct:
            return None
        
        return ArbitrageOpportunity(
            opportunity_type="IMPLICATION_VIOLATION",
            markets=[implied_market, implying_market],
            relationship=RelationType.IMPLIES_AB if direction == "A→B" else RelationType.IMPLIES_BA,
            total_cost=cost,
            guaranteed_return=1.0,
            profit=profit,
            profit_pct=profit_pct,
            action=f"买 '{implied_market.question}' YES @ ${implied_market.yes_price:.3f}\n"
                   f"买 '{implying_market.question}' NO @ ${implying_market.no_price:.3f}",
            confidence=analysis.get("confidence", 0.5),
            needs_review=analysis.get("edge_cases", [])
        )
    
    def check_exhaustive_set(self, markets: List[Market], 
                              analysis: Dict) -> Optional[ArbitrageOpportunity]:
        """检查完备集是否存在套利"""
        total = sum(m.yes_price for m in markets)
        
        if total < 0.98:  # 总和小于1，存在套利
            profit = 1.0 - total
            profit_pct = (profit / total) * 100 if total > 0 else 0
            
            if profit_pct < self.min_profit_pct:
                return None
            
            action_lines = [f"买 '{m.question}' YES @ ${m.yes_price:.3f}" for m in markets]
            
            return ArbitrageOpportunity(
                opportunity_type="EXHAUSTIVE_SET_UNDERPRICED",
                markets=markets,
                relationship=RelationType.EXHAUSTIVE,
                total_cost=total,
                guaranteed_return=1.0,
                profit=profit,
                profit_pct=profit_pct,
                action="\n".join(action_lines),
                confidence=analysis.get("confidence", 0.8),
                needs_review=["确认这些选项构成完备集", "检查结算规则是否一致"]
            )
        
        return None


# ============================================================
# 第五层：主流程编排
# ============================================================

class PolymarketArbitrageSystem:
    """组合套利系统主类"""
    
    def __init__(self, use_mock: bool = True, api_key: str = None):
        self.data_fetcher = DataFetcher(use_mock=use_mock)
        self.similarity_filter = SimilarityFilter()
        self.llm_analyzer = LLMAnalyzer(api_key=api_key)
        self.arbitrage_detector = ArbitrageDetector()
        
    def scan(self, limit: int = 100) -> List[ArbitrageOpportunity]:
        """执行完整扫描流程"""
        opportunities = []
        
        print("\n" + "=" * 60)
        print("Polymarket 组合套利扫描系统")
        print("=" * 60)
        
        # Step 1: 获取市场数据
        print("\n[1/5] 获取市场数据...")
        markets = self.data_fetcher.fetch_markets(limit=limit)
        print(f"     获取到 {len(markets)} 个市场")
        
        if not markets:
            print("     ❌ 无法获取市场数据")
            return []
        
        # Step 2: 按事件分组，寻找完备集
        print("\n[2/5] 寻找完备集...")
        event_groups = self._group_by_event(markets)
        print(f"     发现 {len(event_groups)} 个事件组")
        
        for event_id, group in event_groups.items():
            if len(group) >= 2:
                # 检查是否是完备集
                total = sum(m.yes_price for m in group)
                print(f"     - {event_id}: {len(group)}个市场, 总和={total:.3f}")
                
                if total < 0.98:
                    opp = self.arbitrage_detector.check_exhaustive_set(
                        group, 
                        {"confidence": 0.85, "edge_cases": ["需要确认完备性"]}
                    )
                    if opp:
                        opportunities.append(opp)
                        print(f"       🎯 发现套利! 利润={opp.profit_pct:.2f}%")
        
        # Step 3: 寻找相似市场对
        print("\n[3/5] 寻找相似市场对...")
        similar_pairs = self.similarity_filter.find_similar_pairs(markets, threshold=0.3)
        print(f"     发现 {len(similar_pairs)} 对相似市场")
        
        # Step 4: LLM分析逻辑关系
        print("\n[4/5] 分析逻辑关系...")
        
        for m1, m2, similarity in similar_pairs[:20]:  # 限制分析数量
            print(f"     分析: '{m1.question[:40]}...' vs '{m2.question[:40]}...'")
            
            analysis = self.llm_analyzer.analyze_pair(m1, m2)
            rel = analysis.get("relationship", "UNRELATED")
            conf = analysis.get("confidence", 0)
            
            print(f"       关系: {rel}, 置信度: {conf:.2f}")
            
            if rel in ["IMPLIES_AB", "IMPLIES_BA"]:
                opp = self.arbitrage_detector.check_implication(m1, m2, analysis)
                if opp:
                    opportunities.append(opp)
                    print(f"       🎯 发现套利! 利润={opp.profit_pct:.2f}%")
        
        # Step 5: 输出报告
        print("\n[5/5] 生成报告...")
        self._print_report(opportunities)
        
        return opportunities
    
    def _group_by_event(self, markets: List[Market]) -> Dict[str, List[Market]]:
        """按事件ID分组"""
        groups = {}
        for m in markets:
            if m.event_id:
                if m.event_id not in groups:
                    groups[m.event_id] = []
                groups[m.event_id].append(m)
        return groups
    
    def _print_report(self, opportunities: List[ArbitrageOpportunity]):
        """打印套利机会报告"""
        print("\n" + "=" * 60)
        print("扫描报告")
        print("=" * 60)
        
        if not opportunities:
            print("\n暂未发现符合条件的套利机会")
            print("这很正常——机会不是时时都有")
            return
        
        print(f"\n发现 {len(opportunities)} 个潜在套利机会:\n")
        
        for i, opp in enumerate(opportunities, 1):
            print(f"{'─' * 50}")
            print(f"机会 #{i}: {opp.opportunity_type}")
            print(f"{'─' * 50}")
            print(f"逻辑关系: {opp.relationship.value}")
            print(f"置信度: {opp.confidence:.0%}")
            print(f"总成本: ${opp.total_cost:.4f}")
            print(f"保证回报: ${opp.guaranteed_return:.4f}")
            print(f"利润: ${opp.profit:.4f} ({opp.profit_pct:.2f}%)")
            print(f"\n操作:")
            for line in opp.action.split('\n'):
                print(f"  {line}")
            
            if opp.needs_review:
                print(f"\n⚠️ 需要人工复核:")
                for item in opp.needs_review:
                    print(f"  - {item}")
            print()
        
        # 保存到文件
        output = {
            "timestamp": datetime.now().isoformat(),
            "opportunities": [
                {
                    "type": opp.opportunity_type,
                    "markets": [m.question for m in opp.markets],
                    "profit_pct": opp.profit_pct,
                    "action": opp.action,
                    "confidence": opp.confidence,
                    "needs_review": opp.needs_review
                }
                for opp in opportunities
            ]
        }
        
        with open("arbitrage_report.json", "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ 报告已保存到 arbitrage_report.json")


# ============================================================
# 主程序入口
# ============================================================

def main():
    """主程序"""
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║     Polymarket 组合套利系统 - MVP版本                      ║
    ║                                                           ║
    ║  本系统用于识别预测市场中的逻辑定价违规套利机会             ║
    ║                                                           ║
    ║  当前模式: """ + ("模拟数据" if USE_MOCK_DATA else "真实API") + """                                      ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    # 创建系统实例
    system = PolymarketArbitrageSystem(
        use_mock=USE_MOCK_DATA,
        api_key=os.getenv("ANTHROPIC_API_KEY")
    )
    
    # 执行扫描
    opportunities = system.scan(limit=100)
    
    print("\n" + "=" * 60)
    print("扫描完成！")
    print("=" * 60)
    
    if opportunities:
        print(f"\n下一步行动:")
        print("1. 查看 arbitrage_report.json 获取详细信息")
        print("2. 对每个机会进行人工复核")
        print("3. 确认结算规则一致性")
        print("4. 检查流动性是否足够")
        print("5. 小额测试执行")


if __name__ == "__main__":
    main()
