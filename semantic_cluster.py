#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语义聚类模块
============

使用向量化嵌入对市场进行语义聚类，替代关键词匹配。

核心功能：
1. 获取市场问题的向量嵌入
2. 计算语义相似度
3. 聚类相关市场
4. 发现可能存在套利关系的市场组

使用方法：
    from semantic_cluster import SemanticClusterer

    clusterer = SemanticClusterer()
    clusters = clusterer.cluster_markets(markets, query="Bitcoin January")
"""

import sys
import json
import numpy as np
import requests
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

# UTF-8编码说明：所有输出使用ASCII字符，无需特殊编码处理


@dataclass
class MarketInfo:
    """市场信息"""
    id: str
    question: str
    yes_price: float
    no_price: float
    volume: float
    liquidity: float
    slug: str
    closed: bool = False
    embedding: Optional[np.ndarray] = None


class SemanticClusterer:
    """语义聚类器 - 用向量相似度发现相关市场"""

    def __init__(self, config_path: str = "config.json"):
        """初始化聚类器"""
        from config import Config

        config = Config.load(config_path)

        # 从 active_profile 获取 API 配置
        if config.active_profile and config.active_profile in config.llm_profiles:
            profile = config.llm_profiles[config.active_profile]
            # 过滤掉注释字段
            profile = {k: v for k, v in profile.items() if not k.startswith('_')}
            self.api_base = profile.get('api_base', 'https://api.siliconflow.cn/v1')
            self.api_key = profile.get('api_key', '')
            # 从 profile 读取 embedding_model，如果没有则使用默认值
            self.embed_model = profile.get('embedding_model', 'BAAI/bge-large-zh-v1.5')
        else:
            # 回退到 llm 字段（向后兼容）
            self.api_base = config.llm.api_base or 'https://api.siliconflow.cn/v1'
            self.api_key = config.llm.api_key
            self.embed_model = config.scan.embedding_model  # 从 scan 配置读取

        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            })

    def get_embedding(self, text: str) -> np.ndarray:
        """获取单个文本的向量嵌入"""
        return self.get_embeddings([text])[0]

    def get_embeddings(self, texts: List[str]) -> np.ndarray:
        """批量获取文本向量嵌入"""
        url = f"{self.api_base}/embeddings"

        # 分批处理，避免请求过大 (SiliconFlow限制较小)
        batch_size = 10
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            payload = {
                "model": self.embed_model,
                "input": batch,
                "encoding_format": "float"
            }

            try:
                response = self.session.post(url, json=payload, timeout=60)
                response.raise_for_status()
                result = response.json()

                # 提取embeddings
                for item in result.get('data', []):
                    all_embeddings.append(item['embedding'])

            except Exception as e:
                print(f"Embedding API error: {e}")
                # 返回零向量作为fallback
                for _ in batch:
                    all_embeddings.append([0.0] * 1024)  # BGE-large维度

        return np.array(all_embeddings)

    def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """计算余弦相似度"""
        if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
            return 0.0
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

    def find_similar_markets(self, query: str, markets: List[Dict],
                            top_k: int = 20, threshold: float = 0.5) -> List[Dict]:
        """找到与query语义最相似的市场

        Args:
            query: 搜索查询 (如 "Bitcoin price January 4")
            markets: 市场列表 (原始API数据)
            top_k: 返回最相似的前k个
            threshold: 相似度阈值

        Returns:
            相似市场列表，按相似度排序
        """
        if not markets:
            return []

        # 提取问题文本
        questions = [m.get('question', '') for m in markets]

        # 获取所有embeddings (包括query)
        all_texts = [query] + questions
        print(f"Getting embeddings for {len(all_texts)} texts...")
        embeddings = self.get_embeddings(all_texts)

        query_embedding = embeddings[0]
        market_embeddings = embeddings[1:]

        # 计算相似度
        similarities = []
        for i, (market, emb) in enumerate(zip(markets, market_embeddings)):
            sim = self.cosine_similarity(query_embedding, emb)
            if sim >= threshold:
                similarities.append({
                    'market': market,
                    'similarity': sim,
                    'question': market.get('question', '')
                })

        # 排序
        similarities.sort(key=lambda x: x['similarity'], reverse=True)

        return similarities[:top_k]

    def cluster_markets(self, markets: List[Dict],
                       similarity_threshold: float = 0.75) -> List[List[Dict]]:
        """将市场按语义相似度聚类

        ✅ Rules分析优先：
        - 向量化时结合question + event_description
        - 这样可以根据resolution rules进行更准确的聚类

        使用简单的层次聚类：
        1. 计算所有市场的pairwise相似度
        2. 将相似度 > threshold 的市场归入同一类

        Args:
            markets: 市场列表
            similarity_threshold: 相似度阈值

        Returns:
            聚类结果，每个cluster是一个市场列表
        """
        if not markets:
            return []

        n = len(markets)
        if n > 500:
            print(f"Warning: {n} markets is large, sampling to 500")
            markets = markets[:500]
            n = 500

        # ✅ 新增: 获取embeddings时包含description信息
        # 支持Market对象和字典两种类型
        texts = []
        for m in markets:
            if hasattr(m, 'question'):  # Market对象
                # 优先使用event_description（包含rules）
                desc = getattr(m, 'full_description', None)
                if desc is None:
                    desc = getattr(m, 'event_description', '') or getattr(m, 'market_description', '') or getattr(m, 'description', '')
                # 结合question和description进行向量化
                question = m.question
                texts.append(f"{question}\n\nRules: {desc[:500]}")  # 限制description长度
            else:  # 字典
                desc = (m.get('event_description', '') or
                       m.get('market_description', '') or
                       m.get('description', ''))
                question = m.get('question', '')
                texts.append(f"{question}\n\nRules: {desc[:500]}")

        print(f"Getting embeddings for {n} markets (with rules info)...")
        embeddings = self.get_embeddings(texts)

        # 计算相似度矩阵
        print("Computing similarity matrix...")
        sim_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                sim = self.cosine_similarity(embeddings[i], embeddings[j])
                sim_matrix[i, j] = sim
                sim_matrix[j, i] = sim

        # 简单聚类：Union-Find
        parent = list(range(n))

        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # 合并相似的市场
        for i in range(n):
            for j in range(i + 1, n):
                if sim_matrix[i, j] >= similarity_threshold:
                    union(i, j)

        # 收集聚类
        clusters_dict = defaultdict(list)
        for i in range(n):
            root = find(i)
            clusters_dict[root].append(markets[i])

        # 转换为列表，按大小排序
        clusters = list(clusters_dict.values())
        clusters.sort(key=len, reverse=True)

        return clusters

    def analyze_cluster_for_arbitrage(self, cluster: List[Dict]) -> Dict:
        """分析聚类内的市场是否存在套利关系

        Returns:
            分析结果，包含可能的套利机会
        """
        result = {
            'cluster_size': len(cluster),
            'markets': [],
            'potential_arbitrage': [],
            'analysis': ''
        }

        # 分类市场
        above_markets = []
        below_markets = []
        range_markets = []
        updown_markets = []

        for m in cluster:
            q = m.get('question', '').lower()

            # 解析价格
            prices_str = m.get('outcomePrices', '')
            yes_price = 0.5
            if prices_str:
                try:
                    parts = prices_str.strip('[]').split(',')
                    yes_price = float(parts[0].strip().strip('"\''))
                except:
                    pass

            market_info = {
                'question': m.get('question', ''),
                'yes_price': yes_price,
                'no_price': 1 - yes_price,
                'slug': m.get('slug', '')
            }

            if 'above' in q:
                above_markets.append(market_info)
            elif 'below' in q or 'less than' in q:
                below_markets.append(market_info)
            elif 'between' in q:
                range_markets.append(market_info)
            elif 'up or down' in q:
                updown_markets.append(market_info)

            result['markets'].append(market_info)

        # 检查套利关系
        if above_markets and range_markets:
            result['analysis'] += "Found Above + Range markets - checking equivalence\n"
            # 这里可以添加更详细的套利检查逻辑

        if len(cluster) > 1:
            result['analysis'] += f"Cluster has {len(cluster)} related markets\n"

        return result


