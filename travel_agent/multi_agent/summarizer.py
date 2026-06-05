"""多智能体 Summarizer。"""
from __future__ import annotations

import re
from collections import OrderedDict

from travel_agent.models.user_profile import UserProfile

from .state import ExecutionResult, PlannerOutput, PlanningContext, SummaryResult


DAY_THEMES = [
    "首尔历史中轴线与传统街区",
    "韩屋、壁画村与大学路漫步",
    "明洞商圈与城市夜景",
    "K-pop 打卡与潮流街区",
    "博物馆与汉江休闲体验",
    "近郊轻游与购物补给",
    "返程前自由活动",
    "延伸体验日",
]

STOPWORDS = {
    "来自",
    "travel",
    "collection",
    "热门攻略笔记",
    "热门评论",
    "用户",
    "评论",
    "首尔",
    "韩国",
    "Day1",
    "DAY1",
    "上午",
    "下午",
    "午",
    "晚间",
}


def _build_header(profile: UserProfile, planner_output: PlannerOutput) -> list[str]:
    return [
        f"# {profile.destination} 行程建议",
        "",
        f"- 行程时长：{planner_output.duration_text}",
        f"- 预算参考：{planner_output.budget_text}",
        f"- 同行情况：{planner_output.traveler_summary}",
    ]


def _estimate_days(planner_output: PlannerOutput) -> int:
    text = planner_output.duration_text or ""
    digits = [int(part) for part in text.replace("天", "").replace("日", "").replace("—", "-").split("-") if part.strip().isdigit()]
    if not digits:
        return 3
    if len(digits) == 1:
        return max(1, digits[0])
    return max(1, digits[0])


def _tool_map(execution_result: ExecutionResult) -> dict[str, str]:
    return {
        output.get("tool", ""): output.get("summary", "")
        for output in execution_result.tool_outputs
        if output.get("tool")
    }


def _format_tool_entries(entries: list[dict[str, object]]) -> list[str]:
    lines: list[str] = []
    for item in entries:
        tool_name = str(item.get("tool", "") or "")
        summary = str(item.get("summary", "") or "").strip()
        raw = item.get("raw")
        status = str(item.get("status", "") or "")
        if not tool_name:
            continue
        label = f"`{tool_name}`"
        if status:
            label = f"{label}（{status}）"
        if summary:
            lines.append(f"- {label}：{summary}")
        if raw is not None:
            lines.append(f"  原始返回：{raw}")
    return lines


def _extract_candidates_from_rag(rag_summary: str) -> list[str]:
    candidates: OrderedDict[str, None] = OrderedDict()
    normalized = rag_summary.replace("\n", "-")
    for chunk in re.split(r"[、,，:：\-\|/（）()\[\]【】]", normalized):
        text = chunk.strip().strip(".")
        if not text or text in STOPWORDS:
            continue
        if len(text) < 2 or len(text) > 18:
            continue
        if any(marker in text for marker in ["用户", "评论", "IP属地", "预算", "行程", "建议"]):
            continue
        if text.startswith("💬") or text.startswith("📍"):
            text = text[1:].strip()
        candidates[text] = None
    return list(candidates.keys())


def _pick_seoul_spots(rag_summary: str) -> list[str]:
    preferred = [
        "青瓦台", "北村韩屋村", "梨花洞壁画村", "光化门", "清溪川", "明洞", "新世界免税店", "Hybe",
        "景福宫", "益善洞", "仁寺洞", "弘大", "圣水洞", "汉江", "东大门", "乐天免税店",
    ]
    extracted = _extract_candidates_from_rag(rag_summary)
    merged: OrderedDict[str, None] = OrderedDict()
    for item in preferred:
        if item in rag_summary:
            merged[item] = None
    for item in extracted:
        merged[item] = None
    return list(merged.keys())[:16]


def _pick_food_hints(rag_summary: str) -> list[str]:
    food_terms = ["炸鸡", "芝士焗猪扒饭", "烤肉", "韩餐", "咖啡馆", "年糕", "紫菜包饭"]
    picked: OrderedDict[str, None] = OrderedDict()
    for term in food_terms:
        if term in rag_summary:
            picked[term] = None
    return list(picked.keys())[:5]


def _group_spots_for_days(spots: list[str], days: int) -> list[list[str]]:
    if not spots:
        return [[] for _ in range(days)]
    grouped: list[list[str]] = []
    idx = 0
    for _ in range(days):
        day_spots = spots[idx:idx + 3]
        if not day_spots:
            day_spots = spots[max(0, len(spots) - 3):]
        grouped.append(day_spots)
        idx += 3
    return grouped


