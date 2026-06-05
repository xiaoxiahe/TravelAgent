"""Embedding模块"""
from abc import ABC, abstractmethod
from typing import List, Optional
import os
import numpy as np


class Embedder(ABC):
    """Embedding基类"""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", dimension: int = 384):
        self.model_name = model_name
        self.dimension = dimension

    @abstractmethod
    def encode(self, texts: List[str], normalize: bool = True) -> np.ndarray:
        """编码文本为向量"""
        pass

    def __call__(self, text: str, normalize: bool = True) -> np.ndarray:
        """单条编码"""
        return self.encode([text], normalize=normalize)[0]

    def encode_query(self, query: str, normalize: bool = True) -> np.ndarray:
        """编码查询文本，与encode相同但可用于区分语义"""
        return self.encode([query], normalize=normalize)[0]


class LocalEmbedder(Embedder):
    """使用本地Sentence Transformer的Embedding"""

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        dimension: int = 384,
        device: str = None,
        model_path: Optional[str] = None,
    ):
        super().__init__(model_name=model_name, dimension=dimension)
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError("请安装 sentence-transformers: pip install sentence-transformers")

        self.device = device or ("cuda" if _check_cuda() else "cpu")
        candidate_paths = self._build_candidate_paths(model_name, model_path)

        load_error = None
        self.model = None
        for candidate, local_only in candidate_paths:
            try:
                self.model = SentenceTransformer(candidate, device=self.device, local_files_only=local_only)
                break
            except Exception as exc:
                load_error = exc

        if self.model is None:
            searched = ", ".join(path for path, _ in candidate_paths)
            raise RuntimeError(
                f"本地 embedding 模型加载失败。已尝试: {searched}。"
                "请先将模型下载到本地，并通过 EMBEDDING_MODEL_PATH 指定目录。"
            ) from load_error

        get_dimension = getattr(self.model, "get_embedding_dimension", None)
        if callable(get_dimension):
            self.dimension = get_dimension()
        else:
            self.dimension = self.model.get_sentence_embedding_dimension()

    @staticmethod
    def _build_candidate_paths(model_name: str, model_path: Optional[str]) -> list[tuple[str, bool]]:
        candidates: list[tuple[str, bool]] = []

        if model_path:
            candidates.append((model_path, True))

        env_path = os.getenv("EMBEDDING_MODEL_PATH")
        if env_path and env_path != model_path:
            candidates.append((env_path, True))

        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        project_model_dir = os.path.join(base_dir, "models", model_name)
        candidates.append((project_model_dir, True))

        cache_dir = os.getenv("SENTENCE_TRANSFORMERS_HOME") or os.path.expanduser("~/.cache/torch/sentence_transformers")
        cache_model_dir = os.path.join(cache_dir, model_name.replace("/", "_"))
        candidates.append((cache_model_dir, True))

        candidates.append((model_name, False))

        deduped: list[tuple[str, bool]] = []
        seen = set()
        for path, local_only in candidates:
            if path and path not in seen:
                deduped.append((path, local_only))
                seen.add(path)
        return deduped

    def encode(self, texts: List[str], normalize: bool = True) -> np.ndarray:
        """使用本地模型编码"""
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=normalize,
            convert_to_numpy=True,
            show_progress_bar=len(texts) > 10,
        )
        return embeddings


class DashScopeEmbedder(Embedder):
    """使用DashScope/百炼 API的Embedding（OpenAI兼容模式）"""

    def __init__(self, api_key: str, model_name: str = "text-embedding-v4", dimension: int = 1024):
        super().__init__(model_name=model_name, dimension=dimension)
        self.api_key = api_key
        self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def encode(self, texts: List[str], normalize: bool = True) -> np.ndarray:
        """使用百炼 OpenAI 兼容 API 编码"""
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("请安装 openai: pip install openai")

        client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

        embeddings = []
        for text in texts:
            response = client.embeddings.create(
                model=self.model_name,
                input=text,
                dimensions=self.dimension,
                encoding_format="float",
            )
            embedding = response.data[0].embedding
            emb = np.array(embedding)

            if normalize:
                norm = np.linalg.norm(emb)
                if norm > 0:
                    emb = emb / norm

            embeddings.append(emb)

        return np.array(embeddings)


def _check_cuda() -> bool:
    """检查CUDA是否可用"""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def create_embedder(provider: str = "local", **kwargs) -> Embedder:
    """创建Embedder实例"""
    if provider == "local":
        return LocalEmbedder(**kwargs)
    elif provider == "dashscope":
        import os
        api_key = kwargs.get("api_key") or os.environ.get("DASHSCOPE_API_KEY", "")
        return DashScopeEmbedder(api_key=api_key, **kwargs)
    else:
        raise ValueError(f"Unknown embedder provider: {provider}")
