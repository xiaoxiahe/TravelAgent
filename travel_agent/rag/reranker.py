"""重排序模块"""
from typing import List, Dict, Any, Optional
import numpy as np

from travel_agent.rag.retriever import RetrievalResult


class Reranker:
    """检索结果重排序"""

    def __init__(
        self,
        model_name: str = "text2vec-base-chinese",
        device: str = "cpu"
    ):
        self.model_name = model_name
        self.device = device
        self._model = None

    def _load_model(self):
        """延迟加载模型"""
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(
                    f"sentence-transformers/{self.model_name}",
                    max_length=512,
                    device=self.device
                )
            except ImportError:
                raise ImportError("请安装 sentence-transformers: pip install sentence-transformers")

    def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: int = 10
    ) -> List[RetrievalResult]:
        """对检索结果进行重排序"""
        if not results:
            return []

        self._load_model()

        # 准备句子对
        sentence_pairs = [(query, r.content) for r in results]

        # 计算相关性分数
        scores = self._model.predict(sentence_pairs)

        # 更新结果分数并排序
        for result, score in zip(results, scores):
            result.score = float(score)

        results.sort(key=lambda x: x.score, reverse=True)

        return results[:top_k]


class FeatureBasedReranker:
    """基于特征的重排序"""

    def __init__(self):
        self.feature_weights = {
            "popularity": 0.2,      # 热度
            "rating": 0.25,         # 评分
            "authenticity": 0.25,   # 真实度
            "recency": 0.15,        # 时效性
            "user_match": 0.15,     # 用户偏好匹配度
        }

    def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        user_preferences: Optional[Dict[str, Any]] = None,
        top_k: int = 10
    ) -> List[RetrievalResult]:
        """基于多特征重排序"""
        if not results:
            return []

        for result in results:
            # 计算综合分数
            metadata = result.metadata

            # 基础相关性分数
            base_score = result.score

            # 热度分数
            popularity = metadata.get("popularity", 0)
            popularity_score = min(popularity / 10000, 1.0)  # 归一化

            # 评分分数
            rating = metadata.get("rating", 0)
            rating_score = rating / 5.0 if rating else 0

            # 真实度分数
            authenticity = metadata.get("authenticity_score", 0.5)

            # 时效性分数（新内容权重更高）
            recency_days = metadata.get("recency_days", 365)
            recency_score = max(0, 1 - recency_days / 365)

            # 用户偏好匹配度
            user_match_score = 0.5
            if user_preferences:
                # 检查标签匹配
                tags = set(metadata.get("tags", []))
                preferences = set(user_preferences.get("interests", []))
                if tags and preferences:
                    intersection = len(tags & preferences)
                    union = len(tags | preferences)
                    user_match_score = intersection / union if union > 0 else 0

            # 综合分数
            final_score = (
                base_score * 0.4 +
                popularity_score * self.feature_weights["popularity"] +
                rating_score * self.feature_weights["rating"] +
                authenticity * self.feature_weights["authenticity"] +
                recency_score * self.feature_weights["recency"] +
                user_match_score * self.feature_weights["user_match"]
            )

            result.score = final_score

        # 排序
        results.sort(key=lambda x: x.score, reverse=True)

        return results[:top_k]


class HybridReranker:
    """混合重排序 - 结合语义和特征"""

    def __init__(
        self,
        cross_encoder_model: str = "text2vec-base-chinese",
        use_features: bool = True
    ):
        self.semantic_reranker = Reranker(model_name=cross_encoder_model) if use_features else None
        self.feature_reranker = FeatureBasedReranker()
        self.use_features = use_features

    def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        user_preferences: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
        weights: Dict[str, float] = None
    ) -> List[RetrievalResult]:
        """混合重排序"""
        if not results:
            return []

        if weights is None:
            weights = {"semantic": 0.6, "feature": 0.4}

        # 语义重排序
        if self.semantic_reranker:
            semantic_results = self.semantic_reranker.rerank(query, results.copy(), len(results))
            semantic_scores = {r.id: r.score for r in semantic_results}
        else:
            semantic_scores = {r.id: r.score for r in results}

        # 特征重排序
        feature_results = self.feature_reranker.rerank(
            query,
            results.copy(),
            user_preferences,
            len(results)
        )
        feature_scores = {r.id: r.score for r in feature_results}

        # 合并分数
        for result in results:
            semantic = semantic_scores.get(result.id, 0)
            feature = feature_scores.get(result.id, 0)
            result.score = (
                weights.get("semantic", 0.6) * semantic +
                weights.get("feature", 0.4) * feature
            )

        # 最终排序
        results.sort(key=lambda x: x.score, reverse=True)

        return results[:top_k]


def create_reranker(reranker_type: str = "hybrid", **kwargs) -> Any:
    """创建重排序器"""
    rerankers = {
        "semantic": Reranker,
        "feature": FeatureBasedReranker,
        "hybrid": HybridReranker,
    }

    if reranker_type not in rerankers:
        raise ValueError(f"不支持的重排序类型: {reranker_type}")

    return rerankers[reranker_type](**kwargs)
