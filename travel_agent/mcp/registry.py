"""项目内 MCP 工具定义与注册表。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ToolType = Literal["mcp", "rag", "special"]


@dataclass(slots=True)
class ToolDefinition:
    """单个工具的结构化定义。"""

    name: str
    description: str
    server_name: str | None = None
    remote_name: str | None = None
    tool_type: ToolType = "mcp"
    parameters: dict[str, Any] = field(default_factory=dict)
    required_fields: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_prompt_text(self) -> str:
        required = f"；必填参数: {', '.join(self.required_fields)}" if self.required_fields else ""
        server = f"；来源服务: {self.server_name}" if self.server_name else ""
        remote = f"；远端工具名: {self.remote_name}" if self.remote_name else ""
        tags = f"；标签: {', '.join(self.tags)}" if self.tags else ""
        return f"- {self.name}: {self.description}{server}{remote}{required}{tags}"


AVAILABLE_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="weather_lookup",
        description="查询目的地天气概况与出行提醒",
        server_name="gaode-weather",
        remote_name="maps_weather",
        parameters={
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "目的地城市"},
                "travel_date": {"type": "string", "description": "出发日期，可为空"},
            },
        },
        required_fields=["city"],
        tags=["weather", "planning"],
    ),
    ToolDefinition(
        name="poi_search",
        description="搜索景点、商圈、博物馆等兴趣点",
        server_name="gaode-poi",
        remote_name="maps_text_search",
        parameters={
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "目的地城市"},
                "keyword": {"type": "string", "description": "景点或兴趣点关键词"},
            },
        },
        required_fields=["city", "keyword"],
        tags=["poi", "attraction"],
    ),
    ToolDefinition(
        name="hotel_search",
        description="查询住宿候选项与价格区间",
        server_name="gaode-hotel",
        remote_name="maps_text_search",
        parameters={
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "目的地城市"},
                "keyword": {"type": "string", "description": "酒店区域或住宿偏好"},
            },
        },
        required_fields=["city"],
        tags=["hotel", "accommodation"],
    ),
    ToolDefinition(
        name="train_search",
        description="查询高铁或火车交通信息",
        server_name="cn-rail",
        remote_name="get-tickets",
        parameters={
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "出发地"},
                "destination": {"type": "string", "description": "目的地"},
                "travel_date": {"type": "string", "description": "出发日期，可为空"},
            },
        },
        required_fields=[],
        tags=["train", "transport"],
    ),
    ToolDefinition(
        name="calendar_lookup",
        description="查询指定出发日期的农历、干支与宜忌信息",
        server_name="lunar-calendar",
        remote_name="getChineseCalendar",
        parameters={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "日期，格式 YYYY-MM-DD"},
            },
        },
        required_fields=["date"],
        tags=["calendar", "lunar", "planning"],
    ),
    ToolDefinition(
        name="flight_search",
        description="查询机票候选班次与价格区间",
        server_name="flight-ticket",
        remote_name="searchFlightRoutes",
        parameters={
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "出发地"},
                "destination": {"type": "string", "description": "目的地"},
                "travel_date": {"type": "string", "description": "出发日期"},
            },
        },
        required_fields=[],
        tags=["flight", "transport"],
    ),
]


def get_tool_registry() -> dict[str, ToolDefinition]:
    return {tool.name: tool for tool in AVAILABLE_TOOLS}


def format_tool_registry_for_prompt() -> str:
    return "\n".join(tool.to_prompt_text() for tool in AVAILABLE_TOOLS)
