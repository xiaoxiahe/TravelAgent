"""边/条件函数"""
from typing import Literal

from travel_agent.agent.state import AgentState, Stages


def should_collect_more_info(state: AgentState) -> Literal[
    "ask_travel_type", "ask_duration", "ask_budget", "ask_rhythm",
    "ask_food_preferences", "ask_accommodation", "ask_transport",
    "need_more_info", "confirm_info", "generate_plan"
]:
    """判断是否需要继续收集信息"""
    profile = state.get("user_profile")
    current_stage = state.get("current_stage", 0)

    if profile is None:
        return "welcome"

    # 检查基本信息是否足够
    profile_dict = profile.model_dump()
    required_fields = ["destination", "travel_type", "duration_days", "budget_total"]

    has_required = all(
        profile_dict.get(field) for field in required_fields
    )

    # 如果基本信息足够且已询问过偏好，进入规划阶段
    if has_required and profile.info_stage >= 5:
        return "confirm_info"

    # 否则根据当前阶段继续收集
    stage_to_node = {
        Stages.WELCOME: "welcome",
        Stages.TRAVEL_TYPE: "ask_travel_type",
        Stages.DURATION: "ask_duration",
        Stages.BUDGET: "ask_budget",
        Stages.RHYTHM: "ask_rhythm",
        Stages.FOOD_PREFERENCES: "ask_food_preferences",
        Stages.ACCOMMODATION: "ask_accommodation",
        Stages.TRANSPORT: "ask_transport",
    }

    return stage_to_node.get(current_stage, "confirm_info")


def should_generate_plan(state: AgentState) -> Literal["generate_plan", "need_more_info"]:
    """判断是否开始生成计划"""
    profile = state.get("user_profile")

    if profile and profile.is_info_sufficient():
        return "confirm_info"

    # 可以在这里添加更多判断，如是否需要追问
    return "need_more_info"


def after_question(state: AgentState) -> Literal[
    "update_profile", "ask_travel_type", "ask_duration", "ask_budget",
    "ask_rhythm", "ask_food_preferences", "ask_accommodation", "ask_transport",
    "confirm_info"
]:
    """回答问题后的处理"""
    return "update_profile"


def after_update_profile(state: AgentState) -> str:
    """更新画像后的处理"""
    profile = state["user_profile"]

    # 检查是否还有未收集的必填信息
    if not profile.travel_type:
        return "ask_travel_type"
    if not profile.duration_days:
        return "ask_duration"
    if not profile.budget_total:
        return "ask_budget"

    # 可选信息
    if not profile.rhythm_preference or profile.rhythm_preference == "适中":
        return "ask_rhythm"
    if not profile.food_preferences.cuisine_types:
        return "ask_food_preferences"
    if not profile.accommodation_preference.type:
        return "ask_accommodation"
    if not profile.transport_preference.mode:
        return "ask_transport"

    # 所有信息收集完毕
    return "confirm_info"


def should_revise(state: AgentState) -> Literal["generate_plan", "end"]:
    """判断是否需要修改计划"""
    feedback = state.get("feedback_status")

    if feedback == "unsatisfied":
        return "generate_plan"
    elif feedback == "satisfied":
        return "end"
    else:
        return "end"


def is_welcome(state: AgentState) -> bool:
    """是否在欢迎阶段"""
    return state.get("current_stage") == Stages.WELCOME or state.get("user_profile") is None
