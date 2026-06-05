"""Flask应用主文件"""
from __future__ import annotations

import json
import os
import re
import traceback
import uuid
from datetime import datetime

import requests
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

from travel_agent.agent.config import LLMConfig, config as agent_config
from travel_agent.agent.prompts import NEEDS_ASSESSMENT_SYSTEM_PROMPT, NEEDS_ASSESSMENT_USER_PROMPT
from travel_agent.agent.state import AgentState, Message, Stages
from travel_agent.llm_utils import call_chat_llm, safe_json_loads
from travel_agent.skills import SkillRunner, format_tool_registry_for_prompt
from travel_agent.models.user_profile import UserProfile
from travel_agent.multi_agent import MultiAgentCoordinator, PlanningContext
from travel_agent.session_store import ChatSessionStore

ACCOMMODATION_MAP = {
    "经济型": "青旅",
    "舒适型": "酒店",
    "高档型": "豪华酒店",
    "民宿": "民宿",
    "公寓": "公寓",
    "豪华型": "豪华酒店",
    "酒店": "酒店",
}

_CRAWLER_DATA_CACHE = None  # 懒加载爬虫数据缓存


# ============================================================
# 辅助函数
# ============================================================
def _parse_answer(profile: UserProfile, text: str):
    """智能解析用户回答，更新 profile"""
    text = text.strip()
    if not text or text == "其他":
        return

    # 优先：解析 "X-Y天" 或 "X天" 模式（必须在天数位置，不能是预算数字）
    days_range_pattern = re.search(r"(\d+)\s*[-~至到]\s*(\d+)\s*[天日]", text)
    if days_range_pattern:
        lo, hi = int(days_range_pattern.group(1)), int(days_range_pattern.group(2))
        profile.duration_days_range = f"{lo}-{hi}天"
        profile.duration_days = (lo + hi) // 2  # 取中间值作为规划参考
    else:
        days_pattern = re.search(r"(\d+)\s*[-~到至]?\s*(\d+)?\s*[天日]|[天日]\s*(\d+)\s*[-~到至]?\s*(\d+)?", text)
        if days_pattern:
            if days_pattern.group(1):
                profile.duration_days = int(days_pattern.group(1))
            elif days_pattern.group(3):
                profile.duration_days = int(days_pattern.group(3))
        elif re.search(r"\d+[天日]", text):
            m = re.search(r"(\d+)[天日]", text)
            if m:
                profile.duration_days = int(m.group(1))

    # 预算必须有明确前缀 "预算" / "¥" / "元"，避免误匹配选项文本中的数字
    explicit_budget = re.search(r"预算\s*[内左右约]?\s*(\d+)|(\d+)\s*[千萬万]?\s*元|[¥￥]\s*(\d+)", text)
    if explicit_budget:
        val = explicit_budget.group(1) or explicit_budget.group(2) or explicit_budget.group(3)
        if val:
            profile.budget_total = int(val.replace("千", "000").replace("萬", "0000").replace("万", "0000"))
    # 仅数字（无上下文）不作为预算，避免 "1-2天 / 预算3000内" 中 "3000" 被误判

    # 旅行类型
    travel_types = ["蜜月旅行", "家庭出游", "独自旅行", "朋友团建", "亲子游", "商务旅行", "毕业旅行"]
    for t in travel_types:
        if t in text:
            profile.travel_type = t
            break

    # 行程节奏
    rhythms = ["轻松", "休闲", "适中", "紧凑", "慢节奏", "快节奏", "暴走"]
    for r in rhythms:
        if r in text:
            profile.rhythm_preference = r
            break

    # 住宿
    accommodations = ["经济型", "舒适型", "高档型", "民宿", "公寓", "豪华型", "酒店", "青旅", "豪华酒店"]
    for a in accommodations:
        if a in text:
            profile.accommodation_preference.type = ACCOMMODATION_MAP.get(a, a)
            break

    # 交通
    transports = ["飞机", "高铁", "自驾", "火车", "大巴", "步行", "地铁", "公交"]
    for t in transports:
        if t in text:
            profile.transport_preference.mode = t
            break

    # 美食
    cuisines = ["川菜", "粤菜", "湘菜", "火锅", "烧烤", "日料", "韩餐", "西餐", "泰餐", "越南菜"]
    for c in cuisines:
        if c in text:
            profile.food_preferences.cuisine_types = [c]
            break

    # 同行人数量
    people_match = re.search(r"(\d+)\s*人", text)
    if people_match:
        from travel_agent.models.user_profile import CompanionInfo
        count = int(people_match.group(1))
        profile.companions = [CompanionInfo(relation="朋友", count=count)]

    # 备注（兜底）
    if not any([
        profile.travel_type, profile.duration_days, profile.budget_total,
        profile.rhythm_preference, profile.accommodation_preference.type,
        profile.transport_preference.mode, profile.food_preferences.cuisine_types,
        profile.companions
    ]):
        profile.notes = (profile.notes or "") + " | " + text


def _build_profile_summary(profile: UserProfile) -> str:
    """构建用户画像摘要"""
    companions = profile.companions
    companion_str = ""
    if companions:
        companion_str = f"{companions[0].count}人（{companions[0].relation}）"

    # 天数显示：优先显示范围，其次显示精确值，都无则显示未指定
    days_display = profile.duration_days_range or (f"{profile.duration_days}天" if profile.duration_days else "未指定")
    budget_val = profile.budget_total
    budget_display = f"¥{budget_val:,.0f}" if budget_val else "未指定"

    return f"""目的地: {profile.destination}
旅行类型: {profile.travel_type or '未指定'}
天数: {days_display}
预算: {budget_display}
出行人数: {companion_str or '未指定'}
节奏偏好: {profile.rhythm_preference or '未指定'}
美食偏好: {','.join(profile.food_preferences.cuisine_types) or '未指定'}
住宿偏好: {profile.accommodation_preference.type or '未指定'}
交通方式: {profile.transport_preference.mode or '未指定'}
出发日期: {profile.travel_date or '未指定'}
必去景点: {','.join(profile.must_visit) or '无'}
备注: {profile.notes or '无'}"""


def _build_conversation_summary(state: AgentState) -> str:
    """构建对话摘要"""
    msgs = state.get("messages", [])
    parts = []
    for msg in msgs:
        if msg.role == "user":
            parts.append(f"用户：{msg.content}")
        elif msg.role == "assistant" and msg.is_question:
            parts.append(f"助手（问）：{msg.content}")
        elif msg.role == "assistant" and not msg.is_question:
            parts.append(f"助手（答）：{msg.content}")
    return "\n".join(parts)