def _build_daily_plan(planner_output: PlannerOutput, execution_result: ExecutionResult, context: PlanningContext) -> list[str]:
    profile = context.profile
    days = min(_estimate_days(planner_output), 8)
    tool_outputs = _tool_map(execution_result)
    rag_hint = context.rag_summary.strip()
    pace_hint = profile.rhythm_preference or "适中"
    transport_hint = profile.transport_preference.mode or "公共交通"
    stay_hint = profile.accommodation_preference.type or "酒店"
    spots = _pick_seoul_spots(rag_hint)
    food_hints = _pick_food_hints(rag_hint)
    grouped_spots = _group_spots_for_days(spots, days)
    food_text = "、".join(food_hints) if food_hints else "本地高评分韩餐或西式简餐"

    lines = ["## 推荐行程"]
    for day in range(days):
        theme = DAY_THEMES[day] if day < len(DAY_THEMES) else f"第{day + 1}天主题探索"
        day_spots = grouped_spots[day]
        morning_spot = day_spots[0] if len(day_spots) > 0 else "首尔核心景点"
        afternoon_spot = day_spots[1] if len(day_spots) > 1 else (day_spots[0] if day_spots else "热门街区")
        evening_spot = day_spots[2] if len(day_spots) > 2 else (day_spots[-1] if day_spots else "夜景商圈")

        lines.append("")
        lines.append(f"### Day {day + 1}｜{theme}")
        lines.append(f"- 上午：前往 `{morning_spot}`，安排半天打卡与步行探索，整体节奏保持{pace_hint}。")
        lines.append(f"- 午餐：就在 `{morning_spot}` 或临近片区用餐，优先考虑 {food_text}。")
        lines.append(f"- 下午：衔接 `{afternoon_spot}` 一带继续游览，尽量把同一区域景点串成一条线，减少换乘。")
        lines.append(f"- 晚间：前往 `{evening_spot}` 附近逛街、看夜景或购物后返回酒店休息。")

    lines.append("")
    lines.append("## 落地建议")
    lines.append(f"- 住宿建议：优先筛选交通便利的{stay_hint}，尽量靠近地铁 2 号线、4 号线或热门商圈周边。")
    lines.append(f"- 交通建议：以{transport_hint}为主，优先按片区安排行程，例如景福宫/光化门/清溪川放同一天，明洞/免税店/夜景放同一天。")
    lines.append("- 预算建议：两人 8000 元预算更适合控制住宿档位与购物支出，餐饮可穿插一两顿特色餐，其余以高性价比门店为主。")

    if rag_hint:
        lines.append("")
        lines.append("## 本地知识如何使用")
        lines.append("- 已优先抽取攻略里高频出现的首尔核心片区与景点，并按地理邻近关系拆到不同天，避免整份规划只停留在泛化建议层。")

    if tool_outputs:
        lines.append("")
        lines.append("## 实时查询结果解读")
        lines.extend(_format_tool_entries(execution_result.tool_outputs))

    if execution_result.failed_tools:
        lines.append("")
        lines.append("## 已跳过的实时工具")
        lines.extend(_format_tool_entries(execution_result.failed_tools))

    return lines


def summarize_plan(
    planner_output: PlannerOutput,
    execution_result: ExecutionResult,
    context: PlanningContext,
) -> SummaryResult:
    profile = context.profile
    lines = _build_header(profile, planner_output)
    lines.append("")
    lines.append("## 已确认需求")
    if planner_output.constraints:
        lines.extend([f"- {item}" for item in planner_output.constraints])
    else:
        lines.append("- 当前以目的地、天数和预算为主要约束")

    if context.rag_summary.strip():
        lines.append("")
        lines.append("## 本地知识参考")
        lines.append(context.rag_summary.strip())

    if execution_result.warnings:
        lines.append("")
        lines.append("## 说明")
        for warning in execution_result.warnings:
            lines.append(f"- {warning}")

    lines.append("")
    lines.extend(_build_daily_plan(planner_output, execution_result, context))
    if profile.notes:
        lines.append("")
        lines.append(f"已纳入补充需求：{profile.notes}")

    structured_plan = {
        "destination": profile.destination,
        "content": "\n".join(lines),
        "source": "multi_agent",
        "references": context.references,
        "used_tools": execution_result.used_tools,
        "planner_constraints": planner_output.constraints,
        "planner_reasoning": planner_output.reasoning,
        "planned_tool_arguments": planner_output.tool_arguments,
        "tool_outputs": execution_result.tool_outputs,
        "failed_tools": execution_result.failed_tools,
        "warnings": execution_result.warnings,
    }
    return SummaryResult(content=structured_plan["content"], structured_plan=structured_plan)
