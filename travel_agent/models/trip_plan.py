"""行程计划数据模型"""
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class TimeSlot(BaseModel):
    """时间段安排"""
    time_range: str = Field(description="时间范围，如 09:00-12:00")
    place_name: str = Field(description="地点名称")
    place_type: Literal["景点", "餐厅", "酒店", "购物", "交通", "休息"] = Field(description="地点类型")
    place_id: Optional[str] = Field(default=None, description="地点ID")

    # 详情
    address: str = Field(default="", description="地址")
    tips: str = Field(default="", description="游玩/用餐建议")

    # 费用
    estimated_cost: float = Field(default=0, description="预估费用")
    currency: str = Field(default="CNY", description="货币")

    # 来源
    source_refs: List[str] = Field(default_factory=list, description="参考笔记/来源")

    # 交通衔接
    transport_to_next: str = Field(default="", description="如何前往下一站")


class DayPlan(BaseModel):
    """每日行程"""
    day: int = Field(description="第几天")
    date: str = Field(default="", description="日期")
    theme: str = Field(default="", description="当日主题")
    summary: str = Field(default="", description="行程概述")

    # 时间段安排
    morning: Optional[TimeSlot] = Field(default=None)
    lunch: Optional[TimeSlot] = Field(default=None)
    afternoon: Optional[TimeSlot] = Field(default=None)
    dinner: Optional[TimeSlot] = Field(default=None)
    evening: Optional[TimeSlot] = Field(default=None)
    night: Optional[TimeSlot] = Field(default=None)

    # 当日总结
    total_cost: float = Field(default=0, description="当日总费用")
    highlights: List[str] = Field(default_factory=list, description="当日亮点")
    warnings: List[str] = Field(default_factory=list, description="注意事项")

    # 详细时间线（可选的详细版本）
    timeline: List[TimeSlot] = Field(default_factory=list, description="详细时间线")


class BudgetSummary(BaseModel):
    """预算汇总"""
    total: float = Field(description="总预算")
    breakdown: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="各部分预算明细"
    )
    estimated_total: float = Field(default=0, description="估算总费用")
    currency: str = Field(default="CNY", description="货币")


class TripPlan(BaseModel):
    """完整行程计划"""
    # 基础信息
    destination: str = Field(description="目的地")
    origin: str = Field(default="", description="出发地")
    duration: str = Field(description="行程时长，如 5天4晚")
    start_date: str = Field(default="", description="出发日期")
    end_date: str = Field(default="", description="返程日期")

    # 旅行类型
    travel_type: str = Field(default="", description="旅行性质")

    # 每日行程
    daily_plans: List[DayPlan] = Field(default_factory=list, description="每日计划")

    # 汇总
    budget_summary: BudgetSummary = Field(default_factory=BudgetSummary, description="预算汇总")

    # 住宿
    hotels: List[Dict[str, Any]] = Field(default_factory=list, description="推荐酒店")

    # 交通建议
    transport_suggestions: List[str] = Field(default_factory=list, description="交通建议")

    # 实用信息
    tips: List[str] = Field(default_factory=list, description="实用小贴士")
    warnings: List[str] = Field(default_factory=list, description="注意事项")

    # 推荐装备
    packing_list: List[str] = Field(default_factory=list, description="推荐携带物品")

    # 来源参考
    source_references: List[Dict[str, str]] = Field(default_factory=list, description="参考来源")

    def to_display_text(self) -> str:
        """转换为可读文本"""
        lines = [
            f"# {self.destination} {self.duration} {self.travel_type}旅行",
            "",
            f"出发日期: {self.start_date}",
            f"返程日期: {self.end_date}",
            "",
            "## 每日行程",
            ""
        ]

        for day in self.daily_plans:
            lines.append(f"### Day {day.day}: {day.theme}")
            if day.summary:
                lines.append(f"概述: {day.summary}")
            lines.append("")

            for slot_name in ["morning", "lunch", "afternoon", "dinner", "evening"]:
                slot = getattr(day, slot_name, None)
                if slot:
                    lines.append(f"**{slot.time_range}** {slot.place_type}: {slot.place_name}")
                    if slot.tips:
                        lines.append(f"  建议: {slot.tips}")
                    if slot.estimated_cost:
                        lines.append(f"  费用: ¥{slot.estimated_cost:.0f}")
                    lines.append("")

            lines.append("---")
            lines.append("")

        # 预算汇总
        lines.append("## 预算汇总")
        lines.append(f"总预算: ¥{self.budget_summary.total:.0f}")
        for category, details in self.budget_summary.breakdown.items():
            lines.append(f"- {category}: ¥{details.get('amount', 0):.0f}")
        lines.append("")

        # 小贴士
        if self.tips:
            lines.append("## 实用小贴士")
            for tip in self.tips:
                lines.append(f"- {tip}")
            lines.append("")

        return "\n".join(lines)
