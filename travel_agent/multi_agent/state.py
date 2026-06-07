"""多智能体桥接层的数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from travel_agent.models.user_profile import UserProfile


@dataclass(slots=True)
class PlannerOutput:
    destination: str
    duration_text: str
    budget_text: str
    traveler_summary: str
    constraints: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    tool_arguments: dict[str, dict[str, Any]] = field(default_factory=dict)
    reasoning: str = ""


@dataclass(slots=True)
class ExecutionResult:
    used_tools: list[str] = field(default_factory=list)
    tool_outputs: list[dict[str, Any]] = field(default_factory=list)
    failed_tools: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SummaryResult:
    content: str
    structured_plan: dict[str, Any]


@dataclass(slots=True)
class CoordinatorResult:
    planner: PlannerOutput
    execution: ExecutionResult
    summary: SummaryResult


@dataclass(slots=True)
class PlanningContext:
    profile: UserProfile
    conversation_summary: str = ""
    rag_summary: str = ""
    references: list[dict[str, Any]] = field(default_factory=list)
