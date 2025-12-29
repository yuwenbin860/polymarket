#!/usr/bin/env python3
"""
Phase 0: Polymarket组合套利验证脚本
目标：验证核心链路能跑通
1. 获取Polymarket市场数据
2. 找到相关市场对
3. 用LLM分析逻辑关系
4. 检查定价是否违规
"""

import requests
import json
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

# ============================================================
# 第一部分：数据获取
# ============================================================

GAMMA_API_BASE = "https://gamma-api.polymarket.com"

@dataclass
class Market:
    """市场数据结构"""
    id: str
    question: str
    description: str
    yes_price: float
    no_price: float
    volume: float
    liquidity: float
    end_date: str
    outcome: str  # 结算结果，未结算为空
    event_id: str  # 所属事件ID
    
    def __repr__(self):
        return f"Market('{self.question[:50]}...', YES={self.yes_price:.2f}, NO={self.no_price:.2f})"


def fetch_active_markets(limit: int = 100) -> List[Market]:
    """获取活跃市场列表"""
    url = f"{GAMMA_API_BASE}/markets"
    
    # 只获取活跃的、有流动性的市场
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
                # 解析价格
                yes_price = float(item.get('outcomePrices', '["0.5","0.5"]').strip('[]').split(',')[0].strip('"'))
                no_price = 1 - yes_price
                
                market = Market(
                    id=item.get('id', ''),
                    question=item.get('question', ''),
                    description=item.get('description', ''),
                    yes_price=yes_price,
                    no_price=no_price,
                    volume=float(item.get('volume', 0) or 0),
                    liquidity=float(item.get('liquidity', 0) or 0),
                    end_date=item.get('endDate', ''),
                    outcome=item.get('outcome', ''),
                    event_id=item.get('eventSlug', '') or item.get('event_id', '')
                )
                markets.append(market)
            except Exception as e:
                print(f"解析市场数据失败: {e}")
                continue
                
        return markets
        
    except requests.RequestException as e:
        print(f"API请求失败: {e}")
        return []


def fetch_events(limit: int = 50) -> List[Dict]:
    """获取事件列表（事件包含多个相关市场）"""
    url = f"{GAMMA_API_BASE}/events"
    
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
        return response.json()
    except requests.RequestException as e:
        print(f"获取事件失败: {e}")
        return []


