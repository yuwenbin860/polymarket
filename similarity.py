"""
similarity.py - 语义相似度计算模块

使用 sentence-transformers 进行向量相似度计算，
作为 Jaccard 关键词相似度的补充层，用于发现语义相似但用词不同的市场对。

架构：
1. Jaccard 关键词相似度 (快速初筛)
2. 向量相似度 (语义发现) ← 本模块
3. LLM 精确分析 (最终判断)

使用模型: all-MiniLM-L6-v2 (本地运行，无API成本)
"""

import logging
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)

# 尝试导入 sentence-transformers
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence-transformers 未安装，向量相似度功能不可用")
    logger.warning("安装命令: pip install sentence-transformers")


@dataclass
class SimilarityResult:
    """相似度计算结果"""
    jaccard_score: float
    embedding_score: Optional[float]
    combined_score: float
    discovery_type: str  # "keyword" | "semantic" | "both"


class EmbeddingSimilarityFilter:
    """
    基于向量嵌入的语义相似度筛选器

    使用 sentence-transformers 的轻量模型进行语义相似度计算。
    与 Jaccard 关键词相似度配合使用，形成多层筛选架构。

    优势：
    - 能识别同义词和语义相似的表述
    - "Biden drops out" vs "Biden withdraws from race" 这类语义相同但用词不同的市场
    - "Trump victory" vs "Republican wins presidency" 这类隐含关系

    使用示例:
        filter = EmbeddingSimilarityFilter()
        pairs = filter.find_semantic_pairs(markets, threshold=0.7)
    """

    DEFAULT_MODEL = "all-MiniLM-L6-v2"  # 轻量级，~80MB，效果好

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        jaccard_threshold: float = 0.2,
        embedding_threshold: float = 0.7,
        combined_threshold: float = 0.5,
        cache_embeddings: bool = True
    ):
        """
        初始化语义相似度筛选器

        Args:
            model_name: sentence-transformers 模型名称
            jaccard_threshold: Jaccard 相似度阈值 (用于快速初筛)
            embedding_threshold: 向量相似度阈值 (用于语义发现)
            combined_threshold: 综合相似度阈值 (用于最终筛选)
            cache_embeddings: 是否缓存向量嵌入
        """
        self.model_name = model_name
        self.jaccard_threshold = jaccard_threshold
        self.embedding_threshold = embedding_threshold
        self.combined_threshold = combined_threshold
        self.cache_embeddings = cache_embeddings

        self._model: Optional[SentenceTransformer] = None
        self._embedding_cache: Dict[str, np.ndarray] = {}
        self._initialized = False

    def _initialize_model(self) -> bool:
        """延迟加载模型"""
        if self._initialized:
            return self._model is not None

        self._initialized = True

        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            logger.warning("sentence-transformers 不可用，将仅使用 Jaccard 相似度")
            return False

        try:
            logger.info(f"正在加载 sentence-transformers 模型: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
            logger.info(f"模型加载成功: {self.model_name}")
            return True
        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            return False

    def _get_embedding(self, text: str) -> Optional[np.ndarray]:
        """获取文本的向量嵌入（带缓存）"""
        if self._model is None:
            return None

        if self.cache_embeddings and text in self._embedding_cache:
            return self._embedding_cache[text]

        try:
            embedding = self._model.encode(text, convert_to_numpy=True)
            if self.cache_embeddings:
                self._embedding_cache[text] = embedding
            return embedding
        except Exception as e:
            logger.error(f"向量编码失败: {e}")
            return None

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """计算余弦相似度"""
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(vec1, vec2) / (norm1 * norm2))

    def _calculate_jaccard(self, text1: str, text2: str) -> float:
        """计算 Jaccard 关键词相似度"""
        stop_words = {
            'will', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of',
            'by', 'be', 'is', 'are', 'was', 'were', 'been', 'being', 'have',
            'has', 'had', 'do', 'does', 'did', 'and', 'or', 'but', 'if', 'then',
            'than', 'that', 'this', 'these', 'those', 'what', 'which', 'who'
        }

        words1 = set(text1.lower().split()) - stop_words
        words2 = set(text2.lower().split()) - stop_words

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def calculate_similarity(
        self,
        text1: str,
        text2: str,
        event_id1: Optional[str] = None,
        event_id2: Optional[str] = None,
        end_date1: Optional[str] = None,
        end_date2: Optional[str] = None
    ) -> SimilarityResult:
        """
        计算两段文本的综合相似度

        Args:
            text1, text2: 要比较的两段文本（通常是市场问题）
            event_id1, event_id2: 市场的事件ID（可选，用于加分）
            end_date1, end_date2: 市场的结算日期（可选，用于加分）

        Returns:
            SimilarityResult 包含各层相似度分数
        """
        # 1. Jaccard 关键词相似度
        jaccard = self._calculate_jaccard(text1, text2)

        # 同事件加分
        if event_id1 and event_id1 == event_id2:
            jaccard = min(1.0, jaccard + 0.4)

        # 同结算日加分
        if end_date1 and end_date1 == end_date2:
            jaccard = min(1.0, jaccard + 0.1)

        # 2. 向量相似度
        embedding_score = None
        self._initialize_model()

        if self._model is not None:
            emb1 = self._get_embedding(text1)
            emb2 = self._get_embedding(text2)

            if emb1 is not None and emb2 is not None:
                embedding_score = self._cosine_similarity(emb1, emb2)

        # 3. 综合相似度
        if embedding_score is not None:
            # 加权平均：关键词 30%，向量 70%
            combined = 0.3 * jaccard + 0.7 * embedding_score

            # 确定发现类型
            if jaccard >= self.jaccard_threshold and embedding_score >= self.embedding_threshold:
                discovery_type = "both"
            elif embedding_score >= self.embedding_threshold:
                discovery_type = "semantic"  # 关键发现！用词不同但语义相似
            else:
                discovery_type = "keyword"
        else:
            combined = jaccard
            discovery_type = "keyword"

        return SimilarityResult(
            jaccard_score=jaccard,
            embedding_score=embedding_score,
            combined_score=combined,
            discovery_type=discovery_type
        )

    def find_similar_pairs(
        self,
        markets: List[Any],
        question_attr: str = "question",
        event_id_attr: str = "event_id",
        end_date_attr: str = "end_date"
    ) -> List[Tuple[Any, Any, SimilarityResult]]:
        """
        在市场列表中找出相似的市场对

        Args:
            markets: 市场列表
            question_attr: 市场问题属性名
            event_id_attr: 事件ID属性名
            end_date_attr: 结算日期属性名

        Returns:
            List of (market1, market2, SimilarityResult) 按综合相似度降序排列
        """
        pairs = []

        for i, m1 in enumerate(markets):
            for m2 in markets[i+1:]:
                # 获取属性值
                q1 = getattr(m1, question_attr, str(m1))
                q2 = getattr(m2, question_attr, str(m2))
                eid1 = getattr(m1, event_id_attr, None)
                eid2 = getattr(m2, event_id_attr, None)
                ed1 = getattr(m1, end_date_attr, None)
                ed2 = getattr(m2, end_date_attr, None)

                result = self.calculate_similarity(
                    q1, q2,
                    event_id1=eid1, event_id2=eid2,
                    end_date1=ed1, end_date2=ed2
                )

                if result.combined_score >= self.combined_threshold:
                    pairs.append((m1, m2, result))

        # 按综合相似度降序排列
        pairs.sort(key=lambda x: x[2].combined_score, reverse=True)

        return pairs

    def find_semantic_discoveries(
        self,
        markets: List[Any],
        question_attr: str = "question"
    ) -> List[Tuple[Any, Any, SimilarityResult]]:
        """
        专门查找语义发现的市场对（用词不同但语义相似）

        这是最有价值的发现，因为这些机会不容易被简单的关键词匹配发现。

        Args:
            markets: 市场列表
            question_attr: 市场问题属性名

        Returns:
            仅返回 discovery_type == "semantic" 的市场对
        """
        all_pairs = self.find_similar_pairs(markets, question_attr)

        # 只返回语义发现（关键词不匹配但向量相似的）
        semantic_pairs = [
            p for p in all_pairs
            if p[2].discovery_type == "semantic"
        ]

        if semantic_pairs:
            logger.info(f"发现 {len(semantic_pairs)} 对语义相似但用词不同的市场（关键发现！）")

        return semantic_pairs

    def clear_cache(self):
        """清空向量缓存"""
        self._embedding_cache.clear()
        logger.info("向量缓存已清空")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "model": self.model_name,
            "model_loaded": self._model is not None,
            "cache_size": len(self._embedding_cache),
            "jaccard_threshold": self.jaccard_threshold,
            "embedding_threshold": self.embedding_threshold,
            "combined_threshold": self.combined_threshold
        }