def _get_llm_decision(state: AgentState) -> dict:
    """调用 LLM 决定下一步：继续追问还是开始规划"""
    profile = state["user_profile"]
    round_num = state.get("question_count", 0) + 1

    # 强制 plan 的阈值（防止 LLM 无限追问）
    FORCE_PLAN_THRESHOLD = 5

    try:
        response = call_chat_llm(
            system_prompt=NEEDS_ASSESSMENT_SYSTEM_PROMPT,
            user_prompt=NEEDS_ASSESSMENT_USER_PROMPT.format(
                destination=profile.destination,
                user_profile=_build_profile_summary(profile),
                conversation_summary=_build_conversation_summary(state),
                round=round_num,
            ),
        )
        result = safe_json_loads(response)
        if result and isinstance(result, dict) and result.get("action"):
            # 必要信息已齐全时，先确认用户是否还有其他需求，再进入规划
            if result.get("action") == "plan":
                return {"action": "confirm", "question": "好的，基本信息已经收集完毕了！在正式生成规划之前，您还有其他特别的需求吗？比如必去的景点、必吃的美食、住宿偏好、人数、出发日期等等？", "options": [
                    {"value": "没有了，直接生成规划", "emoji": "👍", "label": "没有了", "desc": "信息足够，直接生成规划"},
                    {"value": "补充需求", "emoji": "✏️", "label": "还有其他需求", "desc": "还有想补充的信息"},
                ]}
            return result
    except Exception as e:
        print(f"[WARN] LLM decision failed: {e}")

    # Fallback：按缺失信息智能追问，不再无限问"还有其他需求吗"
    missing = _find_missing_info(profile)

    if round_num >= FORCE_PLAN_THRESHOLD or not missing:
        return {"action": "confirm", "question": "好的，基本信息已经收集完毕了！在正式生成规划之前，您还有其他特别的需求吗？比如必去的景点、必吃的美食、住宿偏好、人数、出发日期等等？", "options": [
            {"value": "没有了，直接生成规划", "emoji": "👍", "label": "没有了", "desc": "信息足够，直接生成规划"},
            {"value": "补充需求", "emoji": "✏️", "label": "还有其他需求", "desc": "还有想补充的信息"},
        ]}

    # 追问缺失项
    question, options = _MISSING_INFO_QUESTIONS.get(missing, ("请问您还有什么特别的需求吗？", []))
    return {"action": "ask", "question": question, "options": options}


_MISSING_INFO_QUESTIONS = {
    "travel_type": ("这次旅行的性质是什么？", [
        {"value": "蜜月旅行", "emoji": "💕", "label": "蜜月旅行", "desc": "浪漫二人世界"},
        {"value": "家庭出游", "emoji": "👨‍👩‍👧", "label": "家庭出游", "desc": "带上家人一起"},
        {"value": "独自旅行", "emoji": "🎒", "label": "独自旅行", "desc": "一个人的冒险"},
        {"value": "朋友团建", "emoji": "👥", "label": "朋友团建", "desc": "和朋友一起浪"},
        {"value": "其他", "emoji": "✏️", "label": "其他", "desc": "自由描述"},
    ]),
    "duration": ("计划玩几天呢？", [
        {"value": "1-2天", "emoji": "🗓️", "label": "1-2天", "desc": "短途"},
        {"value": "3-5天", "emoji": "🗓️", "label": "3-5天", "desc": "标准"},
        {"value": "6-7天", "emoji": "🗓️", "label": "6-7天", "desc": "深度"},
        {"value": "7天以上", "emoji": "🗓️", "label": "7天+", "desc": "超长"},
        {"value": "其他", "emoji": "✏️", "label": "其他", "desc": "自由描述"},
    ]),
    "budget": ("大概准备多少预算呢？", [
        {"value": "3000以内", "emoji": "💰", "label": "3000以内", "desc": "经济实惠"},
        {"value": "5000左右", "emoji": "💰", "label": "5000左右", "desc": "标准"},
        {"value": "10000左右", "emoji": "💰", "label": "10000左右", "desc": "充裕"},
        {"value": "20000以上", "emoji": "💰", "label": "20000+", "desc": "豪华"},
        {"value": "其他", "emoji": "✏️", "label": "其他", "desc": "自由描述"},
    ]),
}


def _find_missing_info(profile: UserProfile) -> str | None:
    """找出缺失的必要信息"""
    if not profile.travel_type or profile.travel_type == "其他":
        return "travel_type"
    if not profile.duration_days or profile.duration_days <= 0:
        return "duration"
    if not profile.budget_total or profile.budget_total <= 0:
        return "budget"
    return None  # 所有必要信息已齐全


def _ensure_other(options: list):
    """确保选项里有「其他」"""
    if not any(opt.get("value") == "其他" for opt in options):
        options.append({"value": "其他", "emoji": "✏️", "label": "其他", "desc": "自由描述"})


def _send_question(state: AgentState, question: str, options: list):
    """发送一个问题"""
    _ensure_other(options)
    state["messages"].append(Message(
        role="assistant",
        content=question,
        is_question=True,
        options=options,
    ))
    state["question_count"] = state.get("question_count", 0) + 1


def _normalize_rag_items(items: list, key: str = "name") -> list[str]:
    """把 RAG 返回的字符串/字典统一归一化成可展示文本。"""
    normalized: list[str] = []
    for item in items or []:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            value = item.get(key) or item.get("title") or item.get("place") or item.get("content") or ""
            text = str(value).strip()
        else:
            text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def _do_plan(state: AgentState, profile: UserProfile, retriever, coordinator: MultiAgentCoordinator | None = None):
    """执行规划：本地知识检索 + 多智能体协同生成"""
    state["current_stage"] = Stages.REVIEW
    dest = profile.destination

    attractions, restaurants, raw_notes, rag_keywords, references, rag_trace = [], [], "", [], [], {}
    try:
        attractions, restaurants, raw_notes, rag_keywords, references, rag_trace = _retrieve_content(state)
    except Exception as e:
        print(f"[WARN] RAG retrieval failed: {e}")

    rag_sections: list[str] = []
    attraction_names = _normalize_rag_items(attractions, key="name")
    restaurant_names = _normalize_rag_items(restaurants, key="name")
    if attraction_names:
        rag_sections.append("景点参考：" + "、".join(attraction_names[:8]))
    if restaurant_names:
        rag_sections.append("美食参考：" + "、".join(restaurant_names[:8]))
    if raw_notes:
        rag_sections.append(raw_notes[:1200])
    rag_summary = "\n\n".join(section for section in rag_sections if section)

    trip_plan_payload = None
    plan_text = ""

    if coordinator is not None:
        try:
            result = coordinator.create_plan(
                PlanningContext(
                    profile=profile,
                    conversation_summary=_build_conversation_summary(state),
                    rag_summary=rag_summary,
                    references=references,
                )
            )
            trip_plan_payload = result.summary.structured_plan
            plan_text = _generate_plan_with_llm(
                profile,
                attractions,
                restaurants,
                raw_notes,
                dest,
                state,
                tool_outputs=result.execution.tool_outputs,
                failed_tools=result.execution.failed_tools,
                warnings=result.execution.warnings,
            )
            if plan_text:
                trip_plan_payload["content"] = plan_text
                trip_plan_payload["source"] = "multi_agent_llm"
            else:
                plan_text = trip_plan_payload.get("content", "")
                trip_plan_payload["source"] = "multi_agent_fallback"
                print("[WARN] LLM returned empty content, fallback to multi_agent summary")
        except Exception as e:
            print(f"[WARN] Multi-agent planning failed: {e}")
            if trip_plan_payload and trip_plan_payload.get("content"):
                plan_text = trip_plan_payload["content"]
                trip_plan_payload["source"] = trip_plan_payload.get("source") or "multi_agent"
                print("[WARN] Fallback to multi_agent summary after planning exception")

    if not plan_text:
        plan_text = _generate_plan_with_llm(profile, attractions, restaurants, raw_notes, dest, state)
        trip_plan_payload = {
            "destination": dest,
            "content": plan_text,
            "source": "llm",
            "rag_keywords": rag_keywords,
            "references": references,
            "used_tools": [],
        }
    else:
        trip_plan_payload.setdefault("destination", dest)
        trip_plan_payload.setdefault("rag_keywords", rag_keywords)
        trip_plan_payload.setdefault("references", references)

    state["trip_plan"] = trip_plan_payload

    if trip_plan_payload:
        trip_plan_payload.setdefault("agent_trace", {
            "planner_reasoning": trip_plan_payload.get("planner_reasoning", ""),
            "planned_tool_arguments": trip_plan_payload.get("planned_tool_arguments", {}),
            "used_tools": trip_plan_payload.get("used_tools", []),
            "tool_outputs": trip_plan_payload.get("tool_outputs", []),
            "failed_tools": trip_plan_payload.get("failed_tools", []),
            "warnings": trip_plan_payload.get("warnings", []),
            "rag_trace": rag_trace,
        })
        trip_plan_payload["agent_trace"].setdefault("rag_trace", rag_trace)

    state["messages"].append(Message(
        role="assistant",
        content=plan_text + "\n\n您对这份规划满意吗？有什么需要调整的地方？",
        is_question=True,
        options=[
            {"value": "满意", "emoji": "👍", "label": "满意", "desc": "可以了"},
            {"value": "调整景点", "emoji": "🏛️", "label": "调整景点", "desc": "换个景点"},
            {"value": "调整预算", "emoji": "💰", "label": "调整预算", "desc": "预算要改"},
            {"value": "调整节奏", "emoji": "🚶", "label": "调整节奏", "desc": "节奏不合适"},
            {"value": "其他", "emoji": "✏️", "label": "其他", "desc": "自由描述"},
        ],
    ))