def get_markets_by_event(event_slug: str) -> List[Market]:
    """获取某个事件下的所有市场"""
    url = f"{GAMMA_API_BASE}/markets"
    
    params = {
        "event_slug": event_slug,
        "limit": 100
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        markets = []
        for item in data:
            try:
                yes_price = float(item.get('outcomePrices', '["0.5","0.5"]').strip('[]').split(',')[0].strip('"'))
                no_price = 1 - yes_price
                
                market = Market(
                    id=item.get('id', ''),
                    question=item.get('question', ''),
                    description=item.get('description', ''),
                    yes_price=yes_price,
                    no_price=no_price,
                    volume=float(item.get('volume', 0) or 0),
                    liquidity=float(item.get('liquidity', 0) or 0),
                    end_date=item.get('endDate', ''),
                    outcome=item.get('outcome', ''),
                    event_id=event_slug
                )
                markets.append(market)
            except Exception as e:
                continue
                
        return markets
        
    except requests.RequestException as e:
        print(f"获取事件市场失败: {e}")
        return []


# ============================================================
# 第二部分：逻辑关系分析（LLM部分的模拟）
# ============================================================

# 在实际使用时，这里会调用Claude API
# 现在先用规则匹配做简单验证

def analyze_relationship_simple(market_a: Market, market_b: Market) -> Dict:
    """
    简单的规则匹配分析两个市场的逻辑关系
    后续会替换为LLM分析
    """
    q_a = market_a.question.lower()
    q_b = market_b.question.lower()
    
    # 检查是否是同一事件的不同结果（完备集）
    # 例如：多个候选人的胜率
    
    # 检查是否存在包含关系
    # 例如："Trump wins" vs "Republican wins"
    
    # 简单启发式规则
    result = {
        "relationship": "UNKNOWN",
        "confidence": 0.5,
        "reasoning": "需要LLM进一步分析",
        "constraint": None
    }
    
    # 检查关键词重叠
    keywords_a = set(q_a.split())
    keywords_b = set(q_b.split())
    overlap = keywords_a & keywords_b
    
    if len(overlap) > 3:
        result["relationship"] = "POSSIBLY_RELATED"
        result["confidence"] = 0.7
        result["reasoning"] = f"关键词重叠: {overlap}"
    
    return result


# ============================================================
# 第三部分：定价检验
# ============================================================

def check_exhaustive_set(markets: List[Market]) -> Optional[Dict]:
    """
    检查一组市场是否构成完备集，以及是否存在套利
    完备集：所有结果互斥且覆盖全部可能，总和应该=1
    """
    if len(markets) < 2:
        return None
    
    total_yes = sum(m.yes_price for m in markets)
    
    # 如果总和小于1，存在套利机会
    if total_yes < 0.98:  # 留2%的buffer给手续费
        profit = 1.0 - total_yes
        profit_pct = (profit / total_yes) * 100
        
        return {
            "type": "EXHAUSTIVE_SET_ARBITRAGE",
            "markets": [m.question for m in markets],
            "prices": [m.yes_price for m in markets],
            "total": total_yes,
            "profit": profit,
            "profit_pct": profit_pct,
            "action": "买入所有选项各一份"
        }
    
    return None


def check_implication_violation(market_a: Market, market_b: Market, 
                                 a_implies_b: bool = True) -> Optional[Dict]:
    """
    检查包含关系是否被违反
    如果 A → B（A发生则B必发生），那么 P(B) >= P(A)
    """
    if a_implies_b:
        # A → B，检查 P(B) >= P(A)
        if market_b.yes_price < market_a.yes_price - 0.02:  # 2%容差
            spread = market_a.yes_price - market_b.yes_price
            cost = market_b.yes_price + market_a.no_price
            profit = 1.0 - cost
            
            if profit > 0.02:  # 至少2%利润
                return {
                    "type": "IMPLICATION_VIOLATION",
                    "market_a": market_a.question,
                    "market_b": market_b.question,
                    "price_a": market_a.yes_price,
                    "price_b": market_b.yes_price,
                    "spread": spread,
                    "cost": cost,
                    "profit": profit,
                    "profit_pct": (profit / cost) * 100,
                    "action": f"买 '{market_b.question}' YES @ {market_b.yes_price:.3f}, 买 '{market_a.question}' NO @ {market_a.no_price:.3f}"
                }
    
    return None


# ============================================================
# 第四部分：主流程
# ============================================================

def run_phase0_verification():
    """Phase 0 验证流程"""
    print("=" * 60)
    print("Phase 0: Polymarket组合套利验证")
    print("=" * 60)
    
    # Step 1: 测试API连接
    print("\n[Step 1] 测试API连接...")
    markets = fetch_active_markets(limit=20)
    
    if not markets:
        print("❌ API连接失败，请检查网络")
        return False
    
    print(f"✅ 成功获取 {len(markets)} 个市场")
    print("\n热门市场示例:")
    for m in markets[:5]:
        print(f"  - {m.question[:60]}...")
        print(f"    YES: ${m.yes_price:.3f}, Volume: ${m.volume:,.0f}")
    
    # Step 2: 获取事件列表
    print("\n[Step 2] 获取事件列表...")
    events = fetch_events(limit=10)
    
    if not events:
        print("⚠️ 无法获取事件列表")
    else:
        print(f"✅ 成功获取 {len(events)} 个事件")
        print("\n热门事件:")
        for e in events[:5]:
            title = e.get('title', e.get('slug', 'Unknown'))
            print(f"  - {title}")
    
    # Step 3: 寻找同一事件下的多个市场（可能的完备集）
    print("\n[Step 3] 寻找可能的完备集...")
    
    # 按event_id分组
    event_groups = {}
    for m in markets:
        if m.event_id:
            if m.event_id not in event_groups:
                event_groups[m.event_id] = []
            event_groups[m.event_id].append(m)
    
    print(f"发现 {len(event_groups)} 个事件组")
    
    # 检查每个事件组是否存在完备集套利
    opportunities = []
    for event_id, group in event_groups.items():
        if len(group) >= 2:
            opp = check_exhaustive_set(group)
            if opp:
                opportunities.append(opp)
    
    # Step 4: 报告发现
    print("\n[Step 4] 套利机会扫描结果")
    print("-" * 40)
    
    if opportunities:
        print(f"🎯 发现 {len(opportunities)} 个潜在完备集套利机会:\n")
        for i, opp in enumerate(opportunities, 1):
            print(f"机会 #{i}")
            print(f"  类型: {opp['type']}")
            print(f"  市场数: {len(opp['markets'])}")
            print(f"  总价: ${opp['total']:.4f}")
            print(f"  潜在利润: ${opp['profit']:.4f} ({opp['profit_pct']:.2f}%)")
            print(f"  操作: {opp['action']}")
            print()
    else:
        print("暂未发现明显的完备集套利机会")
        print("这很正常——机会不是时时都有")
    
    # Step 5: 输出原始数据供进一步分析
    print("\n[Step 5] 输出数据供进一步分析...")
    
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "markets_count": len(markets),
        "events_count": len(events),
        "event_groups": {k: [m.question for m in v] for k, v in event_groups.items()},
        "opportunities": opportunities,
        "raw_markets": [
            {
                "id": m.id,
                "question": m.question,
                "yes_price": m.yes_price,
                "volume": m.volume,
                "event_id": m.event_id
            }
            for m in markets
        ]
    }
    
    with open("phase0_output.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print("✅ 数据已保存到 phase0_output.json")
    
    print("\n" + "=" * 60)
    print("Phase 0 验证完成！")
    print("=" * 60)
    print("\n下一步：")
    print("1. 查看 phase0_output.json 中的市场数据")
    print("2. 手动挑选几对相关市场")
    print("3. 用LLM分析它们的逻辑关系")
    
    return True


if __name__ == "__main__":
    run_phase0_verification()
