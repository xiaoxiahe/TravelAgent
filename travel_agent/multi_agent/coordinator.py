"""多智能体协调入口。"""
from __future__ import annotations

import json

from travel_agent.skills import SkillRunner

from .executor import MultiAgentExecutor
from .planner import build_planning_brief
from .state import CoordinatorResult, PlanningContext
from .summarizer import summarize_plan


class MultiAgentCoordinator:
    def __init__(self, tool_manager: SkillRunner | None = None) -> None:
        self.tool_manager = tool_manager or SkillRunner()
        self.executor = MultiAgentExecutor(self.tool_manager)

    def create_plan(self, context: PlanningContext) -> CoordinatorResult:
        planner_output = build_planning_brief(context)
        print(f"[Planner] reasoning: {planner_output.reasoning}")
        print(
            "[Planner] tool_arguments:\n"
            + json.dumps(planner_output.tool_arguments, ensure_ascii=False, indent=2)
        )
        execution_result = self.executor.run(planner_output, context)
        summary = summarize_plan(planner_output, execution_result, context)
        return CoordinatorResult(
            planner=planner_output,
            execution=execution_result,
            summary=summary,
        )
