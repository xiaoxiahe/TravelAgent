"""景点数据模型"""
from typing import List, Optional
from pydantic import BaseModel, Field


class Attraction(BaseModel):
    """景点模型"""
    id: str = Field(description="唯一标识")
    name: str = Field(description="景点名称")
    name_en: Optional[str] = Field(default=None, description="英文名")
    location: str = Field(description="地址")
    city: str = Field(description="所在城市")
    country: str = Field(default="日本", description="国家")

    # 分类
    category: str = Field(description="类别：景点/购物/娱乐/自然等")
    tags: List[str] = Field(default_factory=list, description="标签")

    # 游玩信息
    opening_hours: str = Field(default="", description="营业时间")
    suggested_duration: str = Field(default="1-2小时", description="建议游玩时长")
    best_season: List[str] = Field(default_factory=list, description="最佳季节")
    ticket_price: Optional[str] = Field(default=None, description="门票价格")

    # 评分和热度
    rating: float = Field(default=0, description="评分 0-5")
    review_count: int = Field(default=0, description="评价数")
    popularity: int = Field(default=0, description="热度指数")

    # 用户相关
    recommended_for: List[str] = Field(default_factory=list, description="适合人群：情侣/家庭/朋友等")
    suitable_for: List[str] = Field(default_factory=list, description="适合场景")

    # 描述
    description: str = Field(default="", description="简介")
    highlights: List[str] = Field(default_factory=list, description="亮点")
    tips: List[str] = Field(default_factory=list, description="小贴士")

    # 坐标
    latitude: Optional[float] = Field(default=None)
    longitude: Optional[float] = Field(default=None)

    # 情感分析
    sentiment_score: float = Field(default=0, description="情感得分 -1到1")
    authenticity_score: float = Field(default=0, description="真实度 0到1")

    # 源数据
    source_url: str = Field(default="", description="小红书笔记链接")
    source_note_id: str = Field(default="", description="源笔记ID")

    def to_search_text(self) -> str:
        """转换为搜索文本"""
        return f"{self.name} {self.location} {' '.join(self.tags)} {self.description}"
