"""用户画像模型 - 定义旅行规划所需的用户信息"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class CompanionInfo(BaseModel):
    """同行人信息"""
    relation: str = Field(default="朋友", description="关系：配偶/父母/子女/朋友/同事/独自")
    age_range: Literal["儿童", "青少年", "青年", "中年", "老年"] = Field(default="青年", description="年龄段")
    count: int = Field(default=1, description="人数")
    special_needs: List[str] = Field(default_factory=list, description="特殊需求")


class BudgetBreakdown(BaseModel):
    """预算分配"""
    accommodation: float = Field(default=0, description="住宿预算")
    food: float = Field(default=0, description="餐饮预算")
    transport: float = Field(default=0, description="交通预算")
    attractions: float = Field(default=0, description="景点门票预算")
    shopping: float = Field(default=0, description="购物预算")
    other: float = Field(default=0, description="其他预算")


class FoodPreferences(BaseModel):
    """口味偏好"""
    cuisine_types: List[str] = Field(default_factory=list, description="喜欢的菜系")
    price_range: Literal["经济实惠", "适中", "高端"] = Field(default="适中")
    must_have: List[str] = Field(default_factory=list, description="必须包含的食物")
    avoid: List[str] = Field(default_factory=list, description="不喜欢的食物")
    dietary_restrictions: List[str] = Field(default_factory=list, description="饮食限制/过敏")


class AccommodationPreferences(BaseModel):
    """住宿偏好"""
    type: Literal["酒店", "民宿", "青旅", "公寓", "豪华酒店"] = Field(default="酒店")
    location: str = Field(default="", description="位置偏好（如靠近地铁站）")
    star_level: Optional[int] = Field(default=None, description="星级要求")
    amenities: List[str] = Field(default_factory=list, description="设施要求")


class TransportPreferences(BaseModel):
    """交通偏好"""
    mode: Literal["公共交通", "打车", "包车", "自驾", "步行"] = Field(default="公共交通")
    jr_pass: bool = Field(default=False, description="是否使用JR Pass")


class UserProfile(BaseModel):
    """用户画像 - 完整旅行偏好"""
    # 基础信息
    destination: str = Field(default="", description="目的地")
    origin: str = Field(default="", description="出发地")
    duration_days: Optional[int] = Field(default=None, description="旅行天数（精确值）")
    duration_days_range: Optional[str] = Field(default=None, description="旅行天数范围（如'3-5天'）")
    travel_date: Optional[str] = Field(default=None, description="出发日期")

    # 旅行性质
    travel_type: Literal[
        "蜜月旅行", "家庭出游", "独自旅行", "朋友团建", "商务旅行", "亲子游", "毕业旅行", "其他"
    ] = Field(default="其他", description="旅行性质")

    # 同行人
    companions: List[CompanionInfo] = Field(default_factory=list, description="同行人列表")

    # 预算
    budget_total: Optional[float] = Field(default=None, description="总预算")
    budget_breakdown: BudgetBreakdown = Field(default_factory=BudgetBreakdown, description="预算分配")

    # 偏好
    rhythm_preference: Literal["休闲", "适中", "暴走"] = Field(default="适中", description="旅行节奏")
    food_preferences: FoodPreferences = Field(default_factory=FoodPreferences)
    accommodation_preference: AccommodationPreferences = Field(default_factory=AccommodationPreferences)
    transport_preference: TransportPreferences = Field(default_factory=TransportPreferences)

    # 特殊要求
    must_visit: List[str] = Field(default_factory=list, description="必去景点")
    avoid_places: List[str] = Field(default_factory=list, description="不想去的地方")
    notes: str = Field(default="", description="其他备注")

    # 信息收集进度
    info_stage: int = Field(default=0, description="当前信息收集阶段")

    def is_info_sufficient(self) -> bool:
        """判断信息是否足够开始规划"""
        try:
            duration = int(self.duration_days) if not isinstance(self.duration_days, int) else self.duration_days
            budget = float(self.budget_total) if not isinstance(self.budget_total, float) else self.budget_total
            return all([
                bool(self.destination),
                bool(self.travel_type),
                duration > 0,
                budget > 0,
                self.info_stage >= 3,
            ])
        except (ValueError, TypeError):
            return False

    def get_next_question(self) -> tuple[str, dict]:
        """获取下一个需要收集的问题"""
        questions = [
            ("travel_type", {"question": "这次旅行的性质是什么？", "options": [
                {"value": "蜜月旅行", "emoji": "💕"},
                {"value": "家庭出游", "emoji": "👨‍👩‍👧"},
                {"value": "独自旅行", "emoji": "🎒"},
                {"value": "朋友团建", "emoji": "👥"},
                {"value": "商务旅行", "emoji": "💼"},
                {"value": "亲子游", "emoji": "🧒"},
                {"value": "毕业旅行", "emoji": "🎓"},
                {"value": "其他", "emoji": "✏️"}
            ]}),
            ("duration_days", {"question": "计划玩几天？", "type": "number"}),
            ("budget_total", {"question": "您的总预算大概是？", "type": "budget"}),
            ("rhythm_preference", {"question": "旅行节奏偏好？", "options": [
                {"value": "休闲", "desc": "轻松愉快，不赶时间"},
                {"value": "适中", "desc": "合理安排，有玩有休息"},
                {"value": "暴走", "desc": "高效打卡，最大化行程"}
            ]}),
            ("food_preferences", {"question": "口味偏好？", "type": "food"}),
            ("accommodation", {"question": "住宿偏好？", "type": "accommodation"}),
        ]
        if self.info_stage < len(questions):
            return questions[self.info_stage]
        return ("complete", {})
