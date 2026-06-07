"""餐厅数据模型"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class Restaurant(BaseModel):
    """餐厅模型"""
    id: str = Field(description="唯一标识")
    name: str = Field(description="餐厅名称")
    name_en: Optional[str] = Field(default=None, description="英文名")

    # 基本信息
    location: str = Field(description="地址")
    city: str = Field(description="所在城市")
    area: str = Field(default="", description="所属区域")
    latitude: Optional[float] = Field(default=None)
    longitude: Optional[float] = Field(default=None)

    # 分类
    cuisine_type: str = Field(description="菜系")
    price_level: Literal["经济实惠", "适中", "高端", "奢华"] = Field(default="适中")
    price_range: str = Field(default="", description="价格区间，如 ¥100-200/人")

    # 环境和服务
    ambiance: List[str] = Field(default_factory=list, description="环境氛围")
    noise_level: Literal["安静", "适中", "热闹"] = Field(default="适中")
    service: List[str] = Field(default_factory=list, description="服务特点")

    # 特色
    specialties: List[str] = Field(default_factory=list, description="招牌菜")
    features: List[str] = Field(default_factory=list, description="特色标签")
    recommended_dishes: List[str] = Field(default_factory=list, description="推荐菜品")

    # 评分
    rating: float = Field(default=0, description="评分 0-5")
    review_count: int = Field(default=0, description="评价数")

    # 场景适配
    suitable_scenes: List[str] = Field(default_factory=list, description="适合场景")
    suitable_for: List[str] = Field(default_factory=list, description="适合人群")

    # 营业信息
    opening_hours: str = Field(default="", description="营业时间")
    closed_days: str = Field(default="", description="休息日")
    has_private_room: bool = Field(default=False, description="是否有包间")

    # 预订和排队
    reservation_required: bool = Field(default=False, description="是否需要预约")
    queue_status: str = Field(default="", description="排队情况")
    booking_tips: str = Field(default="", description="预约建议")

    # 儿童友好
    kid_friendly: bool = Field(default=False, description="是否儿童友好")
    kids_menu: bool = Field(default=False, description="是否有儿童餐")

    # 评价摘要
    positive_reviews: List[str] = Field(default_factory=list, description="正面评价摘要")
    negative_reviews: List[str] = Field(default_factory=list, description="负面评价摘要")
    tips: List[str] = Field(default_factory=list, description="小贴士")

    # 情感分析
    sentiment_score: float = Field(default=0, description="情感得分 -1到1")
    authenticity_score: float = Field(default=0, description="真实度 0到1")

    # 源数据
    source_url: str = Field(default="", description="小红书笔记链接")
    source_note_id: str = Field(default="", description="源笔记ID")

    def to_search_text(self) -> str:
        """转换为搜索文本"""
        return f"{self.name} {self.cuisine_type} {self.location} {' '.join(self.specialties)}"


class SceneType:
    """餐厅场景类型"""
    BUSINESS_DINNER = "business_dinner"
    DATE_NIGHT = "date_night"
    FAMILY_MEAL = "family_meal"
    QUICK_BITE = "quick_bite"
    SPECIAL_OCCASION = "special_occasion"
    CASUAL_FRIENDS = "casual_friends"
    BREAKFAST = "breakfast"
    LATE_NIGHT = "late_night"

    @classmethod
    def get_keywords(cls, scene: str) -> List[str]:
        """获取场景关键词"""
        keywords_map = {
            cls.BUSINESS_DINNER: ["商务宴请", "高端", "包间", "私密", "正式"],
            cls.DATE_NIGHT: ["约会", "浪漫", "夜景", "氛围感", "烛光"],
            cls.FAMILY_MEAL: ["家庭聚餐", "儿童友好", "分量足", "长辈"],
            cls.QUICK_BITE: ["快餐", "小吃", "性价比", "便捷"],
            cls.SPECIAL_OCCASION: ["纪念日", "生日", "米其林", "仪式感"],
            cls.CASUAL_FRIENDS: ["朋友聚餐", "放松", "热闹"],
            cls.BREAKFAST: ["早餐", "早茶", "brunch"],
            cls.LATE_NIGHT: ["宵夜", "深夜食堂", "夜宵"],
        }
        return keywords_map.get(scene, [])
