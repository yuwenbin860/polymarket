#!/usr/bin/env python3
"""
Bitcoin January 3 合成套利验证脚本
===================================

验证用户发现的套利案例：
- Event 1: "Bitcoin Up or Down on January 3?" (threshold $90k)
- Event 2: "Bitcoin price on January 3?" (price ranges)
- Event 3: "Bitcoin above ___ on January 3?" (thresholds)

理论：Event 1 DOWN = Sum(所有 < $90k 区间的 YES)
"""

import requests
import json
import re
import os
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple

# ============================================================
# 数据结构
# ============================================================

@dataclass
class BitcoinMarket:
    """Bitcoin市场数据"""
    market_id: str
    question: str
    yes_price: float
    no_price: float
    volume: float
    liquidity: float
    event_id: str
    event_title: str
    market_type: str  # 'up_down', 'price_range', 'above_threshold', 'other'
    threshold: Optional[float] = None  # 单一阈值
    range_low: Optional[float] = None  # 区间下限
    range_high: Optional[float] = None  # 区间上限
    outcome: Optional[str] = None  # 'UP', 'DOWN', 'YES' 等

# ============================================================
# API客户端
# ============================================================

class PolymarketClient:
    """Polymarket API客户端"""

    def __init__(self):
        self.base_url = "https://gamma-api.polymarket.com"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BitcoinArbVerify/1.0"
        })

    def get_markets(self, limit: int = 500) -> List[Dict]:
        """获取市场列表"""
        url = f"{self.base_url}/markets"
        params = {
            "limit": limit,
            "active": "true",
            "closed": "false",
            "order": "volume",
            "ascending": "false"
        }

        response = self.session.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_events(self, limit: int = 200) -> List[Dict]:
        """获取事件列表"""
        url = f"{self.base_url}/events"
        params = {
            "limit": limit,
            "active": "true",
            "closed": "false"
        }

        response = self.session.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def search_markets(self, keyword: str) -> List[Dict]:
        """搜索市场（通过本地过滤）"""
        markets = self.get_markets(limit=500)
        keyword_lower = keyword.lower()
        return [m for m in markets if keyword_lower in m.get('question', '').lower()]

# ============================================================
# 数值提取器
# ============================================================