# ============================================================
# 缺失的辅助函数
# ============================================================
def _new_state() -> AgentState:
    """创建新状态"""
    return AgentState(
        messages=[],
        user_profile=None,
        current_stage=Stages.WELCOME,
        answers={},
        info_sufficient=False,
        retrieved_docs=[],
        trip_plan=None,
        error=None,
        feedback_status=None,
        revision_target=None,
        question_count=0,
    )


def _extract_place_and_keywords(text: str, profile: UserProfile | None = None) -> tuple[str, list[str]]:
    """从文本中提取标准化地名，并返回更贴合用户需求的搜索关键词列表"""
    text = text.strip()
    if not text:
        return "未知", []

    fallback_keywords = [text]
    for suffix in ["景点", "美食", "攻略", "旅游"]:
        if suffix not in text:
            fallback_keywords.append(f"{text}{suffix}")

    if profile:
        if profile.travel_type and profile.travel_type not in fallback_keywords:
            fallback_keywords.append(profile.travel_type)
        if profile.duration_days and profile.duration_days > 0:
            fallback_keywords.append(f"{profile.duration_days}天行程")
        if profile.budget_total and profile.budget_total > 0:
            if profile.budget_total < 3000:
                fallback_keywords.extend(["经济", "性价比", "平价"])
            elif profile.budget_total < 8000:
                fallback_keywords.extend(["中等预算", "实惠", "性价比"])
            else:
                fallback_keywords.extend(["高预算", "舒适", "品质"])
        if profile.rhythm_preference:
            fallback_keywords.append(profile.rhythm_preference)

        cuisine_types = getattr(profile.food_preferences, "cuisine_types", []) or []
        fallback_keywords.extend(cuisine_types[:3])

        dietary_restrictions = getattr(profile.food_preferences, "dietary_restrictions", []) or []
        fallback_keywords.extend(dietary_restrictions[:3])

        profile_special_requirements = getattr(profile, "special_requirements", []) or []
        fallback_keywords.extend(profile_special_requirements[:3])

        must_visit = getattr(profile, "must_visit", []) or []
        fallback_keywords.extend(must_visit[:3])

    deduped_fallback = []
    seen = set()
    for kw in fallback_keywords:
        kw = str(kw).strip()
        if kw and kw not in seen:
            seen.add(kw)
            deduped_fallback.append(kw)

    if not profile:
        return text, deduped_fallback

    prompt = f"""你是旅行 RAG 检索词优化器。请根据用户需求，生成更适合做游记/攻略/评论检索的查询关键词，不要写死模板，不要泛泛而谈。

目的地：{text}
出发地：{profile.origin or '未指定'}
旅行类型：{profile.travel_type or '未指定'}
天数：{profile.duration_days or profile.duration_days_range or '未指定'}
预算：{profile.budget_total or '未指定'}
节奏：{profile.rhythm_preference or '未指定'}
交通：{profile.transport_preference.mode or '未指定'}
住宿偏好：{profile.accommodation_preference.type or '未指定'}
住宿位置偏好：{profile.accommodation_preference.location or '未指定'}
美食偏好：{','.join(profile.food_preferences.cuisine_types) or '无'}
饮食限制：{','.join(profile.food_preferences.dietary_restrictions) or '无'}
必去景点：{','.join(profile.must_visit) or '无'}
避开地点：{','.join(profile.avoid_places) or '无'}
备注：{profile.notes or '无'}

请输出 JSON：
{{
  "destination": "标准化后的检索目的地",
  "keywords": ["查询词1", "查询词2", "查询词3"]
}}

规则：
1. 只输出 JSON。
2. `destination` 可以比原始输入更适合检索，例如把国家级目的地细化为核心城市，但必须仍与用户需求一致。
3. `keywords` 要面向 RAG 检索，适合搜游记、攻略、评论、景点、美食、���宿区域，不要只堆砌单个偏好词。
4. 查询词尽量具体，优先包含目的地 + 场景，例如“首尔 明洞 攻略”、“首尔 弘大 美食”、“首尔 4天 行程”。
5. 返回 3 到 6 个关键词即可。
"""

    response = call_chat_llm(
        system_prompt="你是旅行 RAG 检索词优化器，只输出 JSON。",
        user_prompt=prompt,
        max_tokens=800,
        temperature=0.1,
    )
    payload = safe_json_loads(response)
    if isinstance(payload, dict):
        dest_norm = str(payload.get("destination") or text).strip() or text
        llm_keywords = payload.get("keywords")
        if isinstance(llm_keywords, list):
            merged = [dest_norm]
            for kw in llm_keywords:
                kw = str(kw).strip()
                if kw and kw not in merged:
                    merged.append(kw)
            for kw in deduped_fallback:
                if len(merged) >= 6:
                    break
                if kw not in merged:
                    merged.append(kw)
            return dest_norm, merged

    return text, deduped_fallback


