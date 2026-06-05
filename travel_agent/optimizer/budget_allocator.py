"""预算分配模块"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from travel_agent.models.user_profile import UserProfile, BudgetBreakdown


@dataclass
class BudgetAllocation:
    """预算分配"""
    category: str
    amount: float
    ratio: float
    items: List[Dict[str, Any]]


class BudgetAllocator:
    """预算分配器"""

    # 默认分配比例（可调整）
    DEFAULT_ALLOCATION = {
        "accommodation": 0.30,  # 住宿 30%
        "food": 0.25,           # 餐饮 25%
        "transport": 0.15,      # 交通 15%
        "attractions": 0.10,    # 景点 10%
        "shopping": 0.15,      # 购物 15%
        "other": 0.05,         # 其他 5%
    }

    # 旅行类型对应的分配调整
    TRAVEL_TYPE_ADJUSTMENTS = {
        "蜜月旅行": {
            "accommodation": 0.35,
            "food": 0.30,
            "shopping": 0.10,
        },
        "家庭出游": {
            "accommodation": 0.35,
            "food": 0.25,
            "attractions": 0.15,
        },
        "独自旅行": {
            "accommodation": 0.20,
            "food": 0.30,
            "shopping": 0.10,
        },
        "朋友团建": {
            "food": 0.35,
            "transport": 0.20,
            "shopping": 0.10,
        },
        "商务旅行": {
            "accommodation": 0.35,
            "transport": 0.20,
            "food": 0.20,
        },
        "亲子游": {
            "accommodation": 0.30,
            "attractions": 0.20,
            "food": 0.25,
        },
    }

    def __init__(self):
        self.allocation = self.DEFAULT_ALLOCATION.copy()

    def allocate(
        self,
        profile: UserProfile,
        daily_plan_costs: List[float] = None
    ) -> Dict[str, BudgetAllocation]:
        """
        分配预算

        Args:
            profile: 用户画像
            daily_plan_costs: 每日计划费用

        Returns:
            分配结果
        """
        total = profile.budget_total
        days = profile.duration_days

        # 获取基础分配比例
        allocation = self.allocation.copy()

        # 根据旅行类型调整
        if profile.travel_type in self.TRAVEL_TYPE_ADJUSTMENTS:
            adjustments = self.TRAVEL_TYPE_ADJUSTMENTS[profile.travel_type]
            for category, ratio in adjustments.items():
                allocation[category] = ratio

        # 重新归一化
        total_ratio = sum(allocation.values())
        for category in allocation:
            allocation[category] /= total_ratio

        # 计算金额
        result = {}
        for category, ratio in allocation.items():
            result[category] = BudgetAllocation(
                category=category,
                amount=total * ratio,
                ratio=ratio,
                items=[]
            )

        # 分配每日费用
        if daily_plan_costs:
            total_daily = sum(daily_plan_costs)
            if total_daily > 0:
                for i, cost in enumerate(daily_plan_costs):
                    result["attractions"].items.append({
                        "day": i + 1,
                        "amount": cost
                    })

        return result

    def adjust_allocation(
        self,
        current_allocation: Dict[str, BudgetAllocation],
        category: str,
        new_amount: float
    ) -> Dict[str, BudgetAllocation]:
        """
        调整某个类别的预算

        其他类别会相应减少
        """
        result = {k: v for k, v in current_allocation.items()}

        old_amount = result[category].amount
        diff = new_amount - old_amount

        if diff == 0:
            return result

        # 计算需要调整的其他类别
        other_categories = [k for k in result.keys() if k != category]
        if not other_categories:
            return result

        # 按比例分配差额
        total_other = sum(result[c].amount for c in other_categories)

        for cat in other_categories:
            ratio = result[cat].amount / total_other if total_other > 0 else 0
            adjustment = diff * ratio

            result[cat] = BudgetAllocation(
                category=cat,
                amount=result[cat].amount - adjustment,
                ratio=result[cat].ratio,
                items=result[cat].items
            )

        # 更新调整的类别
        result[category] = BudgetAllocation(
            category=category,
            amount=new_amount,
            ratio=result[category].ratio,
            items=result[category].items
        )

        return result

    def calculate_daily_budget(
        self,
        allocation: Dict[str, BudgetAllocation],
        days: int
    ) -> Dict[str, float]:
        """
        计算每日预算

        Returns:
            每日各类别的预算
        """
        daily = {}
        for category, alloc in allocation.items():
            daily[category] = alloc.amount / days

        return daily

    def estimate_cost(
        self,
        category: str,
        destination: str,
        days: int,
        quality: str = "适中"
    ) -> float:
        """
        估算某类别的费用

        Args:
            category: 类别
            destination: 目的地
            days: 天数
            quality: 质量等级

        Returns:
            估算费用
        """
        # 目的地系数
        dest_multiplier = {
            "东京": 1.3,
            "大阪": 1.1,
            "京都": 1.0,
            "北海道": 1.2,
            "冲绳": 1.1,
        }.get(destination, 1.0)

        # 质量系数
        quality_multiplier = {
            "经济实惠": 0.7,
            "适中": 1.0,
            "高端": 1.5,
            "奢华": 2.0,
        }.get(quality, 1.0)

        # 基础费用
        base_costs = {
            "accommodation": 500,    # 每晚
            "food": 200,             # 每天
            "transport": 100,        # 每天
            "attractions": 150,     # 每天
            "shopping": 300,        # 总计
            "other": 50,            # 每天
        }

        base = base_costs.get(category, 100)

        if category == "accommodation":
            days -= 1  # 住宿晚数比天数少1

        return base * days * dest_multiplier * quality_multiplier

    def check_budget_feasibility(
        self,
        planned_costs: Dict[str, float],
        budget: float
    ) -> Dict[str, Any]:
        """
        检查预算可行性

        Returns:
            检查结果
        """
        total_planned = sum(planned_costs.values())
        remaining = budget - total_planned

        return {
            "is_feasible": total_planned <= budget,
            "total_planned": total_planned,
            "budget": budget,
            "remaining": remaining,
            "overspend": max(0, total_planned - budget),
            "status": "ok" if remaining >= 0 else "over_budget",
            "suggestions": self._get_suggestions(remaining, planned_costs)
        }

    def _get_suggestions(
        self,
        remaining: float,
        planned_costs: Dict[str, float]
    ) -> List[str]:
        """获取节省建议"""
        suggestions = []

        if remaining >= 0:
            return suggestions

        overspend = -remaining

        if planned_costs.get("accommodation", 0) > 1000:
            suggestions.append("考虑选择稍偏一些的住宿，性价比更高")

        if planned_costs.get("food", 0) > 500:
            suggestions.append("午餐可以选择套餐或定食，价格更实惠")

        if planned_costs.get("shopping", 0) > 500:
            suggestions.append("购物可以留到机场免税店，更划算")

        suggestions.append("善用信用卡返现和优惠券")

        return suggestions


def create_budget_report(
    allocation: Dict[str, BudgetAllocation],
    daily_costs: Dict[str, float] = None
) -> str:
    """生成预算报告文本"""
    lines = ["## 预算分配报告", ""]

    for category, alloc in allocation.items():
        category_name = {
            "accommodation": "住宿",
            "food": "餐饮",
            "transport": "交通",
            "attractions": "景点",
            "shopping": "购物",
            "other": "其他",
        }.get(category, category)

        lines.append(f"**{category_name}**: ¥{alloc.amount:,.0f} ({alloc.ratio:.0%})")

    if daily_costs:
        lines.append("")
        lines.append("### 每日预算")
        for category, daily in daily_costs.items():
            lines.append(f"- {category}: ¥{daily:,.0f}")

    return "\n".join(lines)
