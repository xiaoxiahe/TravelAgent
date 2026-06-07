"""Travel tool registry and execution metadata."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ToolType = Literal["skill", "rag", "special"]


@dataclass(slots=True)
class ToolDefinition:
    """单个工具的结构化定义。"""

    name: str
    description: str
    tool_type: ToolType = "skill"
    required_fields: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    skill_name: str | None = None
    command_template: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_prompt_text(self) -> str:
        required = f"；必填参数: {', '.join(self.required_fields)}" if self.required_fields else ""
        skill = f"；来源技能: {self.skill_name}" if self.skill_name else ""
        tags = f"；标签: {', '.join(self.tags)}" if self.tags else ""
        return f"- {self.name}: {self.description}{skill}{required}{tags}"


AVAILABLE_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="weather_lookup",
        description="查询目的地天气概况与出行提醒",
        skill_name="amap-lbs-skill",
        required_fields=["city"],
        parameters={
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "目的地城市"},
                "travel_date": {"type": "string", "description": "出发日期，可为空"},
            },
        },
        tags=["weather", "planning"],
        metadata={"capability": "amap-weather"},
    ),
    ToolDefinition(
        name="poi_search",
        description="搜索景点、商圈、博物馆等兴趣点",
        skill_name="amap-lbs-skill",
        required_fields=["city", "keyword"],
        parameters={
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "目的地城市"},
                "keyword": {"type": "string", "description": "景点或兴趣点关键词"},
            },
        },
        tags=["poi", "attraction"],
        metadata={"capability": "amap-poi"},
    ),
    ToolDefinition(
        name="hotel_search",
        description="查询住宿候选项与价格区间",
        skill_name="rollinggo-hotel-cli",
        required_fields=["destination", "check_in_date", "check_out_date"],
        parameters={
            "type": "object",
            "properties": {
                "destination": {"type": "string", "description": "目的地城市"},
                "keyword": {"type": "string", "description": "酒店区域或住宿偏好"},
                "check_in_date": {"type": "string", "description": "入住日期 YYYY-MM-DD"},
                "check_out_date": {"type": "string", "description": "离店日期 YYYY-MM-DD"},
            },
        },
        tags=["hotel", "accommodation"],
        metadata={"capability": "rollinggo-search"},
    ),
    ToolDefinition(
        name="calendar_lookup",
        description="查询指定出发日期的农历、干支与宜忌信息",
        skill_name="lao-huangli",
        required_fields=["date"],
        parameters={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "日期，格式 YYYY-MM-DD"},
            },
        },
        tags=["calendar", "lunar", "planning"],
        metadata={"capability": "huangli"},
    ),
    ToolDefinition(
        name="flight_search",
        description="查询机票候选班次与价格区间",
        skill_name="rollinggo-flight-skill",
        required_fields=["origin", "destination", "travel_date"],
        parameters={
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "出发地"},
                "destination": {"type": "string", "description": "目的地"},
                "travel_date": {"type": "string", "description": "出发日期 YYYY-MM-DD"},
                "trip_type": {"type": "string", "description": "单程或往返，默认 ONE_WAY"},
                "cabin_grade": {"type": "string", "description": "舱位等级，默认 ECONOMY"},
            },
        },
        tags=["flight", "transport"],
        metadata={"capability": "rollinggo-flight"},
    ),
]


def get_tool_registry() -> dict[str, ToolDefinition]:
    return {tool.name: tool for tool in AVAILABLE_TOOLS}


def format_tool_registry_for_prompt() -> str:
    return "\n".join(tool.to_prompt_text() for tool in AVAILABLE_TOOLS)
