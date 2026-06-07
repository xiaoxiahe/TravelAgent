"""多智能体 Planner。"""
from __future__ import annotations

import re
from typing import Any

from travel_agent.utils.travel_date import (
    build_calendar_query_dates,
    coerce_future_date,
    infer_travel_date,
    should_query_calendar,
    upcoming_weekday_dates,
)
from travel_agent.llm_utils import call_chat_llm, safe_json_loads
from travel_agent.models.user_profile import UserProfile
from travel_agent.skills import format_tool_registry_for_prompt
from travel_agent.skills.runner import SkillRunner

from .state import PlannerOutput, PlanningContext


DEFAULT_REQUIRED_TOOLS = ["poi_search", "weather_lookup", "hotel_search"]
OVERSEAS_KEYWORDS = (
    "东京", "日本", "大阪", "京都", "横滨", "福冈", "北海道",
    "首尔", "韩国", "釜山", "曼谷", "泰国", "新加坡", "吉隆坡",
    "越南", "河内", "胡志明", "美国", "纽约", "洛杉矶", "英国", "伦敦",
    "法国", "巴黎", "悉尼", "墨尔本", "欧洲",
)


def _is_overseas_destination(destination: str) -> bool:
    dest = (destination or "").strip()
    return any(keyword in dest for keyword in OVERSEAS_KEYWORDS)


def _infer_origin(profile: UserProfile, conversation_summary: str = "") -> str:
    origin = (profile.origin or "").strip()
    if origin:
        return origin
    text = " ".join(part for part in [conversation_summary or "", profile.notes or ""] if part)
    origin_patterns = [
        r"从\s*([^\s，,。到至去]+?)\s*出发",
        r"出发地[是为：:]\s*([^\s，,。]+)",
        r"我在\s*([^\s，,。]+)",
    ]
    for pattern in origin_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return ""


def _should_search_flights(profile: UserProfile, conversation_summary: str = "") -> bool:
    destination = (profile.destination or "").strip()
    origin = _infer_origin(profile, conversation_summary)
    travel_date = infer_travel_date(profile, conversation_summary)
    if not origin or not travel_date or not destination:
        return False

    text = " ".join(
        part for part in [
            conversation_summary or "",
            profile.notes or "",
            profile.transport_preference.mode or "",
            destination,
        ]
        if part
    )
    flight_hints = ("飞机", "航班", "机票", "飞", "航空")
    if any(hint in text for hint in flight_hints):
        return True
    if _is_overseas_destination(destination):
        return True
    return profile.transport_preference.mode in {"飞机", "航班"}


def _coerce_future_date(date_str: str) -> str:
    return coerce_future_date(date_str)