class ValueExtractor:
    """从市场问题中提取数值"""

    @staticmethod
    def extract_price(text: str) -> Optional[float]:
        """提取价格数值，支持多种格式"""
        # 格式: $90,000 / $90000 / 90000 / $90k / 90k
        patterns = [
            r'\$?([\d,]+(?:\.\d+)?)\s*k',  # 90k, $90k
            r'\$?([\d,]+(?:\.\d+)?)',       # 90000, $90,000
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '')
                value = float(value_str)
                # 如果匹配到k后缀，乘以1000
                if 'k' in text[match.start():match.end()].lower():
                    value *= 1000
                # 如果值太小，可能是k格式
                if value < 1000:
                    value *= 1000
                return value
        return None

    @staticmethod
    def extract_range(text: str) -> Tuple[Optional[float], Optional[float]]:
        """提取价格区间"""
        # 格式: $78,000 - $80,000 / $78k-$80k / 78000-80000
        patterns = [
            r'\$?([\d,]+(?:\.\d+)?)\s*k?\s*[-–to]+\s*\$?([\d,]+(?:\.\d+)?)\s*k?',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                low_str = match.group(1).replace(',', '')
                high_str = match.group(2).replace(',', '')
                low = float(low_str)
                high = float(high_str)

                # 处理k后缀
                full_match = text[match.start():match.end()].lower()
                if 'k' in full_match:
                    if low < 1000:
                        low *= 1000
                    if high < 1000:
                        high *= 1000
                elif low < 1000 and high < 1000:
                    low *= 1000
                    high *= 1000

                return (low, high)
        return (None, None)

    @staticmethod
    def extract_threshold_from_updown(text: str) -> Optional[float]:
        """从Up/Down市场提取阈值"""
        # "price to beat" 或 "threshold" 后的数值
        patterns = [
            r'price\s+to\s+beat[:\s]*\$?([\d,]+(?:\.\d+)?)',
            r'threshold[:\s]*\$?([\d,]+(?:\.\d+)?)',
            r'above\s+\$?([\d,]+(?:\.\d+)?)',
            r'below\s+\$?([\d,]+(?:\.\d+)?)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '')
                return float(value_str)

        # 尝试通用提取
        return ValueExtractor.extract_price(text)

# ============================================================
# 市场分类器
# ============================================================

class MarketClassifier:
    """分类Bitcoin市场类型"""

    @staticmethod
    def classify(question: str, description: str = "") -> str:
        """判断市场类型"""
        q_lower = question.lower()
        d_lower = description.lower()
        combined = q_lower + " " + d_lower

        # Up/Down 市场
        if 'up or down' in combined or 'up/down' in combined:
            return 'up_down'

        # Above 阈值市场
        if 'above' in combined and ('?' in question or 'will' in combined):
            return 'above_threshold'

        # Below 阈值市场
        if 'below' in combined and ('?' in question or 'will' in combined):
            return 'below_threshold'

        # 价格区间市场 (包含 - 或 to)
        if re.search(r'\d+\s*[-–to]+\s*\d+', combined):
            return 'price_range'

        # 其他
        return 'other'

    @staticmethod
    def parse_market(raw: Dict) -> BitcoinMarket:
        """解析原始API数据为结构化对象"""
        question = raw.get('question', '')
        description = raw.get('description', '')
        market_type = MarketClassifier.classify(question, description)

        # 提取数值
        extractor = ValueExtractor()
        threshold = None
        range_low = None
        range_high = None

        if market_type == 'up_down':
            threshold = extractor.extract_threshold_from_updown(question + " " + description)
        elif market_type == 'above_threshold':
            threshold = extractor.extract_price(question)
        elif market_type == 'below_threshold':
            threshold = extractor.extract_price(question)
        elif market_type == 'price_range':
            range_low, range_high = extractor.extract_range(question)

        # 提取outcome
        outcome = None
        outcomes = raw.get('outcomes', [])
        if outcomes:
            outcome = outcomes[0] if isinstance(outcomes[0], str) else None

        # 解析价格 - 处理多种格式
        yes_price = 0.5
        try:
            outcome_prices = raw.get('outcomePrices', '')
            if outcome_prices:
                # 格式可能是: '["0.5","0.5"]' 或 '[0.5,0.5]' 或 JSON
                if isinstance(outcome_prices, str):
                    # 去除外层引号和括号
                    prices_str = outcome_prices.strip('[]')
                    # 分割并清理
                    parts = prices_str.split(',')
                    if parts:
                        price_str = parts[0].strip().strip('"\'')
                        yes_price = float(price_str)
                elif isinstance(outcome_prices, list):
                    yes_price = float(outcome_prices[0])
        except (ValueError, IndexError) as e:
            yes_price = 0.5

        return BitcoinMarket(
            market_id=raw.get('id', ''),
            question=question,
            yes_price=yes_price,
            no_price=1 - yes_price,
            volume=float(raw.get('volume', 0) or 0),
            liquidity=float(raw.get('liquidity', 0) or 0),
            event_id=raw.get('groupItemTitle', '') or raw.get('slug', ''),
            event_title=raw.get('groupItemTitle', '') or question[:50],
            market_type=market_type,
            threshold=threshold,
            range_low=range_low,
            range_high=range_high,
            outcome=outcome
        )

# ============================================================
# 套利验证器
# ============================================================

class CompositeArbitrageVerifier:
    """合成套利验证器"""

    def __init__(self, markets: List[BitcoinMarket]):
        self.markets = markets
        self.up_down_markets = [m for m in markets if m.market_type == 'up_down']
        self.range_markets = [m for m in markets if m.market_type == 'price_range']
        self.above_markets = [m for m in markets if m.market_type == 'above_threshold']
        self.below_markets = [m for m in markets if m.market_type == 'below_threshold']

    def verify_down_vs_ranges(self, threshold: float) -> Dict:
        """
        验证：UP/DOWN市场的DOWN价格 vs 区间市场<阈值的YES之和

        理论：如果 BTC < $90k，则 DOWN=YES
        等价于：所有价格区间 < $90k 的 YES 之和
        """
        result = {
            'threshold': threshold,
            'down_price': None,
            'sum_below_threshold': 0.0,
            'ranges_below': [],
            'gap': None,
            'has_arbitrage': False
        }

        # 找到对应的 UP/DOWN 市场
        for m in self.up_down_markets:
            if m.threshold and abs(m.threshold - threshold) < 1000:
                # DOWN价格 = NO价格（假设UP是YES）
                result['down_price'] = m.no_price
                break

        # 计算所有 < 阈值的区间YES价格之和
        for m in self.range_markets:
            if m.range_high and m.range_high <= threshold:
                result['sum_below_threshold'] += m.yes_price
                result['ranges_below'].append({
                    'range': f"${m.range_low:,.0f} - ${m.range_high:,.0f}",
                    'yes_price': m.yes_price,
                    'question': m.question[:60]
                })

        # 计算差距
        if result['down_price'] is not None and result['sum_below_threshold'] > 0:
            result['gap'] = abs(result['down_price'] - result['sum_below_threshold'])
            result['has_arbitrage'] = result['gap'] > 0.02  # 2%阈值

        return result

    def find_all_arbitrage(self) -> List[Dict]:
        """查找所有可能的合成套利机会"""
        opportunities = []

        # 收集所有阈值
        thresholds = set()
        for m in self.up_down_markets:
            if m.threshold:
                thresholds.add(m.threshold)
        for m in self.above_markets:
            if m.threshold:
                thresholds.add(m.threshold)

        # 验证每个阈值
        for threshold in thresholds:
            result = self.verify_down_vs_ranges(threshold)
            if result['down_price'] is not None or result['sum_below_threshold'] > 0:
                opportunities.append(result)

        return opportunities

    def generate_report(self) -> Dict:
        """生成验证报告"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_markets': len(self.markets),
                'up_down_markets': len(self.up_down_markets),
                'range_markets': len(self.range_markets),
                'above_markets': len(self.above_markets),
                'below_markets': len(self.below_markets)
            },
            'markets_detail': {
                'up_down': [asdict(m) for m in self.up_down_markets],
                'ranges': [asdict(m) for m in self.range_markets],
                'above': [asdict(m) for m in self.above_markets]
            },
            'arbitrage_analysis': self.find_all_arbitrage()
        }
        return report

# ============================================================
# 主程序
# ============================================================

def main():
    print("=" * 60)
    print("Bitcoin January 3 合成套利验证")
    print("=" * 60)

    # 1. 获取市场数据
    print("\n[1/4] 获取市场数据...")
    client = PolymarketClient()

    try:
        all_markets = client.get_markets(limit=500)
        print(f"    获取到 {len(all_markets)} 个市场")
    except Exception as e:
        print(f"    错误: {e}")
        return

    # 2. 过滤Bitcoin相关市场
    print("\n[2/4] 过滤Bitcoin + January相关市场...")
    bitcoin_jan_markets = []

    keywords = ['bitcoin', 'btc']
    date_keywords = ['january', 'jan 3', 'jan3', 'january 3']

    for m in all_markets:
        question = m.get('question', '').lower()
        # Bitcoin相关
        if any(kw in question for kw in keywords):
            # January相关
            if any(dk in question for dk in date_keywords):
                bitcoin_jan_markets.append(m)

    print(f"    找到 {len(bitcoin_jan_markets)} 个Bitcoin+January市场")

    # 如果没找到，尝试更宽松的搜索
    if len(bitcoin_jan_markets) < 5:
        print("    尝试更宽松的搜索...")
        for m in all_markets:
            question = m.get('question', '').lower()
            if any(kw in question for kw in keywords) and 'january' in question:
                if m not in bitcoin_jan_markets:
                    bitcoin_jan_markets.append(m)
        print(f"    扩展后找到 {len(bitcoin_jan_markets)} 个市场")

    # 3. 分类和解析市场
    print("\n[3/4] 分类市场类型...")
    parsed_markets = []

    for raw in bitcoin_jan_markets:
        try:
            market = MarketClassifier.parse_market(raw)
            parsed_markets.append(market)

            # 打印详情
            type_icon = {
                'up_down': '[UP/DOWN]',
                'price_range': '[RANGE]',
                'above_threshold': '[ABOVE]',
                'below_threshold': '[BELOW]',
                'other': '[OTHER]'
            }.get(market.market_type, '[?]')

            price_info = ""
            if market.threshold:
                price_info = f"threshold=${market.threshold:,.0f}"
            elif market.range_low and market.range_high:
                price_info = f"range=${market.range_low:,.0f}-${market.range_high:,.0f}"

            print(f"    {type_icon} YES={market.yes_price:.2%} | {price_info}")
            print(f"        Q: {market.question[:70]}...")

        except Exception as e:
            print(f"    解析失败: {e}")

    # 4. 套利验证
    print("\n[4/4] 验证套利机会...")
    verifier = CompositeArbitrageVerifier(parsed_markets)
    report = verifier.generate_report()

    # 打印摘要
    print("\n" + "=" * 60)
    print("验证报告摘要")
    print("=" * 60)
    print(f"总市场数: {report['summary']['total_markets']}")
    print(f"  - Up/Down市场: {report['summary']['up_down_markets']}")
    print(f"  - 区间市场: {report['summary']['range_markets']}")
    print(f"  - Above阈值市场: {report['summary']['above_markets']}")

    # 打印套利分析
    print("\n套利分析:")
    for i, arb in enumerate(report['arbitrage_analysis'], 1):
        print(f"\n  [{i}] 阈值: ${arb['threshold']:,.0f}")
        print(f"      DOWN价格: {arb['down_price']:.2%}" if arb['down_price'] else "      DOWN价格: N/A")
        print(f"      区间<阈值的YES之和: {arb['sum_below_threshold']:.2%}")
        if arb['gap']:
            print(f"      价差: {arb['gap']:.2%}")
            print(f"      套利机会: {'YES!' if arb['has_arbitrage'] else 'No'}")

        if arb['ranges_below']:
            print(f"      包含区间:")
            for r in arb['ranges_below'][:5]:  # 最多显示5个
                print(f"        - {r['range']}: YES={r['yes_price']:.2%}")

    # 5. 保存报告
    os.makedirs('output', exist_ok=True)
    output_file = f"output/bitcoin_jan3_verify_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n报告已保存到: {output_file}")

    return report

if __name__ == "__main__":
    main()