def _load_crawler_data() -> list:
    """懒加载爬虫数据（仅当 RAG 为空时使用）"""
    global _CRAWLER_DATA_CACHE
    if _CRAWLER_DATA_CACHE is None:
        import json, os
        candidates = [
            "LittleCrawler/data/xhs/json/search_contents_2026-06-02.json",
            "data/xhs/json/search_contents_2026-06-02.json",
            "LittleCrawler/data/xhs/json/search_comments_2026-06-02.json",
        ]
        for path in candidates:
            full = os.path.join(os.path.dirname(os.path.dirname(__file__)), path)
            if os.path.exists(full):
                try:
                    with open(full, encoding="utf-8") as f:
                        _CRAWLER_DATA_CACHE = json.load(f)
                    break
                except Exception:
                    pass
        if _CRAWLER_DATA_CACHE is None:
            _CRAWLER_DATA_CACHE = []
    return _CRAWLER_DATA_CACHE


def _build_dest_knowledge(destination: str, keywords: list[str]) -> str:
    """从爬虫数据中动态提取目的地相关知识（景点、美食、体验）"""
    crawler = _load_crawler_data()
    if not crawler:
        return f"暂无 {destination} 的详细参考信息，请根据实际情况安排。"

    # 收集笔记中与目的地相关的条目
    matched_notes = []
    for note in crawler:
        # 检查标题、标签、描述是否包含目的地关键词
        combined = " ".join([
            note.get("title", ""),
            note.get("tag_list", ""),
            note.get("desc", ""),
        ])
        if any(kw in combined for kw in keywords):
            matched_notes.append(note)
        # 没有关键词时默认收录（爬虫数据本身就是为了这个目的地爬的）
        if not matched_notes:
            matched_notes.append(note)
            if len(matched_notes) >= 30:  # 最多取 30 条
                break

    if not matched_notes:
        return f"暂无 {destination} 的详细参考信息。"

    # 提取景点/美食关键词
    attractions_set, food_set, tips_set = set(), set(), set()
    for note in matched_notes[:30]:
        title = note.get("title", "")
        tags = note.get("tag_list", "")
        desc = note.get("desc", "")[:300]

        if title:
            attractions_set.add(title)
        if tags:
            food_keywords = [t for t in tags.split(",") if any(
                kw in t.lower() for kw in ["吃", "美食", "餐厅", "cafe", "咖啡", "烤肉", "炸鸡", "火锅", "甜品", "小吃"]
            )]
            food_set.update(food_keywords)
        if desc:
            tips_set.add(desc.strip().replace("\n", " ")[:150])

    parts = [f"【{destination}热门景点/体验】（来自 {len(matched_notes)} 篇小红书笔记）"]
    for a in list(attractions_set)[:8]:
        parts.append(f"  • {a}")

    if food_set:
        parts.append(f"\n【{destination}美食推荐】")
        for f in list(food_set)[:6]:
            parts.append(f"  • {f}")

    if tips_set:
        parts.append(f"\n【用户真实体验/小贴士】")
        for tip in list(tips_set)[:5]:
            parts.append(f"  • {tip}")

    return "\n".join(parts)


def _retrieve_content(state: AgentState, top_k: int = 5) -> tuple[list, list, str, list[str], list[dict], dict]:
    """检索相关内容，优先只保留相关性最高的少量结果"""
    profile = state["user_profile"]
    if not profile:
        return [], [], "", [], [], {}

    dest_norm, keywords = _extract_place_and_keywords(profile.destination, profile)
    attractions, restaurants = [], []
    references: list[dict] = []
    search_queries: list[str] = []
    rag_trace: dict = {
        "collection": "travel",
        "destination": dest_norm,
        "generated_keywords": keywords,
        "queries": [],
        "fused_result_count": 0,
        "selected_notes": 0,
        "selected_comments": 0,
        "status": "idle",
    }

    try:
        from travel_agent.rag.retriever import MultiQueryRetriever
        from travel_agent.rag.vectorstore import ChromaVectorStore

        retriever = MultiQueryRetriever(
            vector_store=ChromaVectorStore(collection_name="travel"),
            top_k=top_k,
        )

        search_queries = [dest_norm]
        _ = _build_dest_knowledge(dest_norm, keywords)
        for kw in keywords:
            if kw != dest_norm and kw not in search_queries:
                search_queries.append(kw)
            if len(search_queries) >= 6:
                break

        rag_trace["search_queries"] = search_queries
        print(f"[INFO] RAG keywords for {dest_norm}: {', '.join(search_queries)}")

        query_rankings: list[list[dict]] = []
        for query in search_queries:
            try:
                docs = retriever.vector_store.search(
                    query=query,
                    top_k=top_k,
                )
                print(f"[INFO] RAG query '{query}' got {len(docs)} docs")
                rag_trace["queries"].append({
                    "query": query,
                    "hit_count": len(docs),
                    "top_docs": [
                        {
                            "title": doc.get("metadata", {}).get("title", "未命名文档"),
                            "type": doc.get("metadata", {}).get("type", "unknown"),
                            "score": round(float(doc.get("score", 0.0) or 0.0), 4),
                            "url": doc.get("metadata", {}).get("url", ""),
                        }
                        for doc in docs[:3]
                    ],
                })
            except Exception as e:
                print(f"[WARN] RAG query '{query}' failed: {e}")
                rag_trace["queries"].append({
                    "query": query,
                    "hit_count": 0,
                    "error": str(e),
                    "top_docs": [],
                })
                continue

            ranked_docs = []
            for rank, doc in enumerate(docs, start=1):
                ranked_docs.append({
                    "content": doc.get("content", ""),
                    "metadata": doc.get("metadata", {}),
                    "score": doc.get("score", 0.0),
                    "id": doc.get("id"),
                    "url": doc.get("metadata", {}).get("url", ""),
                    "rank": rank,
                    "query": query,
                })
            if ranked_docs:
                query_rankings.append(ranked_docs)

        fused_scores: dict[str, dict] = {}
        for docs in query_rankings:
            for rank, item in enumerate(docs, start=1):
                doc_id = item.get("id") or item.get("content", "")
                if doc_id not in fused_scores:
                    fused_scores[doc_id] = {
                        "content": item["content"],
                        "metadata": item.get("metadata", {}),
                        "score": 0.0,
                        "id": item.get("id"),
                        "url": item.get("url", ""),
                        "queries": set(),
                    }
                fused_scores[doc_id]["score"] += 1.0 / (60 + rank)
                fused_scores[doc_id]["queries"].add(item.get("query", ""))

        fused_docs = sorted(
            fused_scores.values(),
            key=lambda x: (x["score"], len(x["queries"])),
            reverse=True,
        )[:top_k]
        rag_trace["fused_result_count"] = len(fused_docs)
        rag_trace["fused_docs"] = [
            {
                "title": doc.get("metadata", {}).get("title", "未命名文档"),
                "type": doc.get("metadata", {}).get("type", "unknown"),
                "score": round(float(doc.get("score", 0.0) or 0.0), 4),
                "url": doc.get("url", ""),
                "queries": sorted(list(doc.get("queries", set()))),
            }
            for doc in fused_docs
        ]

        seen_places = set()
        note_docs = []
        comment_docs = []
        for doc in fused_docs:
            doc_type = doc.get("metadata", {}).get("type", "")
            if doc_type == "comment":
                if len(comment_docs) < 5:
                    comment_docs.append(doc)
            else:
                if len(note_docs) < 5:
                    note_docs.append(doc)
            if len(note_docs) >= 5 and len(comment_docs) >= 5:
                break

        rag_trace["selected_notes"] = len(note_docs)
        rag_trace["selected_comments"] = len(comment_docs)

        raw_notes_parts = ["【来自 travel collection 的热门攻略笔记】"]
        for doc in note_docs:
            place = _extract_place_name_from_content(doc["content"], doc["metadata"].get("title", ""))
            if not place or place in seen_places:
                continue
            seen_places.add(place)
            tips = _clean_tips(doc["content"][:200])
            attractions.append({
                "name": place,
                "category": "景点",
                "tips": [tips],
            })
            raw_notes_parts.append(f"📍 {doc['metadata'].get('title', place)}\n{_clean_tips(doc['content'][:400])}")
            references.append({
                "name": doc["metadata"].get("title", place),
                "place": place,
                "type": "笔记",
                "url": doc.get("url", ""),
                "score": round(doc["score"], 4),
                "queries": sorted(list(doc.get("queries", set()))),
                "collection": "travel",
            })

        if comment_docs:
            raw_notes_parts.append("\n【来自 travel collection 的热门评论】")
            for doc in comment_docs:
                author = doc.get("metadata", {}).get("author", "匿名用户")
                raw_notes_parts.append(f"💬 {author}\n{_clean_tips(doc['content'][:240])}")

        raw_notes = "\n".join(raw_notes_parts) if len(raw_notes_parts) > 1 else ""
        rag_trace["status"] = "success"

        print(f"[INFO] RAG retrieved {len(note_docs)} notes, {len(comment_docs)} comments, {len(attractions)} attractions, 0 restaurants, {len(fused_docs)} fused docs for {dest_norm} (top_k={top_k})")
    except Exception as e:
        print(f"[WARN] RAG retrieval failed: {e}")
        raw_notes = ""
        rag_trace["status"] = "failed"
        rag_trace["error"] = str(e)

    return attractions, restaurants, raw_notes, search_queries, references, rag_trace