def _postprocess_tool_plan(
    profile: UserProfile,
    required_tools: list[str],
    tool_arguments: dict[str, dict[str, Any]],
    conversation_summary: str = "",
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    destination = (profile.destination or "").strip()
    travel_date = infer_travel_date(profile, conversation_summary)
    if travel_date:
        profile.travel_date = travel_date

    if _is_overseas_destination(destination):
        required_tools = [tool for tool in required_tools if tool not in {"weather_lookup", "poi_search"}]
        tool_arguments = {name: args for name, args in tool_arguments.items() if name in required_tools}

    calendar_dates: list[str] = []
    if travel_date:
        calendar_dates = build_calendar_query_dates(travel_date, conversation_summary)
    elif should_query_calendar(profile, conversation_summary):
        calendar_dates = upcoming_weekday_dates(3)

    if calendar_dates:
        if "calendar_lookup" not in required_tools:
            required_tools.append("calendar_lookup")
        tool_arguments["calendar_lookup"] = {
            "date": calendar_dates[0],
            "dates": calendar_dates,
        }

    if "hotel_search" in tool_arguments:
        hotel_args = tool_arguments["hotel_search"]
        check_in = (
            hotel_args.get("check_in_date")
            or hotel_args.get("travel_date")
            or travel_date
        )
        if check_in:
            check_in = _coerce_future_date(str(check_in))
            hotel_args["check_in_date"] = check_in
            hotel_args["travel_date"] = check_in
        duration = profile.duration_days or 3
        hotel_args["stay_nights"] = max(1, int(duration) - 1)

    origin = _infer_origin(profile, conversation_summary)
    if origin:
        profile.origin = origin
    if _should_search_flights(profile, conversation_summary):
        if "flight_search" not in required_tools:
            required_tools.append("flight_search")
        tool_arguments["flight_search"] = {
            "origin": SkillRunner._normalize_flight_place(origin),
            "destination": SkillRunner._normalize_flight_place(destination),
            "travel_date": travel_date,
            "trip_type": "ONE_WAY",
            "cabin_grade": "ECONOMY",
            "adult_number": 1,
            "child_number": 0,
        }

    return required_tools, tool_arguments


def _duration_text(profile: UserProfile) -> str:
    if profile.duration_days_range:
        return profile.duration_days_range
    if profile.duration_days:
        return f"{profile.duration_days}天"
    return "待定"


def _budget_text(profile: UserProfile) -> str:
    if profile.budget_total:
        return f"¥{profile.budget_total:,.0f}"
    return "待定"


def _traveler_summary(profile: UserProfile) -> str:
    if not profile.companions:
        return "暂未说明同行人"
    first = profile.companions[0]
    return f"{first.count}人同行（{first.relation}）"


def _build_constraints(profile: UserProfile) -> list[str]:
    constraints: list[str] = []

    if profile.travel_type and profile.travel_type != "其他":
        constraints.append(f"旅行类型：{profile.travel_type}")
    if profile.rhythm_preference:
        constraints.append(f"节奏偏好：{profile.rhythm_preference}")
    if profile.food_preferences.cuisine_types:
        constraints.append(f"美食偏好：{'、'.join(profile.food_preferences.cuisine_types)}")
    if profile.accommodation_preference.type:
        constraints.append(f"住宿偏好：{profile.accommodation_preference.type}")
    if profile.accommodation_preference.location:
        constraints.append(f"住宿位置偏好：{profile.accommodation_preference.location}")
    if profile.transport_preference.mode:
        constraints.append(f"交通偏好：{profile.transport_preference.mode}")
    if profile.must_visit:
        constraints.append(f"必去景点：{'、'.join(profile.must_visit)}")
    if profile.avoid_places:
        constraints.append(f"避开地点：{'、'.join(profile.avoid_places)}")
    if profile.travel_date:
        constraints.append(f"出发日期：{profile.travel_date}")
    if profile.notes:
        constraints.append(f"补充说明：{profile.notes}")

    return constraints


def _fallback_tool_plan(profile: UserProfile) -> tuple[list[str], dict[str, dict[str, Any]], str]:
    destination = (profile.destination or "").strip()
    origin = (profile.origin or "").strip()
    travel_date = (profile.travel_date or "").strip()
    accommodation_keyword = (profile.accommodation_preference.type or "酒店").strip() or "酒店"

    required_tools = list(DEFAULT_REQUIRED_TOOLS)
    tool_arguments: dict[str, dict[str, Any]] = {
        "poi_search": {
            "city": destination,
            "keyword": (profile.must_visit[0] if profile.must_visit else f"{destination} 景点").strip(),
        },
        "weather_lookup": {
            "city": destination,
            "travel_date": travel_date,
        },
        "hotel_search": {
            "city": destination,
            "destination": destination,
            "keyword": f"{destination} {accommodation_keyword}".strip(),
            "travel_date": travel_date,
        },
    }

    if profile.travel_date:
        required_tools.append("calendar_lookup")
        tool_arguments["calendar_lookup"] = {"date": travel_date}
    if profile.origin and profile.travel_date and _should_search_flights(profile):
        required_tools.append("flight_search")
        tool_arguments["flight_search"] = {
            "origin": SkillRunner._normalize_flight_place(origin),
            "destination": SkillRunner._normalize_flight_place(destination),
            "travel_date": travel_date,
            "trip_type": "ONE_WAY",
            "cabin_grade": "ECONOMY",
            "adult_number": 1,
            "child_number": 0,
        }

    reasoning = "LLM 查询规划失败，回退到默认工具策略：优先查询 POI、天气、酒店，必要时补充黄历与航班。"
    return required_tools, tool_arguments, reasoning


def _normalize_planner_payload(payload: Any, profile: UserProfile) -> tuple[list[str], dict[str, dict[str, Any]], str]:
    fallback_tools, fallback_args, fallback_reasoning = _fallback_tool_plan(profile)
    if not isinstance(payload, dict):
        return fallback_tools, fallback_args, fallback_reasoning

    requested_tools = payload.get("required_tools")
    requested_args = payload.get("tool_arguments")
    reasoning = str(payload.get("reasoning") or "").strip() or fallback_reasoning

    if not isinstance(requested_tools, list):
        requested_tools = fallback_tools

    valid_tools: list[str] = []
    for item in requested_tools:
        tool_name = str(item).strip()
        if tool_name and tool_name not in valid_tools:
            valid_tools.append(tool_name)
    if not valid_tools:
        valid_tools = fallback_tools

    normalized_args: dict[str, dict[str, Any]] = {}
    requested_args = requested_args if isinstance(requested_args, dict) else {}
    for tool_name in valid_tools:
        tool_payload = requested_args.get(tool_name)
        if isinstance(tool_payload, dict):
            normalized_args[tool_name] = {str(k): v for k, v in tool_payload.items()}
        else:
            normalized_args[tool_name] = fallback_args.get(tool_name, {})

    for tool_name in valid_tools:
        if not normalized_args.get(tool_name):
            normalized_args[tool_name] = fallback_args.get(tool_name, {})

    return valid_tools, normalized_args, reasoning


def _build_llm_tool_plan(context: PlanningContext, constraints: list[str]) -> tuple[list[str], dict[str, dict[str, Any]], str]:
    profile = context.profile
    destination = (profile.destination or "").strip()
    user_profile_str = f"""目的地: {destination or '未指定'}
出发地: {profile.origin or '未指定'}
出发日期: {profile.travel_date or '未指定'}
天数: {_duration_text(profile)}
预算: {_budget_text(profile)}
旅行类型: {profile.travel_type or '未指定'}
节奏偏好: {profile.rhythm_preference or '未指定'}
交通偏好: {profile.transport_preference.mode or '未指定'}
住宿偏好: {profile.accommodation_preference.type or '未指定'}
住宿位置偏好: {profile.accommodation_preference.location or '未指定'}
必去景点: {','.join(profile.must_visit) or '无'}
避开地点: {','.join(profile.avoid_places) or '无'}
补充说明: {profile.notes or '无'}"""

    prompt = f"""你是旅行规划查询调度器。你的任务不是直接写最终行程，而是先根据用户需求，规划‘为了生成更精细行程，应该调用哪些 skill，以及每个 skill 用什么参数’。

可用工具：
{format_tool_registry_for_prompt()}

用户画像：
{user_profile_str}

对话摘要：
{context.conversation_summary or '无'}

本地知识摘要：
{context.rag_summary or '无'}

已知约束：
{chr(10).join(f'- {item}' for item in constraints) or '- 无'}

请输出 JSON，结构必须严格如下：
{{
  "reasoning": "一句话说明为什么这样查",
  "required_tools": ["tool_name1", "tool_name2"],
  "tool_arguments": {{
    "tool_name1": {{"param": "value"}},
    "tool_name2": {{"param": "value"}}
  }}
}}

规则：
1. 只返回 JSON，不要解释。
2. 必须先考虑用户需求的精细程度，再决定是否调用工具，不要无脑全调。
3. 如果用户目的地过于宽泛（如国家），应把查询参数细化到更适合搜索的城市/片区，但最终仍服务于原始需求。
4. `poi_search` 关键词要尽量具体，例如“首尔 明洞 景点”或“首尔 亲子 景点”，不要只写“韩国景点”。
5. `hotel_search` 要尽量带上住宿偏好或区域线索；境外目的地需使用英文城市名（如 Tokyo）并填写未来入住日期。
6. 用户给出具体日期、或“X月初”这类时间范围时，必须调用 `calendar_lookup`，日期用 YYYY-MM-DD。
7. 境外目的地（如日本/东京）不要调用 `weather_lookup` 和 `poi_search`（高德仅覆盖中国境内）。
8. 境外目的地或有明确飞机/机票意图，且已知出发地 + 出发日期时，应调用 `flight_search`；出发地优先用 profile.origin，没有则从对话中推断。
9. `flight_search` 的 origin/destination 填中文城市名即可（如「东京」，不要写「日本东京」），系统会自动解析机场代码。
10. 如果某工具没必要，可以不调用。
11. 如果信息不足，优先保留最关键的 1-3 个工具。
"""

    response = call_chat_llm(
        system_prompt="你是旅行规划查询调度器，只输出 JSON。",
        user_prompt=prompt,
        max_tokens=1200,
        temperature=0.1,
    )
    payload = safe_json_loads(response)
    return _normalize_planner_payload(payload, profile)


def build_planning_brief(context: PlanningContext) -> PlannerOutput:
    profile = context.profile
    constraints = _build_constraints(profile)
    required_tools, tool_arguments, reasoning = _build_llm_tool_plan(context, constraints)
    required_tools, tool_arguments = _postprocess_tool_plan(
        profile,
        required_tools,
        tool_arguments,
        context.conversation_summary or "",
    )

    return PlannerOutput(
        destination=profile.destination,
        duration_text=_duration_text(profile),
        budget_text=_budget_text(profile),
        traveler_summary=_traveler_summary(profile),
        constraints=constraints,
        required_tools=required_tools,
        tool_arguments=tool_arguments,
        reasoning=reasoning,
    )