class HybridSimilarityFilter:
    """
    混合相似度筛选器

    结合 Jaccard 和向量相似度，提供多层筛选架构。
    如果 sentence-transformers 不可用，自动降级为纯 Jaccard 模式。

    使用示例:
        filter = HybridSimilarityFilter()
        pairs = filter.find_similar_pairs(markets)

        # 获取纯语义发现（最有价值）
        semantic_pairs = filter.find_semantic_discoveries(markets)
    """

    def __init__(
        self,
        jaccard_threshold: float = 0.2,
        embedding_threshold: float = 0.7,
        combined_threshold: float = 0.4,
        enable_embedding: bool = True
    ):
        """
        初始化混合筛选器

        Args:
            jaccard_threshold: Jaccard 相似度阈值
            embedding_threshold: 向量相似度阈值
            combined_threshold: 综合相似度阈值
            enable_embedding: 是否启用向量相似度
        """
        self.jaccard_threshold = jaccard_threshold
        self.embedding_threshold = embedding_threshold
        self.combined_threshold = combined_threshold

        self._embedding_filter: Optional[EmbeddingSimilarityFilter] = None

        if enable_embedding and SENTENCE_TRANSFORMERS_AVAILABLE:
            self._embedding_filter = EmbeddingSimilarityFilter(
                jaccard_threshold=jaccard_threshold,
                embedding_threshold=embedding_threshold,
                combined_threshold=combined_threshold
            )
        elif enable_embedding:
            logger.warning("向量相似度已禁用：sentence-transformers 未安装")

    @property
    def embedding_enabled(self) -> bool:
        """向量相似度是否可用"""
        return self._embedding_filter is not None

    def find_similar_pairs(
        self,
        markets: List[Any],
        question_attr: str = "question"
    ) -> List[Tuple[Any, Any, float, Optional[str]]]:
        """
        查找相似市场对

        Returns:
            List of (market1, market2, score, discovery_type)
            - score: 综合相似度分数
            - discovery_type: "keyword" | "semantic" | "both" | None
        """
        if self._embedding_filter:
            pairs = self._embedding_filter.find_similar_pairs(markets, question_attr)
            return [
                (m1, m2, result.combined_score, result.discovery_type)
                for m1, m2, result in pairs
            ]
        else:
            # 降级模式：纯 Jaccard
            return self._find_pairs_jaccard_only(markets, question_attr)

    def _find_pairs_jaccard_only(
        self,
        markets: List[Any],
        question_attr: str
    ) -> List[Tuple[Any, Any, float, None]]:
        """纯 Jaccard 模式"""
        stop_words = {
            'will', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of',
            'by', 'be', 'is', 'are'
        }

        pairs = []
        for i, m1 in enumerate(markets):
            for m2 in markets[i+1:]:
                q1 = getattr(m1, question_attr, str(m1))
                q2 = getattr(m2, question_attr, str(m2))

                words1 = set(q1.lower().split()) - stop_words
                words2 = set(q2.lower().split()) - stop_words

                if not words1 or not words2:
                    continue

                intersection = len(words1 & words2)
                union = len(words1 | words2)
                score = intersection / union if union > 0 else 0

                # 同事件加分
                eid1 = getattr(m1, 'event_id', None)
                eid2 = getattr(m2, 'event_id', None)
                if eid1 and eid1 == eid2:
                    score = min(1.0, score + 0.4)

                if score >= self.jaccard_threshold:
                    pairs.append((m1, m2, score, None))

        pairs.sort(key=lambda x: x[2], reverse=True)
        return pairs

    def find_semantic_discoveries(
        self,
        markets: List[Any],
        question_attr: str = "question"
    ) -> List[Tuple[Any, Any, float]]:
        """
        查找语义发现（用词不同但语义相似）

        Returns:
            List of (market1, market2, embedding_score) - 仅语义发现
        """
        if not self._embedding_filter:
            logger.warning("向量相似度不可用，无法进行语义发现")
            return []

        pairs = self._embedding_filter.find_semantic_discoveries(markets, question_attr)
        return [
            (m1, m2, result.embedding_score)
            for m1, m2, result in pairs
        ]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        base_stats = {
            "embedding_enabled": self.embedding_enabled,
            "jaccard_threshold": self.jaccard_threshold,
            "embedding_threshold": self.embedding_threshold,
            "combined_threshold": self.combined_threshold
        }

        if self._embedding_filter:
            base_stats.update(self._embedding_filter.get_stats())

        return base_stats