def _extract_place_name_from_content(content: str, fallback_title: str) -> str:
    """从笔记内容中提取景点/餐厅名称"""
    content = content.strip()
    if not content:
        return fallback_title or "未知地点"

    import re

    invalid_markers = ["评论", "用户", "IP属地", "流量卡", "请教", "你好", "日本吃饭", "楼主会日语"]

    def _is_valid_place(text: str) -> bool:
        text = text.strip("【】[]（）()：:.- ")
        if not text or len(text) < 2 or len(text) > 30:
            return False
        if any(marker in text for marker in invalid_markers):
            return False
        if text.startswith("💬") or text.startswith("用户"):
            return False
        return True

    headings = re.findall(r'^#+\s*(.+?)(?:\n|$)', content, re.MULTILINE)
    for h in headings:
        h = h.strip()
        if _is_valid_place(h) and not h.startswith("攻略") and not h.startswith("必备"):
            return h

    subheadings = re.findall(r'^#{1,2}\s*(.+?)(?:\n|$)', content, re.MULTILINE)
    for s in subheadings:
        s = s.strip()
        if _is_valid_place(s):
            return s

    first_line = content.split("\n")[0].strip()
    if _is_valid_place(first_line):
        return first_line

    if _is_valid_place(fallback_title):
        return fallback_title.strip()

    match = re.search(r"[\u4e00-\u9fffA-Za-z]{2,20}(塔|寺|宫|馆|园|山|湖|川|街|站|店|村|谷|城|桥|浜|町|神社|美术馆|展望台|公园)", content)
    if match:
        return match.group(0)

    return "未知地点"


def _clean_tips(text: str) -> str:
    """清理笔记内容中的话题标签，保留核心描述"""
    import re
    # 移除 #话题# 标签
    text = re.sub(r'#\S+', '', text)
    # 移除多余空白
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:150] if text else "值得一去"


def _extract_places_from_notes(attr_docs: list, rest_docs: list) -> str:
    """将检索到的笔记整理成参考文本，供 LLM 规划时使用"""
    sections = []
    sections.append("【来自小红书的热门攻略笔记】")

    for doc in (attr_docs + rest_docs)[:15]:
        title = doc.metadata.get("title", "未命名笔记")
        content = doc.content
        if not content or len(content) < 20:
            continue
        # 取前400字，移除话题标签
        excerpt = _clean_tips(content[:400])
        sections.append(f"\n📍 {title}\n{excerpt}")

    return "\n".join(sections) if sections else ""


