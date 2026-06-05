"""Agent配置"""
import os
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class LLMConfig:
    """LLM配置"""
    # 使用阿里通义千问
    provider: str = "dashscope"
    model: str = "qwen3.7-max-2026-05-17"
    api_key: Optional[str] = None
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    temperature: float = 0.7
    max_tokens: int = 4096

    def __post_init__(self):
        if self.api_key is None:
            self.api_key = os.getenv("DASHSCOPE_API_KEY", "")


@dataclass
class EmbeddingConfig:
    """Embedding配置"""
    provider: str = os.getenv("EMBEDDING_PROVIDER", "dashscope")
    model_name: str = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-v4")
    model_path: Optional[str] = os.getenv("EMBEDDING_MODEL_PATH")
    dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "1024"))

    @property
    def model(self):
        return self.model_name


@dataclass
class ChromaConfig:
    """Chroma向量数据库配置"""
    persist_directory: str = "./chroma_db"
    collection_name: str = "travel_knowledge"
    distance_metric: str = "cosine"

    # 检索参数
    top_k: int = 10
    min_score: float = 0.5


@dataclass
class AgentConfig:
    """Agent整体配置"""
    # LLM
    llm: LLMConfig = field(default_factory=LLMConfig)

    # Embedding
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)

    # 向量数据库
    chroma: ChromaConfig = field(default_factory=ChromaConfig)

    # Agent参数
    max_questions: int = 10  # 最大追问次数
    min_info_threshold: int = 5  # 信息足够的最小阶段

    # 规划参数
    max_attractions_per_day: int = 4  # 每天最多景点数
    max_restaurants_per_day: int = 3  # 每天最多餐饮数

    # 预算分配默认比例
    default_budget_allocation: dict = None

    def __post_init__(self):
        if self.default_budget_allocation is None:
            self.default_budget_allocation = {
                "accommodation": 0.30,  # 住宿 30%
                "food": 0.25,  # 餐饮 25%
                "transport": 0.15,  # 交通 15%
                "attractions": 0.10,  # 景点 10%
                "shopping": 0.15,  # 购物 15%
                "other": 0.05,  # 其他 5%
            }


# 全局配置实例
config = AgentConfig()


# 获取配置
def get_config() -> AgentConfig:
    return config


def update_llm_config(**kwargs):
    """更新LLM配置"""
    for key, value in kwargs.items():
        if hasattr(config.llm, key):
            setattr(config.llm, key, value)


def update_embedding_config(**kwargs):
    """更新Embedding配置"""
    for key, value in kwargs.items():
        if hasattr(config.embedding, key):
            setattr(config.embedding, key, value)


def update_chroma_config(**kwargs):
    """更新Chroma配置"""
    for key, value in kwargs.items():
        if hasattr(config.chroma, key):
            setattr(config.chroma, key, value)
