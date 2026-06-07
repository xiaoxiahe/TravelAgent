"""酒店数据模型"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class Hotel(BaseModel):
    """酒店模型"""
    id: str = Field(description="唯一标识")
    name: str = Field(description="酒店名称")
    name_en: Optional[str] = Field(default=None, description="英文名")

    # 位置
    location: str = Field(description="地址")
    city: str = Field(description="所在城市")
    area: str = Field(default="", description="所属区域/商圈")
    latitude: Optional[float] = Field(default=None)
    longitude: Optional[float] = Field(default=None)

    # 类型
    hotel_type: Literal["经济型", "舒适型", "高档型", "豪华型", "民宿", "公寓", "青旅"] = Field(
        default="舒适型"
    )
    star_rating: Optional[int] = Field(default=None, description="星级")

    # 价格
    price_range: str = Field(default="", description="价格区间")
    price_per_night: float = Field(default=0, description="每晚价格")
    currency: str = Field(default="CNY", description="货币")

    # 设施
    amenities: List[str] = Field(default_factory=list, description="设施服务")
    room_features: List[str] = Field(default_factory=list, description="房间特色")

    # 评分
    rating: float = Field(default=0, description="评分 0-5")
    review_count: int = Field(default=0, description="评价数")

    # 交通
    nearest_station: str = Field(default="", description="最近地铁站")
    distance_to_station: str = Field(default="", description="到地铁站距离")
    airport_transfer: bool = Field(default=False, description="是否提供接送机")

    # 服务
    check_in_time: str = Field(default="15:00", description="入住时间")
    check_out_time: str = Field(default="11:00", description="退房时间")
    luggage_storage: bool = Field(default=False, description="是否可寄存行李")

    # 适合人群
    suitable_for: List[str] = Field(default_factory=list, description="适合人群")
    recommended_for_scenes: List[str] = Field(default_factory=list, description="推荐场景")

    # 评价摘要
    positive_reviews: List[str] = Field(default_factory=list, description="好评摘要")
    negative_reviews: List[str] = Field(default_factory=list, description="差评摘要")
    tips: List[str] = Field(default_factory=list, description="小贴士")

    # 图片
    image_urls: List[str] = Field(default_factory=list, description="图片链接")

    # 源数据
    booking_url: str = Field(default="", description="预订链接")

    def to_search_text(self) -> str:
        """转换为搜索文本"""
        return f"{self.name} {self.area} {self.hotel_type} {','.join(self.amenities)}"