def _generate_plan_with_llm(
    profile: UserProfile,
    attractions: list,
    restaurants: list,
    raw_notes: str,
    destination: str,
    state: AgentState,
    tool_outputs: list[dict] | None = None,
    failed_tools: list[dict] | None = None,
    warnings: list[str] | None = None,
) -> str:
    """使用 LLM 生成行程规划，直接返回 Markdown 文本。"""

    if raw_notes:
        reference_docs = raw_notes
    else:
        ref_parts = []
        if attractions:
            ref_parts.append("【推荐景点】")
            for a in attractions[:8]:
                ref_parts.append(f"- {a['name']}: {a['tips'][0] if a.get('tips') else '值得一去'}")
        if restaurants:
            ref_parts.append("\n【推荐餐厅】")
            for r in restaurants[:8]:
                ref_parts.append(f"- {r['name']}: {r['tips'][0] if r.get('tips') else '味道不错'}")
        reference_docs = "\n".join(ref_parts) if ref_parts else "暂无详细参考信息。"

    tool_outputs = tool_outputs or []
    failed_tools = failed_tools or []
    warnings = warnings or []

    tool_lines = []
    tool_name_map = {
        "weather_lookup": "天气",
        "poi_search": "POI 景点",
        "hotel_search": "酒店",
        "train_search": "火车/高铁",
        "calendar_lookup": "黄历/农历",
        "flight_search": "机票",
    }
    for item in tool_outputs:
        tool_name = item.get("tool", "")
        summary = (item.get("summary") or "").strip()
        raw = item.get("raw")
        if not tool_name or not summary:
            continue
        pretty_name = tool_name_map.get(tool_name, tool_name)
        preview = "\n".join(summary.splitlines()[:10]).strip()
        tool_lines.append(f"- {pretty_name}（{tool_name}）\n摘要：{preview}")
        if raw is not None:
            tool_lines.append(f"  原始返回：{raw}")
    tool_context = "\n".join(tool_lines) if tool_lines else "暂无成功的实时工具结果。"

    failed_lines = []
    for item in failed_tools:
        tool_name = item.get("tool", "")
        summary = (item.get("summary") or "").strip()
        raw = item.get("raw")
        status = item.get("status") or "failed"
        if not tool_name:
            continue
        pretty_name = tool_name_map.get(tool_name, tool_name)
        failed_lines.append(f"- {pretty_name}（{tool_name} / {status}）\n摘要：{summary or '无'}")
        if raw is not None:
            failed_lines.append(f"  原始返回：{raw}")
    failed_context = "\n".join(failed_lines) if failed_lines else "无"

    warning_context = "\n".join(f"- {warning}" for warning in warnings if warning.strip()) or "无"

    user_profile_str = f"""目的地: {destination}
旅行类型: {profile.travel_type or '未指定'}
天数: {profile.duration_days or '未指定'}天
预算: ¥{profile.budget_total or '未指定'}
节奏偏好: {profile.rhythm_preference or '未指定'}
美食偏好: {','.join(profile.food_preferences.cuisine_types) or '都可以'}
住宿: {profile.accommodation_preference.type or '未指定'}
交通: {profile.transport_preference.mode or '未指定'}
必去景点: {','.join(profile.must_visit) or '无'}
备注: {profile.notes or '无'}"""

    qa_history = ""
    if state and state.get("messages"):
        lines = []
        for msg in state["messages"]:
            if msg.role == "user":
                lines.append(f"用户：{msg.content}")
            elif msg.role == "assistant" and msg.is_question:
                lines.append(f"助手（问）：{msg.content}")
            elif msg.role == "assistant" and not msg.is_question:
                lines.append(f"助手（答）：{msg.content}")
        if lines:
            qa_history = "\n".join(lines)

    prompt = f"""请基于以下信息，为用户生成一份完整的 {destination} 旅行规划。

=== 需求确认对话历史 ===
{qa_history}

=== 用户画像 ===
{user_profile_str}

=== {destination} 热门攻略笔记（来自小红书真实用户分享）===
{reference_docs}

=== 实时工具结果（优先参考）===
{tool_context}

=== 已跳过/失败的实时工具 ===
{failed_context}

=== 实时工具异常/缺失信息 ===
{warning_context}

要求：
1. 必须融合对话历史中的所有明确需求，尤其是用户补充的偏好、必去点、预算、节奏等
2. 必须优先使用实时工具结果中的天气、POI、酒店、火车/高铁、机票信息；若某类工具没有结果，再回退使用攻略笔记
3. 必须融合小红书笔记中的真实景点和餐厅名称，不要虚构地名
4. 如果实时工具结果中没有机票信息，不要编造机票班次、价格或航班号
5. 每天至少安排 4 个时段：上午 / 午餐 / 下午 / 晚餐
6. 每天行程要有区别，避免前后天重复
7. 预算要合理分配，并给出总预算和小结；预算摘要必须完整输出六项：总预算、交通、餐饮、住宿、购物、其他，其中“其他”不能省略，且每一项都要有明确金额
8. 输出必须是 Markdown，不要输出 JSON，不要输出代码块，不要加解释性前缀
9. 直接输出最终规划正文，要求可直接展示给用户
10. 若实时工具结果与攻略笔记冲突，优先采用实时工具结果，并在小贴士里简短提示"以实时查询为准"

请按以下结构输出：
# {destination} 旅行规划

## 旅行概览
- 目的地：
- 天数：
- 预算：
- 风格概述：

## Day 1：标题
### 🌅 上午
- 地点：
- 时间：
- 亮点：

### 🍽️ 午餐
- 地点：
- 时间：
- 推荐理由：

### ☀️ 下午
- 地点：
- 时间：
- 亮点：

### 🌙 晚餐
- 地点：
- 时间：
- 推荐理由：

## Day 2：...

## 预算摘要
- 总预算：
- 交通：
- 餐饮：
- 住宿：
- 购物：
- 其他：

## 小贴士
- 
- 
"""

    response = call_chat_llm(
        system_prompt="你是专业旅行规划师。请直接输出完整 Markdown 行程，不要输出 JSON，不要输出代码块，不要输出解释。",
        user_prompt=prompt,
        max_tokens=8192,
        temperature=0.35,
    )

    return response.strip() if response else f"# {destination} 旅行规划\n\n抱歉，当前未能生成完整规划。"



def _format_plan(plan: dict) -> str:
    """格式化行程为文本"""
    if not plan:
        return "暂无规划"
    lines = [f"📋 **{plan.get('destination', '您的')} 旅行规划已生成！**\n"]
    lines.append(f"行程时长：{plan.get('duration', '')}\n")

    for day in plan.get("daily_plans", []):
        lines.append(f"### Day {day.get('day', '')}: {day.get('theme', '自由探索')}")
        for slot_name, icon in [("morning", "🌅"), ("lunch", "🍽️"), ("afternoon", "☀️"), ("dinner", "🌙")]:
            slot = day.get(slot_name)
            if slot:
                place = slot.get("place_name", slot.get("place", ""))
                time_range = slot.get("time_range", "")
                tips = slot.get("tips", "")
                lines.append(f"{icon} {time_range} | {place} | {tips}")
        lines.append("")

    budget = plan.get("budget_summary", {})
    if budget:
        lines.append(f"### 预算摘要\n总预算：¥{budget.get('total', 0):,.0f}\n")

    tips = plan.get("tips", [])
    if tips:
        lines.append("### 小贴士\n")
        for tip in tips:
            lines.append(f"- {tip}")

    return "\n".join(lines)


