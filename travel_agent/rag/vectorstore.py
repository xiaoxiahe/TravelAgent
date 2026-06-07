"""Chroma向量数据库封装"""
from typing import List, Dict, Any, Optional, Tuple
import json
from pathlib import Path

import chromadb
from chromadb.config import Settings
from chromadb.api.models.Collection import Collection

from travel_agent.rag.embedder import create_embedder, Embedder
from travel_agent.agent.config import config as agent_config


class ChromaVectorStore:
    """Chroma向量数据库封装"""

    def __init__(
        self,
        persist_directory: str = "./chroma_db",
        collection_name: str = "travel_knowledge",
        embedder: Optional[Embedder] = None,
        metadata_filter: Optional[Dict[str, Any]] = None
    ):
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        self.collection_name = collection_name
        self.embedder = embedder or create_embedder(
            provider=agent_config.embedding.provider,
            model_name=agent_config.embedding.model_name,
            dimension=agent_config.embedding.dimension,
        )
        self.metadata_filter = metadata_filter

        # 初始化Chroma客户端
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(anonymized_telemetry=False)
        )

        self._collection: Optional[Collection] = None

    @property
    def collection(self) -> Collection:
        """获取Collection，延迟初始化"""
        if self._collection is None:
            try:
                self._collection = self.client.get_collection(name=self.collection_name)
            except Exception:
                # Collection不存在，创建新的（dimension由首次添加的向量决定）
                self._collection = self.client.create_collection(
                    name=self.collection_name,
                    metadata={"description": "Travel knowledge base"}
                )
        return self._collection

    def _format_dimension_error(self, actual_dimension: int) -> ValueError:
        expected_dimension = getattr(self.embedder, "dimension", None)
        expected_text = expected_dimension if expected_dimension is not None else "unknown"
        return ValueError(
            f"Collection '{self.collection_name}' 的向量维度与当前 embedding 配置不一致："
            f"集合中已有 {actual_dimension} 维向量，但当前配置生成 {expected_text} 维。"
            "请统一使用同一 embedding 模型，或清空/重建该 collection。"
        )

    @staticmethod
    def _extract_collection_dimension(exc: Exception) -> Optional[int]:
        message = str(exc)
        import re
        match = re.search(r"dimension of (\d+), got (\d+)", message)
        if match:
            return int(match.group(1))
        return None

    def add_documents(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None
    ) -> List[str]:
        """添加文档到向量库"""
        if ids is None:
            import uuid
            ids = [str(uuid.uuid4()) for _ in documents]

        if metadatas is None:
            metadatas = [{} for _ in documents]

        # 生成embeddings
        embeddings = self.embedder.encode(documents)

        # 添加到collection
        try:
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids,
                embeddings=embeddings.tolist()
            )
        except Exception as exc:
            actual_dimension = self._extract_collection_dimension(exc)
            if actual_dimension is not None:
                raise self._format_dimension_error(actual_dimension) from exc
            raise

        return ids

    def search(
        self,
        query: str,
        top_k: int = 10,
        filter_criteria: Optional[Dict[str, Any]] = None,
        include: List[str] = ["documents", "metadatas", "distances"]
    ) -> List[Dict[str, Any]]:
        """搜索相似文档"""
        # 编码查询
        query_embedding = self.embedder.encode_query(query)

        # 执行查询
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=top_k,
                where=filter_criteria or self.metadata_filter,
                include=include
            )
        except Exception as exc:
            actual_dimension = self._extract_collection_dimension(exc)
            if actual_dimension is not None:
                raise self._format_dimension_error(actual_dimension) from exc
            raise

        # 格式化结果
        formatted_results = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                formatted_results.append({
                    "content": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else None,
                    "id": results["ids"][0][i] if results["ids"] else None
                })

        return formatted_results

    def search_by_vector(
        self,
        vector: List[float],
        top_k: int = 10,
        filter_criteria: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """通过向量搜索"""
        try:
            results = self.collection.query(
                query_embeddings=[vector],
                n_results=top_k,
                where=filter_criteria or self.metadata_filter
            )
        except Exception as exc:
            actual_dimension = self._extract_collection_dimension(exc)
            if actual_dimension is not None:
                raise self._format_dimension_error(actual_dimension) from exc
            raise

        formatted_results = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                formatted_results.append({
                    "content": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else None,
                    "id": results["ids"][0][i] if results["ids"] else None
                })

        return formatted_results

    def get_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取文档"""
        try:
            result = self.collection.get(ids=[doc_id], include=["documents", "metadatas"])
            if result["documents"]:
                return {
                    "content": result["documents"][0],
                    "metadata": result["metadatas"][0] if result["metadatas"] else {},
                    "id": doc_id
                }
        except Exception:
            pass
        return None

    def delete(self, ids: List[str]) -> bool:
        """删除文档"""
        try:
            self.collection.delete(ids=ids)
            return True
        except Exception:
            return False

    def count(self) -> int:
        """获取文档数量"""
        return self.collection.count()

    def peek(self, limit: int = 10) -> List[Dict[str, Any]]:
        """查看前N条文档"""
        result = self.collection.peek(limit=limit)
        return [
            {
                "content": doc,
                "metadata": meta,
                "id": id_
            }
            for doc, meta, id_ in zip(
                result.get("documents", []),
                result.get("metadatas", []),
                result.get("ids", [])
            )
        ]

    def clear(self) -> bool:
        """清空集合"""
        try:
            self.client.delete_collection(self.collection_name)
            self._collection = None
            return True
        except Exception:
            return False


# 全局实例
_vector_store: Optional[ChromaVectorStore] = None


def get_vector_store(
    persist_directory: str = "./chroma_db",
    collection_name: str = "travel_knowledge"
) -> ChromaVectorStore:
    """获取全局VectorStore实例"""
    global _vector_store
    if _vector_store is None:
        _vector_store = ChromaVectorStore(
            persist_directory=persist_directory,
            collection_name=collection_name
        )
    return _vector_store


def init_vector_store(**kwargs) -> ChromaVectorStore:
    """初始化全局VectorStore"""
    global _vector_store
    _vector_store = ChromaVectorStore(**kwargs)
    return _vector_store
