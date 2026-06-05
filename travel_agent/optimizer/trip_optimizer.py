"""行程优化器"""
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import random
import math

from travel_agent.models.user_profile import UserProfile
from travel_agent.models.attraction import Attraction
from travel_agent.models.restaurant import Restaurant
from travel_agent.models.trip_plan import TripPlan, DayPlan, TimeSlot, BudgetSummary


@dataclass
class Constraint:
    """约束条件"""
    name: str
    check_func: callable
    weight: float = 1.0


class TripOptimizer:
    """行程优化器 - 多目标优化"""

    def __init__(
        self,
        max_attractions_per_day: int = 4,
        max_restaurants_per_day: int = 3,
        rest_duration_minutes: int = 30
    ):
        self.max_attractions_per_day = max_attractions_per_day
        self.max_restaurants_per_day = max_restaurants_per_day
        self.rest_duration_minutes = rest_duration_minutes

        # 定义约束
        self.constraints = [
            Constraint("opening_hours", self._check_opening_hours, 1.0),
            Constraint("travel_time", self._check_travel_time, 0.8),
            Constraint("budget", self._check_budget, 1.0),
            Constraint("rest_time", self._check_rest_time, 0.5),
        ]

    def optimize(
        self,
        profile: UserProfile,
        attractions: List[Dict[str, Any]],
        restaurants: List[Dict[str, Any]],
        hotels: List[Dict[str, Any]] = None
    ) -> TripPlan:
        """优化生成行程计划"""
        days = profile.duration_days
        budget = profile.budget_total
        rhythm = profile.rhythm_preference

        # 根据节奏调整每天安排
        attractions_per_day = self._get_attractions_per_day(rhythm)

        # 初始化每日计划
        daily_plans = []
        for day in range(1, days + 1):
            day_plan = self._create_day_plan(
                day=day,
                attractions=attractions,
                restaurants=restaurants,
                max_attractions=attractions_per_day,
                rhythm=rhythm
            )
            daily_plans.append(day_plan)

        # 计算预算分配
        budget_summary = self._calculate_budget(
            profile=profile,
            daily_plans=daily_plans,
            hotels=hotels or []
        )

        # 创建行程计划
        trip_plan = TripPlan(
            destination=profile.destination,
            origin=profile.origin,
            duration=f"{days}天{days-1}晚",
            start_date="",  # 后续补充
            end_date="",
            travel_type=profile.travel_type,
            daily_plans=daily_plans,
            budget_summary=budget_summary,
            hotels=hotels or [],
            tips=self._generate_tips(profile, daily_plans)
        )

        return trip_plan

    def _get_attractions_per_day(self, rhythm: str) -> int:
        """根据节奏获取每天景点数量"""
        rhythm_map = {
            "休闲": 2,
            "适中": 3,
            "暴走": 5,
        }
        return rhythm_map.get(rhythm, 3)

    def _create_day_plan(
        self,
        day: int,
        attractions: List[Dict[str, Any]],
        restaurants: List[Dict[str, Any]],
        max_attractions: int,
        rhythm: str
    ) -> DayPlan:
        """创建每日计划"""
        # 随机选择景点
        selected_attractions = random.sample(
            attractions[:min(len(attractions), 20)],
            min(max_attractions, len(attractions))
        )

        # 分配到不同时间段
        time_slots = self._assign_time_slots(
            attractions=selected_attractions,
            restaurants=restaurants,
            rhythm=rhythm
        )

        # 计算当日费用
        total_cost = sum(slot.estimated_cost for slot in time_slots if isinstance(slot, TimeSlot))

        return DayPlan(
            day=day,
            theme=self._get_day_theme(selected_attractions),
            morning=time_slots[0] if len(time_slots) > 0 else None,
            lunch=time_slots[1] if len(time_slots) > 1 else None,
            afternoon=time_slots[2] if len(time_slots) > 2 else None,
            dinner=time_slots[3] if len(time_slots) > 3 else None,
            evening=time_slots[4] if len(time_slots) > 4 else None,
            total_cost=total_cost,
            highlights=self._extract_highlights(selected_attractions)
        )

    def _assign_time_slots(
        self,
        attractions: List[Dict[str, Any]],
        restaurants: List[Dict[str, Any]],
        rhythm: str
    ) -> List[TimeSlot]:
        """分配时间槽"""
        time_slots = []

        # 早上去景点
        if len(attractions) > 0:
            tips_raw = attractions[0].get("tips", ["早点去人少"])
            tips_str = tips_raw[0] if isinstance(tips_raw, list) else str(tips_raw)
            time_slots.append(TimeSlot(
                time_range="09:00-12:00",
                place_name=attractions[0].get("name", "景点"),
                place_type="景点",
                place_id=attractions[0].get("id"),
                address=attractions[0].get("location", ""),
                tips=tips_str,
                estimated_cost=attractions[0].get("ticket_price", 0)
            ))

        # 午餐
        if len(restaurants) > 0:
            restaurant = restaurants[0]
            time_slots.append(TimeSlot(
                time_range="12:00-13:30",
                place_name=restaurant.get("name", "餐厅"),
                place_type="餐厅",
                place_id=restaurant.get("id"),
                tips="尝试招牌菜",
                estimated_cost=restaurant.get("price", 100)
            ))

        # 下午景点
        if len(attractions) > 1:
            tips_raw = attractions[1].get("tips", [])
            tips_str = tips_raw[0] if isinstance(tips_raw, list) and tips_raw else "傍晚去更好看"
            time_slots.append(TimeSlot(
                time_range="14:00-17:00",
                place_name=attractions[1].get("name", "景点"),
                place_type="景点",
                place_id=attractions[1].get("id"),
                address=attractions[1].get("location", ""),
                tips=tips_str,
                estimated_cost=attractions[1].get("ticket_price", 0)
            ))

        # 晚餐
        if len(restaurants) > 1:
            restaurant = restaurants[1]
            time_slots.append(TimeSlot(
                time_range="18:00-20:00",
                place_name=restaurant.get("name", "餐厅"),
                place_type="餐厅",
                place_id=restaurant.get("id"),
                tips="提前预约",
                estimated_cost=restaurant.get("price", 150)
            ))

        # 晚上活动
        if len(attractions) > 2 and rhythm != "暴走":
            time_slots.append(TimeSlot(
                time_range="20:00-22:00",
                place_name=attractions[2].get("name", "夜景"),
                place_type="景点",
                place_id=attractions[2].get("id"),
                tips="夜景很美",
                estimated_cost=0
            ))

        return time_slots

    def _get_day_theme(self, attractions: List[Dict[str, Any]]) -> str:
        """获取当日主题"""
        if not attractions:
            return "自由活动"

        categories = [a.get("category", "") for a in attractions]
        if "购物" in categories:
            return "购物之旅"
        elif "美食" in categories:
            return "美食探索"
        elif "自然" in categories:
            return "自然风光"
        else:
            themes = ["经典打卡", "深度探索", "休闲漫游", "文化体验"]
            return random.choice(themes)

    def _extract_highlights(self, attractions: List[Dict[str, Any]]) -> List[str]:
        """提取亮点"""
        highlights = []
        for a in attractions[:3]:
            if a.get("highlights"):
                highlights.extend(a.get("highlights", [])[:2])
        return list(set(highlights))[:5]

    def _calculate_budget(
        self,
        profile: UserProfile,
        daily_plans: List[DayPlan],
        hotels: List[Dict[str, Any]]
    ) -> BudgetSummary:
        """计算预算分配"""
        total = profile.budget_total
        days = len(daily_plans)

        # 默认分配比例
        allocation = profile.budget_total * 0.3  # 简化计算

        # 住宿
        accommodation_cost = 0
        if hotels:
            accommodation_cost = hotels[0].get("price_per_night", 500) * (days - 1)

        # 餐饮（每天估算）
        food_cost = sum(day.total_cost for day in daily_plans) * 0.4

        # 交通
        transport_cost = total * 0.15

        # 景点门票
        attractions_cost = sum(day.total_cost for day in daily_plans) * 0.3

        # 购物
        shopping_cost = total - accommodation_cost - food_cost - transport_cost - attractions_cost

        return BudgetSummary(
            total=total,
            breakdown={
                "住宿": {"amount": accommodation_cost, "ratio": 0.30},
                "餐饮": {"amount": food_cost, "ratio": 0.25},
                "交通": {"amount": transport_cost, "ratio": 0.15},
                "景点": {"amount": attractions_cost, "ratio": 0.10},
                "购物": {"amount": shopping_cost, "ratio": 0.20},
            },
            estimated_total=total
        )

    def _generate_tips(self, profile: UserProfile, daily_plans: List[DayPlan]) -> List[str]:
        """生成小贴士"""
        tips = []

        # 基于目的地
        destination = profile.destination
        if "东京" in destination:
            tips.append("建议购买JR Pass，可无限次乘坐地铁和新干线")
            tips.append("大部分商场支持支付宝/微信支付")
        elif "大阪" in destination:
            tips.append("道顿堀晚上更热闹，建议晚上去")
            tips.append("环球影城建议提前买快速票")
        elif "京都" in destination:
            tips.append("寺庙大多需要脱鞋进入，请穿方便穿脱的鞋子")
            tips.append("樱花季和红叶季人流量大，提前预订住宿")

        # 基于旅行类型
        if profile.travel_type == "亲子游":
            tips.append("携带儿童推车，很多景点需要步行")
        elif profile.travel_type == "独自旅行":
            tips.append("日本治安很好，但注意保管好贵重物品")

        # 基于预算
        if profile.budget_total < 5000:
            tips.append("善用便利店和自动贩卖机，价格透明")
            tips.append("午餐选择套餐比单点更划算")

        return tips[:5]

    # ========== 约束检查方法 ==========

    def _check_opening_hours(self, attraction: Dict, planned_time: str) -> bool:
        """检查是否在营业时间内"""
        opening_hours = attraction.get("opening_hours", "")
        # 简化检查
        return True

    def _check_travel_time(
        self,
        from_place: Dict,
        to_place: Dict,
        max_minutes: int = 60
    ) -> bool:
        """检查交通时间"""
        # 简化实现，实际应该调用地图API
        return True

    def _check_budget(self, item_cost: float, remaining_budget: float) -> bool:
        """检查预算"""
        return item_cost <= remaining_budget

    def _check_rest_time(
        self,
        previous_activity_end: str,
        next_activity_start: str,
        min_gap_minutes: int = 30
    ) -> bool:
        """检查休息时间"""
        return True
