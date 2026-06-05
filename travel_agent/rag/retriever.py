"""检索器模块"""
from typing import List, Dict, Any, Optional
import json

from travel_agent.rag.vectorstore import ChromaVectorStore, get_vector_store
from travel_agent.rag.query_expander import QueryExpander, QueryParser


class RetrievalResult:
    """检索结果"""

    def __init__(
        self,
        content: str,
        metadata: Dict[str, Any],
        score: float,
        doc_id: str = None
    ):
        self.content = content
        self.metadata = metadata
        self.score = score
        self.id = doc_id

    @property
    def source_type(self) -> str:
        """来源类型"""
        return self.metadata.get("type", "unknown")

    @property
    def source_name(self) -> str:
        """来源名称"""
        return self.metadata.get("name", "未知")

    @property
    def url(self) -> str:
        """来源URL"""
        return self.metadata.get("url", "")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "metadata": self.metadata,
            "score": self.score,
            "id": self.id,
            "source_type": self.source_type,
            "source_name": self.source_name,
        }


class MultiQueryRetriever:
    """多查询检索器"""

    def __init__(
        self,
        vector_store: Optional[ChromaVectorStore] = None,
        top_k: int = 10,
        fusion_method: str = "rrf"  # reciprocal rank fusion
    ):
        self.vector_store = vector_store or get_vector_store()
        self.top_k = top_k
        self.fusion_method = fusion_method
        self.query_expander = QueryExpander()
        self.query_parser = QueryParser()

    def retrieve(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> List[RetrievalResult]:
        """执行检索"""
        # 扩展查询
        expanded_queries = self.query_expander.expand(query, context)

        # 对每个查询执行检索
        all_results = []
        for q in expanded_queries:
            results = self.vector_store.search(
                query=q,
                top_k=self.top_k,
                filter_criteria=filters
            )
            all_results.extend(results)

        # 融合结果
        fused_results = self._fusion(all_results, k=60 if self.fusion_method == "rrf" else 1)

        # 转换为RetrievalResult
        return [
            RetrievalResult(
                content=r["content"],
                metadata=r.get("metadata", {}),
                score=r.get("score", 0),
                doc_id=r.get("id")
            )
            for r in fused_results
        ]

    def _fusion(self, results: List[Dict], k: int = 60) -> List[Dict]:
        """结果融合"""
        if self.fusion_method == "rrf":
            return self._reciprocal_rank_fusion(results, k)
        elif self.fusion_method == "score_avg":
            return self._score_average_fusion(results)
        else:
            return results

    def _reciprocal_rank_fusion(self, results: List[Dict], k: int) -> List[Dict]:
        """倒数排名融合 (RRF)"""
        doc_scores = {}

        for result in results:
            doc_id = result.get("id", result.get("content", ""))
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {
                    "content": result.get("content"),
                    "metadata": result.get("metadata", {}),
                    "rrf_score": 0
                }
            # RRF公式: 1/(k+rank)
            rank = results.index(result) + 1
            doc_scores[doc_id]["rrf_score"] += 1 / (k + rank)

        # 按RRF分数排序
        sorted_docs = sorted(
            doc_scores.values(),
            key=lambda x: x["rrf_score"],
            reverse=True
        )

        # 重新计算归一化分数
        max_score = max((d["rrf_score"] for d in sorted_docs), default=1)
        for doc in sorted_docs:
            doc["score"] = doc["rrf_score"] / max_score if max_score > 0 else 0

        return sorted_docs

    def _score_average_fusion(self, results: List[Dict]) -> List[Dict]:
        """分数平均融合"""
        doc_scores = {}

        for result in results:
            doc_id = result.get("id", result.get("content", ""))
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {
                    "content": result.get("content"),
                    "metadata": result.get("metadata", {}),
                    "total_score": 0,
                    "count": 0
                }
            doc_scores[doc_id]["total_score"] += result.get("score", 0)
            doc_scores[doc_id]["count"] += 1

        # 计算平均分数
        for doc in doc_scores.values():
            doc["score"] = doc["total_score"] / doc["count"] if doc["count"] > 0 else 0

        return sorted(
            doc_scores.values(),
            key=lambda x: x["score"],
            reverse=True
        )


class AttractionRetriever:
    """景点检索器"""

    def __init__(self, retriever: MultiQueryRetriever = None, collection_name: str = "travel"):
        self.retriever = retriever
        self.expander = QueryExpander()
        self._collection_name = collection_name
        self._vector_store = None

    @property
    def vector_store(self):
        if self._vector_store is None:
            self._vector_store = get_vector_store(collection_name=self._collection_name)
        return self._vector_store

    def retrieve_attractions(
        self,
        destination: str,
        travel_type: str = None,
        preferences: Dict[str, Any] = None,
        top_k: int = 20
    ) -> List[RetrievalResult]:
        """检索景点"""
        query_parts = [destination, "景点"]

        if travel_type:
            query_parts.append(travel_type)

        if preferences:
            query_parts.extend(preferences.get("interests", []))

        query = " ".join(query_parts)

        expanded_queries = self.expander.expand_for_attraction(query, travel_type)

        all_results = []
        for q in expanded_queries:
            results = self.vector_store.search(
                query=q,
                top_k=top_k,
                filter_criteria={"type": "attraction"}
            )
            all_results.extend(results)

        fused = self.retriever._fusion(all_results) if self.retriever else all_results

        return [
            RetrievalResult(
                content=r["content"],
                metadata=r.get("metadata", {}),
                score=r.get("score", 0),
                doc_id=r.get("id")
            )
            for r in fused
        ]


class RestaurantRetriever:
    """餐厅检索器"""

    def __init__(self, retriever: MultiQueryRetriever = None, collection_name: str = "restaurant"):
        self.retriever = retriever
        self.expander = QueryExpander()
        self._collection_name = collection_name
        self._vector_store = None

    @property
    def vector_store(self):
        if self._vector_store is None:
            self._vector_store = get_vector_store(collection_name=self._collection_name)
        return self._vector_store

    def retrieve_restaurants(
        self,
        location: str,
        scene: str = None,
        cuisine_type: str = None,
        price_range: str = None,
        top_k: int = 15
    ) -> List[RetrievalResult]:
        """检索餐厅"""
        query_parts = [location, "餐厅"]

        if cuisine_type:
            query_parts.append(cuisine_type)

        if scene:
            query_parts.append(scene)

        query = " ".join(query_parts)

        expanded_queries = self.expander.expand_for_restaurant(query, scene)

        filters = [{"type": "restaurant"}]
        if cuisine_type:
            filters.append({"cuisine_type": cuisine_type})
        where_clause = {"$and": filters} if len(filters) > 1 else filters[0]

        all_results = []
        for q in expanded_queries:
            results = self.vector_store.search(
                query=q,
                top_k=top_k,
                filter_criteria=where_clause
            )
            all_results.extend(results)

        fused = self.retriever._fusion(all_results) if self.retriever else all_results

        return [
            RetrievalResult(
                content=r["content"],
                metadata=r.get("metadata", {}),
                score=r.get("score", 0),
                doc_id=r.get("id")
            )
            for r in fused
        ]


def create_retriever(
    collection_name: str = "travel_knowledge",
    persist_directory: str = "./chroma_db"
) -> MultiQueryRetriever:
    """创建检索器实例"""
    vector_store = get_vector_store(persist_directory, collection_name)
    return MultiQueryRetriever(vector_store=vector_store)
