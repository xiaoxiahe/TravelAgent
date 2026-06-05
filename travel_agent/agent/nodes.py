"""LangGraph节点函数"""
import json
from typing import Dict, Any, List
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from travel_agent.agent.state import AgentState, Message, Stages
from travel_agent.models.user_profile import UserProfile, FoodPreferences, AccommodationPreferences, TransportPreferences


def welcome_node(state: AgentState) -> AgentState:
    """欢迎节点 - 处理用户初始输入"""
    # 获取用户输入的目的地
    last_message = state["messages"][-1].content if state["messages"] else ""

    # 创建用户画像
    profile = UserProfile(destination=last_message.strip())

    welcome_text = (
        f"好的！让我来帮您规划【{profile.destination}】的旅行！\n\n"
        f"为了给您更好的推荐，我会问您几个问题来了解您的需求。\n\n"
        f"**第一个问题：**"
    )

    state["user_profile"] = profile
    state["current_stage"] = Stages.TRAVEL_TYPE
    state["messages"].append(Message(
        role="assistant",
        content=welcome_text,
        is_question=True
    ))

    return state


def ask_travel_type_node(state: AgentState) -> AgentState:
    """询问旅行类型"""
    profile = state["user_profile"]

    question = "这次旅行的性质是什么？"
    options = [
        {"value": "蜜月旅行", "emoji": "💕", "desc": "浪漫二人世界"},
        {"value": "家庭出游", "emoji": "👨‍👩‍👧", "desc": "带上家人一起"},
        {"value": "独自旅行", "emoji": "🎒", "desc": "一个人的冒险"},
        {"value": "朋友团建", "emoji": "👥", "desc": "和朋友一起浪"},
        {"value": "商务旅行", "emoji": "💼", "desc": "出差顺便玩"},
        {"value": "亲子游", "emoji": "🧒", "desc": "带孩子出行"},
        {"value": "毕业旅行", "emoji": "🎓", "desc": "青春不留白"},
        {"value": "其他", "emoji": "✏️", "desc": "自定义"},
    ]

    state["messages"].append(Message(
        role="assistant",
        content=question,
        options=options,
        is_question=True
    ))
    state["current_stage"] = Stages.TRAVEL_TYPE

    return state


def ask_duration_node(state: AgentState) -> AgentState:
    """询问行程天数"""
    profile = state["user_profile"]

    question = f"您计划在【{profile.destination}】玩几天呢？"
    options = [
        {"value": "1", "desc": "1天 - 当天往返/周末游"},
        {"value": "2-3", "desc": "2-3天 - 短途旅行"},
        {"value": "4-5", "desc": "4-5天 - 深度游"},
        {"value": "6-7", "desc": "6-7天 - 经典线路"},
        {"value": "7+", "desc": "7天以上 - 深度探索"},
    ]

    state["messages"].append(Message(
        role="assistant",
        content=question,
        options=options,
        is_question=True
    ))
    state["current_stage"] = Stages.DURATION

    return state


def ask_budget_node(state: AgentState) -> AgentState:
    """询问预算"""
    profile = state["user_profile"]
    travel_type = profile.travel_type

    question = f"您的【{travel_type}】总预算是多少？（人民币）"
    options = [
        {"value": "3000", "desc": "¥3000以下 - 经济实惠型"},
        {"value": "5000", "desc": "¥3000-5000 - 性价比之选"},
        {"value": "10000", "desc": "¥5000-10000 - 舒适体验"},
        {"value": "20000", "desc": "¥10000-20000 - 高端享受"},
        {"value": "20000+", "desc": "¥20000以上 - 奢华之旅"},
    ]

    state["messages"].append(Message(
        role="assistant",
        content=question,
        options=options,
        is_question=True
    ))
    state["current_stage"] = Stages.BUDGET

    return state


