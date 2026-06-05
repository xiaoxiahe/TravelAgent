"""多智能体 Planner。"""
from __future__ import annotations

from typing import Any

from travel_agent.llm_utils import call_chat_llm, safe_json_loads
from travel_agent.models.user_profile import UserProfile
from travel_agent.skills import format_tool_registry_for_prompt

from .state import PlannerOutput, PlanningContext


DEFAULT_REQUIRED_TOOLS = ["poi_search", "weather_lookup", "hotel_search"]


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
    if profile.origin and profile.travel_date and profile.transport_preference.mode in {"飞机", "航班"}:
        required_tools.append("flight_search")
        tool_arguments["flight_search"] = {
            "origin": origin,
            "destination": destination,
            "travel_date": travel_date,
            "trip_type": "ONE_WAY",
            "cabin_grade": "ECONOMY",
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
5. `hotel_search` 要尽量带上住宿偏好或区域线索。
6. 只有在有明确日期时才调用 `calendar_lookup`。
7. 只有在有明确出发地 + 日期 + 飞机意图时才调用 `flight_search`。
8. 如果某工具没必要，可以不调用。
9. 如果信息不足，优先保留最关键的 1-3 个工具。
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