# ============================================================
# Flask 路由
# ============================================================
def _create_flask_routes(
    app: Flask,
    sessions: dict,
    retriever,
    optimizer,
    coordinator: MultiAgentCoordinator | None = None,
    session_store: ChatSessionStore | None = None,
):

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/chat", methods=["POST"])
    def chat():
        try:
            data = request.json or {}
            user_message = data.get("message", "")
            session_id = data.get("session_id")

            if session_id and session_id in sessions:
                state = sessions[session_id]
            elif session_id and session_store:
                state = session_store.load_state(session_id)
                if state is not None:
                    sessions[session_id] = state
                else:
                    session_id = str(uuid.uuid4())
                    state = _new_state()
                    sessions[session_id] = state
            else:
                session_id = str(uuid.uuid4())
                state = _new_state()
                sessions[session_id] = state

            state["messages"].append(Message(role="user", content=user_message))

            # 欢迎阶段：设置目的地
            if state["current_stage"] == Stages.WELCOME:
                user_text = user_message.strip()
                # 从输入中剥离天数/预算词，提取纯目的地
                dest = re.sub(r"[\d一二三四五六七八九十百]+[天日天]|预算[以内左右约]?\d+|每天\d+", "", user_text).strip()
                if not dest:
                    dest = user_text
                state["user_profile"] = UserProfile(destination=dest)
                # 欢迎阶段也解析天数等信息
                _parse_answer(state["user_profile"], user_text)
                state["current_stage"] = Stages.TRAVEL_TYPE
                state["question_count"] = 0
                # 第一次由 LLM 决定问什么
                decision = _get_llm_decision(state)
                if decision.get("action") == "plan":
                    # 必要信息齐全但先确认，进入 CONFIRM 阶段
                    state["current_stage"] = Stages.CONFIRM
                    state["messages"].append(Message(role="assistant", content=decision.get("question", "好的，基本信息已收集完毕！在正式生成规划之前，您还有其他特别的需求吗？"), is_question=True, options=decision.get("options", [])))
                elif decision.get("action") == "confirm":
                    state["current_stage"] = Stages.CONFIRM
                    state["messages"].append(Message(role="assistant", content=decision["question"], is_question=True, options=decision["options"]))
                else:
                    _send_question(state, decision["question"], decision.get("options", []))
            else:
                profile = state["user_profile"]

                # CONFIRM 阶段：用户也可以通过输入文字来回答"还有补充吗"
                if state["current_stage"] == Stages.CONFIRM:
                    lower_msg = user_message.strip().lower()
                    if "没有" in lower_msg or "直接" in lower_msg or "生成" in lower_msg:
                        state["current_stage"] = Stages.PLANNING
                        _do_plan(state, profile, retriever, coordinator)
                    else:
                        # 用户输入了补充内容，记录到备注
                        profile.notes = (profile.notes or "") + f" | [用户补充] {user_message}"
                        state["current_stage"] = Stages.CONFIRM
                        # 继续询问是否还有其他补充
                        state["messages"].append(Message(
                            role="assistant",
                            content="好的，已记录您的补充！还有其他需要补充的吗？",
                            is_question=True,
                            options=[
                                {"value": "没有了，直接生成规划", "emoji": "👍", "label": "没有了", "desc": "信息足够，直接生成规划"},
                                {"value": "补充需求", "emoji": "✏️", "label": "还有其他需求", "desc": "还有想补充的信息"},
                            ],
                        ))

                # 补充需求阶段：用户用文字描述补充内容
                elif state["current_stage"] == Stages.SPECIAL_REQUIREMENTS:
                    profile.notes = (profile.notes or "") + f" | [用户补充] {user_message}"
                    state["current_stage"] = Stages.CONFIRM
                    state["messages"].append(Message(
                        role="assistant",
                        content="好的，已记录您的补充！在正式生成规划之前，您还有其他特别的需求吗？",
                        is_question=True,
                        options=[
                            {"value": "没有了，直接生成规划", "emoji": "👍", "label": "没有了", "desc": "信息足够，直接生成规划"},
                            {"value": "补充需求", "emoji": "✏️", "label": "还有其他需求", "desc": "还有想补充的信息"},
                        ],
                    ))

                # 规划已生成后的追问（行程调整等）
                elif state["current_stage"] == Stages.PLANNING:
                    state["messages"].append(Message(
                        role="assistant",
                        content=f"好的，您的需求是：{user_message}。请告诉我您希望如何调整行程？",
                        is_question=True,
                        options=[
                            {"value": "调整景点", "emoji": "🏛️", "label": "调整景点", "desc": "换个景点"},
                            {"value": "调整预算", "emoji": "💰", "label": "调整预算", "desc": "预算要改"},
                            {"value": "调整节奏", "emoji": "🚶", "label": "调整节奏", "desc": "节奏不合适"},
                        ],
                    ))

                # 普通信息收集阶段
                else:
                    _parse_answer(profile, user_message)
                    decision = _get_llm_decision(state)
                    if decision.get("action") == "confirm":
                        state["current_stage"] = Stages.CONFIRM
                        state["messages"].append(Message(
                            role="assistant",
                            content=decision["question"],
                            is_question=True,
                            options=decision["options"],
                        ))
                    elif decision.get("action") == "plan":
                        state["current_stage"] = Stages.CONFIRM
                        state["messages"].append(Message(
                            role="assistant",
                            content="好的，基本信息已收集完毕！在正式生成规划之前，您还有其他特别的需求吗？",
                            is_question=True,
                            options=[
                                {"value": "没有了，直接生成规划", "emoji": "👍", "label": "没有了", "desc": "信息足够，直接生成规划"},
                                {"value": "补充需求", "emoji": "✏️", "label": "还有其他需求", "desc": "还有想补充的信息"},
                            ],
                        ))
                    else:
                        _send_question(state, decision["question"], decision.get("options", []))

            latest = state["messages"][-1] if state["messages"] else None
            # 分离：messages 只到用户消息，助手下一轮问题通过 next_question 传递
            msgs = [msg for msg in state["messages"] if msg.role == "user"]
            next_q = latest.content if latest and latest.role == "assistant" else None
            next_opts = latest.options if latest and latest.role == "assistant" else []
            sessions[session_id] = state
            if session_store:
                session_store.save_state(session_id, state)
            return jsonify({
                "session_id": session_id,
                "messages": [msg.model_dump() for msg in msgs],
                "next_question": next_q,
                "next_options": next_opts,
                "current_stage": state["current_stage"],
                "trip_plan": state["trip_plan"],
                "user_profile": state["user_profile"].model_dump() if state["user_profile"] else None,
            })
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e), "message": "抱歉，服务出错了，请重试。"}), 500

    @app.route("/api/select", methods=["POST"])
    def select_option():
        try:
            data = request.json or {}
            option_value = data.get("value", "")
            session_id = data.get("session_id")
            custom_text = data.get("custom_text", "")

            if not session_id or session_id not in sessions:
                return jsonify({"error": "Session not found"}), 404

            state = sessions[session_id]
            profile = state["user_profile"]
            if not profile:
                return jsonify({"error": "No user profile"}), 400

            # "其他"选项用自定义文本
            if option_value == "其他" and custom_text.strip():
                option_value = custom_text.strip()

            # 将用户点击的选项作为用户消息记录（让聊天历史完整显示）
            state["messages"].append(Message(role="user", content=option_value))

            # ---------- 按阶段分别处理 ----------

            # 1. REVIEW 阶段（行程已生成，用户做调整选择）
            if state["current_stage"] == Stages.REVIEW:
                state["answers"]["review_choice"] = option_value
                if option_value == "满意":
                    state["messages"].append(Message(role="assistant", content="太好了！祝您旅途愉快～"))
                else:
                    state["messages"].append(Message(role="assistant", content=f"好的，我们来调整：{option_value}"))
                sessions[session_id] = state
                return jsonify({
                    "session_id": session_id,
                    "messages": [msg.model_dump() for msg in state["messages"]],
                    "next_question": None,
                    "next_options": [],
                    "current_stage": Stages.REVIEW,
                    "trip_plan": state["trip_plan"],
                })

            # 2. CONFIRM 阶段（必要信息已齐全，询问"还有其他需求吗？"）
            if state["current_stage"] == Stages.CONFIRM:
                if option_value == "没有了，直接生成规划":
                    state["current_stage"] = Stages.PLANNING
                    _do_plan(state, profile, retriever, coordinator)
                else:
                    # 用户选择了要补充某方面 → 进入 SPECIAL_REQUIREMENTS 追问具体内容
                    state["current_stage"] = Stages.SPECIAL_REQUIREMENTS
                    state["messages"].append(Message(
                        role="assistant",
                        content="好的，请告诉我您还有什么需要补充的？",
                        is_question=True,
                        options=[
                            {"value": "补充必去景点", "emoji": "🏛️", "label": "补充必去景点", "desc": "添加必去的景点"},
                            {"value": "补充人数/日期", "emoji": "👥", "label": "补充人数/日期", "desc": "补充出行人数或日期"},
                            {"value": "补充预算/住宿", "emoji": "💰", "label": "补充预算/住宿", "desc": "调整预算或住宿偏好"},
                            {"value": "补充美食偏好", "emoji": "🍽️", "label": "补充美食偏好", "desc": "添加想吃的美食类型"},
                            {"value": "其他特殊需求", "emoji": "✏️", "label": "其他特殊需求", "desc": "其他需求"},
                        ],
                    ))

            # 3. SPECIAL_REQUIREMENTS 阶段（用户已选了要补充哪方面，追问具体内容）
            elif state["current_stage"] == Stages.SPECIAL_REQUIREMENTS:
                supplemental_map = {
                    "补充必去景点": ("必去景点", "请告诉我您有哪些必去的景点？"),
                    "补充人数/日期": ("人数/日期", "请告诉我出行人数和出发日期？"),
                    "补充预算/住宿": ("预算/住宿", "请告诉我调整后的预算和住宿偏好？"),
                    "补充美食偏好": ("美食偏好", "请告诉我您想吃的美食类型？"),
                    "其他特殊需求": ("特殊需求", "请告诉我您的特殊需求？"),
                }
                label, prompt = supplemental_map.get(option_value, ("补充信息", "请告诉我您还想补充什么信息？"))
                profile.notes = (profile.notes or "") + f" | [{label}] {option_value}"
                # 追问具体内容，回复后回到 CONFIRM
                state["messages"].append(Message(
                    role="assistant",
                    content=prompt,
                    is_question=True,
                    options=[{"value": "其他", "emoji": "✏️", "label": "其他", "desc": "自由描述"}],
                ))
                state["current_stage"] = Stages.CONFIRM

            # 4. 普通信息收集阶段：解析选项 → LLM 决定下一步
            else:
                global _CRAWLER_DATA_CACHE
                _parse_answer(profile, option_value)

                decision = _get_llm_decision(state)
                if decision.get("action") == "confirm":
                    state["current_stage"] = Stages.CONFIRM
                    state["messages"].append(Message(
                        role="assistant",
                        content=decision["question"],
                        is_question=True,
                        options=decision["options"],
                    ))
                elif decision.get("action") == "plan":
                    # 必要信息已齐全，先确认是否还有其他需求
                    state["current_stage"] = Stages.CONFIRM
                    state["messages"].append(Message(
                        role="assistant",
                        content="好的，基本信息已收集完毕！在正式生成规划之前，您还有其他特别的需求吗？比如必去的景点、必吃的美食、住宿偏好、人数、出发日期等等？",
                        is_question=True,
                        options=[
                            {"value": "没有了，直接生成规划", "emoji": "👍", "label": "没有了", "desc": "信息足够，直接生成规划"},
                            {"value": "补充需求", "emoji": "✏️", "label": "还有其他需求", "desc": "还有想补充的信息"},
                        ],
                    ))
                else:
                    _send_question(state, decision["question"], decision.get("options", []))

            # ---------- 返回响应 ----------
            latest = state["messages"][-1] if state["messages"] else None
            next_q = latest.content if latest and latest.role == "assistant" else None
            next_opts = latest.options if latest and latest.role == "assistant" else []

            sessions[session_id] = state
            if session_store:
                session_store.save_state(session_id, state)
            return jsonify({
                "session_id": session_id,
                "messages": [msg.model_dump() for msg in state["messages"]],
                "next_question": next_q,
                "next_options": next_opts,
                "current_stage": state["current_stage"],
                "trip_plan": state["trip_plan"],
            })
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e), "message": "抱歉，服务出错了，请重试。"}), 500

    @app.route("/api/sessions", methods=["GET"])
    def list_sessions():
        if not session_store:
            return jsonify({"sessions": []})
        return jsonify({"sessions": session_store.list_sessions()})

    @app.route("/api/sessions", methods=["POST"])
    def create_session():
        state = _new_state()
        session_id = session_store.create_session() if session_store else str(uuid.uuid4())
        sessions[session_id] = state
        if session_store:
            session_store.save_state(session_id, state)
        return jsonify({
            "session_id": session_id,
            "messages": [],
            "current_stage": state["current_stage"],
            "trip_plan": state["trip_plan"],
        })

    @app.route("/api/sessions/<session_id>", methods=["GET"])
    def get_session(session_id: str):
        state = sessions.get(session_id)
        if state is None and session_store:
            state = session_store.load_state(session_id)
            if state is not None:
                sessions[session_id] = state
        if state is None:
            return jsonify({"error": "Session not found"}), 404
        latest = state["messages"][-1] if state.get("messages") else None
        return jsonify({
            "session_id": session_id,
            "messages": [msg.model_dump() for msg in state.get("messages", [])],
            "next_question": latest.content if latest and latest.role == "assistant" else None,
            "next_options": latest.options if latest and latest.role == "assistant" else [],
            "current_stage": state.get("current_stage", Stages.WELCOME),
            "trip_plan": session_store._make_json_safe(state.get("trip_plan")) if session_store else state.get("trip_plan"),
            "user_profile": state["user_profile"].model_dump() if state.get("user_profile") else None,
        })

    @app.route("/api/sessions/<session_id>", methods=["DELETE"])
    def delete_session(session_id: str):
        sessions.pop(session_id, None)
        if session_store:
            session_store.delete_session(session_id)
        return jsonify({"ok": True, "session_id": session_id})

    return app


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", str(uuid.uuid4()))
    CORS(app)

    sessions: dict[str, AgentState] = {}
    session_store = ChatSessionStore()

    retriever = None
    optimizer = None
    coordinator = MultiAgentCoordinator()

    try:
        from travel_agent.optimizer.trip_optimizer import TripOptimizer
        from travel_agent.rag.vectorstore import ChromaVectorStore
        from travel_agent.rag.embedder import create_embedder

        # 初始化两个 collection 的检索器
        travel_store = ChromaVectorStore(collection_name="travel")
        restaurant_store = ChromaVectorStore(collection_name="restaurant")
        print(f"[INFO] RAG travel collection: {travel_store.count()} docs")
        print(f"[INFO] RAG restaurant collection: {restaurant_store.count()} docs")
        retriever = None  # 不再需要通用的 retriever
        optimizer = TripOptimizer()
    except Exception as e:
        print(f"[WARN] Failed to initialize RAG retriever: {e}")
        retriever = None
        optimizer = None

    _create_flask_routes(app, sessions, retriever, optimizer, coordinator, session_store)
    return app


app = create_app()