def ask_rhythm_node(state: AgentState) -> AgentState:
    """询问旅行节奏"""
    question = "您喜欢什么样的旅行节奏？"
    options = [
        {"value": "休闲", "emoji": "🧘", "desc": "轻松愉快，不赶时间，睡到自然醒"},
        {"value": "适中", "emoji": "🚶", "desc": "合理安排，有玩有休息"},
        {"value": "暴走", "emoji": "🏃", "desc": "高效打卡，最大化行程"},
    ]

    state["messages"].append(Message(
        role="assistant",
        content=question,
        options=options,
        is_question=True
    ))
    state["current_stage"] = Stages.RHYTHM

    return state


def ask_food_preferences_node(state: AgentState) -> AgentState:
    """询问口味偏好"""
    question = "您对美食有什么偏好吗？"
    options = [
        {"value": "日料", "emoji": "🍣", "desc": "寿司、刺身、拉面"},
        {"value": "中餐", "emoji": "🥢", "desc": "中华料理"},
        {"value": "西餐", "emoji": "🥩", "desc": "牛排、意面"},
        {"value": "当地特色", "emoji": "🏮", "desc": "必吃当地美食"},
        {"value": "不挑", "emoji": "🍽️", "desc": "什么都吃"},
        {"value": "其他", "emoji": "✏️", "desc": "自定义"},
    ]

    state["messages"].append(Message(
        role="assistant",
        content=question,
        options=options,
        is_question=True
    ))
    state["current_stage"] = Stages.FOOD_PREFERENCES

    return state


def ask_accommodation_node(state: AgentState) -> AgentState:
    """询问住宿偏好"""
    question = "您希望住什么样的地方？"
    options = [
        {"value": "豪华酒店", "emoji": "🏨", "desc": "五星/度假村"},
        {"value": "商务酒店", "emoji": "🏨", "desc": "舒适便利"},
        {"value": "民宿", "emoji": "🏠", "desc": "有特色当地风情"},
        {"value": "青旅", "emoji": "🛏️", "desc": "经济实惠"},
        {"value": "公寓", "emoji": "🏢", "desc": "适合长住"},
        {"value": "其他", "emoji": "✏️", "desc": "自定义"},
    ]

    state["messages"].append(Message(
        role="assistant",
        content=question,
        options=options,
        is_question=True
    ))
    state["current_stage"] = Stages.ACCOMMODATION

    return state


def ask_transport_node(state: AgentState) -> AgentState:
    """询问交通偏好"""
    question = "您prefer什么交通方式？"
    options = [
        {"value": "公共交通", "emoji": "🚇", "desc": "地铁、公交"},
        {"value": "JR Pass", "emoji": "🚃", "desc": "铁路周游券"},
        {"value": "包车", "emoji": "🚗", "desc": "专车接送"},
        {"value": "自驾", "emoji": "🚙", "desc": "租车自驾"},
        {"value": "步行", "emoji": "🚶", "desc": "暴走模式"},
    ]

    state["messages"].append(Message(
        role="assistant",
        content=question,
        options=options,
        is_question=True
    ))
    state["current_stage"] = Stages.TRANSPORT

    return state


def confirm_info_node(state: AgentState) -> AgentState:
    """确认信息节点"""
    profile = state["user_profile"]

    # 汇总收集的信息
    summary = (
        f"好的，让我确认一下您的需求：\n\n"
        f"📍 **目的地：** {profile.destination}\n"
        f"🎯 **旅行类型：** {profile.travel_type}\n"
        f"📅 **天数：** {profile.duration_days}天\n"
        f"💰 **预算：** ¥{profile.budget_total:,.0f}\n"
        f"⚡ **节奏：** {profile.rhythm_preference}\n"
        f"🍽️ **口味：** {', '.join(profile.food_preferences.cuisine_types) if profile.food_preferences.cuisine_types else '不挑'}\n"
        f"🏨 **住宿：** {profile.accommodation_preference.type}\n"
        f"🚇 **交通：** {profile.transport_preference.mode}\n\n"
        f"信息收集完毕，我现在为您生成旅行规划..."
    )

    state["messages"].append(Message(
        role="assistant",
        content=summary,
        is_question=False
    ))
    state["current_stage"] = Stages.PLANNING

    return state