# ============================================================
# 便捷函数
# ============================================================

def create_similarity_filter(
    enable_embedding: bool = True,
    jaccard_threshold: float = 0.2,
    embedding_threshold: float = 0.7
) -> HybridSimilarityFilter:
    """
    创建相似度筛选器的便捷函数

    Args:
        enable_embedding: 是否启用向量相似度
        jaccard_threshold: Jaccard 相似度阈值
        embedding_threshold: 向量相似度阈值

    Returns:
        HybridSimilarityFilter 实例
    """
    return HybridSimilarityFilter(
        enable_embedding=enable_embedding,
        jaccard_threshold=jaccard_threshold,
        embedding_threshold=embedding_threshold
    )


def check_embedding_available() -> bool:
    """检查向量相似度功能是否可用"""
    return SENTENCE_TRANSFORMERS_AVAILABLE


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("语义相似度模块测试")
    print("=" * 60)

    # 检查 sentence-transformers 是否可用
    if not check_embedding_available():
        print("\n[!] sentence-transformers 未安装")
        print("安装命令: pip install sentence-transformers")
        print("\n将使用纯 Jaccard 模式进行测试...")

    # 测试数据：模拟市场
    class MockMarket:
        def __init__(self, question, event_id=None):
            self.question = question
            self.event_id = event_id
            self.end_date = None

    test_markets = [
        MockMarket("Will Trump win the 2024 election?", "election2024"),
        MockMarket("Will Donald Trump become president?", "election2024"),
        MockMarket("Will Biden drop out of the race?", "biden"),
        MockMarket("Will Biden withdraw from the presidential race?", "biden"),
        MockMarket("Will the Fed cut interest rates in 2024?", "fed"),
        MockMarket("Will interest rates decrease this year?", "fed"),
        MockMarket("Will Bitcoin reach $100k?", "crypto"),
        MockMarket("Will BTC price hit 100000 dollars?", "crypto"),
    ]

    print(f"\n测试市场数量: {len(test_markets)}")

    # 创建筛选器
    filter = create_similarity_filter(enable_embedding=True)
    stats = filter.get_stats()
    print(f"\n筛选器状态:")
    print(f"  - 向量相似度: {'[OK] 已启用' if stats['embedding_enabled'] else '[X] 未启用'}")

    # 查找相似对
    print("\n查找相似市场对...")
    pairs = filter.find_similar_pairs(test_markets)

    print(f"\n发现 {len(pairs)} 对相似市场:")
    for m1, m2, score, discovery_type in pairs[:10]:
        dtype_label = {
            "semantic": "[SEM]",  # 语义发现
            "keyword": "[KW]",    # 关键词匹配
            "both": "[BOTH]",     # 两者都有
            None: "[KW]"
        }.get(discovery_type, "[?]")
        print(f"\n  {dtype_label} 相似度: {score:.3f} [{discovery_type or 'jaccard'}]")
        print(f"     A: {m1.question}")
        print(f"     B: {m2.question}")

    # 查找纯语义发现
    if filter.embedding_enabled:
        print("\n" + "=" * 60)
        print("[SEM] 语义发现（用词不同但语义相似 - 最有价值！）")
        print("=" * 60)

        semantic_pairs = filter.find_semantic_discoveries(test_markets)

        if semantic_pairs:
            for m1, m2, score in semantic_pairs:
                print(f"\n  [SEM] 向量相似度: {score:.3f}")
                print(f"     A: {m1.question}")
                print(f"     B: {m2.question}")
        else:
            print("\n  未发现纯语义匹配的市场对")

    print("\n测试完成！")