def need_more_info_node(state: AgentState) -> AgentState:
    """需要更多信息节点"""
    profile = state["user_profile"]

    question = "我还需要了解一些信息："
    options = [
        {"value": "companions", "desc": "同行人信息"},
        {"value": "must_visit", "desc": "必去景点"},
        {"value": "avoid", "desc": "不想去的地方"},
        {"value": "dietary", "desc": "饮食禁忌"},
    ]

    state["messages"].append(Message(
        role="assistant",
        content=question,
        options=options,
        is_question=True
    ))

    return state


def update_profile_node(state: AgentState) -> AgentState:
    """更新用户画像"""
    profile = state["user_profile"]
    answers = state["answers"]
    current_stage = state["current_stage"]

    # 根据当前阶段更新对应字段
    if current_stage == Stages.TRAVEL_TYPE and "travel_type" in answers:
        profile.travel_type = answers["travel_type"]
        profile.info_stage = 1

    elif current_stage == Stages.DURATION and "duration" in answers:
        duration_map = {"1": 1, "2-3": 2, "4-5": 4, "6-7": 6, "7+": 7}
        profile.duration_days = duration_map.get(answers["duration"], 3)
        profile.info_stage = 2

    elif current_stage == Stages.BUDGET and "budget" in answers:
        budget_map = {
            "3000": 2500, "5000": 4000, "10000": 7500,
            "20000": 15000, "20000+": 25000
        }
        profile.budget_total = budget_map.get(answers["budget"], 5000)
        profile.info_stage = 3

    elif current_stage == Stages.RHYTHM and "rhythm" in answers:
        profile.rhythm_preference = answers["rhythm"]
        profile.info_stage = 4

    elif current_stage == Stages.FOOD_PREFERENCES and "food" in answers:
        profile.food_preferences = FoodPreferences(cuisine_types=[answers["food"]])
        profile.info_stage = 5

    elif current_stage == Stages.ACCOMMODATION and "accommodation" in answers:
        profile.accommodation_preference = AccommodationPreferences(type=answers["accommodation"])
        profile.info_stage = 6

    elif current_stage == Stages.TRANSPORT and "transport" in answers:
        profile.transport_preference = TransportPreferences(mode=answers["transport"])
        profile.info_stage = 7

    # 检查信息是否足够
    profile_dict = profile.model_dump()
    required_fields = ["destination", "travel_type", "duration_days", "budget_total"]
    state["info_sufficient"] = all(
        profile_dict.get(field) for field in required_fields
    ) and profile.info_stage >= 5

    state["user_profile"] = profile

    return state


def get_next_question(state: AgentState) -> str:
    """根据当前阶段获取下一个问题"""
    profile = state["user_profile"]
    current_stage = state["current_stage"]

    if profile.info_stage < current_stage:
        return "ask_more"

    # 根据当前阶段返回下一个节点
    stage_map = {
        Stages.WELCOME: "welcome",
        Stages.TRAVEL_TYPE: "ask_travel_type",
        Stages.DURATION: "ask_duration",
        Stages.BUDGET: "ask_budget",
        Stages.RHYTHM: "ask_rhythm",
        Stages.FOOD_PREFERENCES: "ask_food_preferences",
        Stages.ACCOMMODATION: "ask_accommodation",
        Stages.TRANSPORT: "ask_transport",
    }

    # 如果当前阶段已完成，返回下一个阶段的问题
    if profile.info_stage >= current_stage:
        next_stage = current_stage + 1
        if next_stage in stage_map:
            return stage_map[next_stage]

    return "confirm_info"
