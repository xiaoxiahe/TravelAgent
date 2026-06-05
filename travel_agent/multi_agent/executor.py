"""多智能体 Executor。"""
from __future__ import annotations

import json

from travel_agent.skills import SkillRunner

from .state import ExecutionResult, PlannerOutput, PlanningContext


class MultiAgentExecutor:
    def __init__(self, tool_manager: SkillRunner) -> None:
        self.tool_manager = tool_manager

    def run(self, planner_output: PlannerOutput, context: PlanningContext) -> ExecutionResult:
        profile = context.profile
        result = ExecutionResult()

        for tool_name in planner_output.required_tools:
            enabled, status_text = self.tool_manager.get_tool_status(tool_name)
            if not enabled:
                print(f"[Skill] skip tool={tool_name} reason={status_text}")
                result.warnings.append(status_text)
                result.failed_tools.append(
                    {
                        "tool": tool_name,
                        "status": "skipped",
                        "summary": status_text,
                        "raw": None,
                    }
                )
                continue

            arguments = planner_output.tool_arguments.get(tool_name) or self._build_arguments(tool_name, profile)
            print(f"[Skill] calling tool={tool_name} args={json.dumps(arguments, ensure_ascii=False)}")
            execution = self.tool_manager.execute_tool(tool_name, arguments)
            summary_preview = "\n".join((execution.to_summary() or "").splitlines()[:10]).strip()
            raw_preview = self._serialize_for_log(execution.raw)
            if execution.success:
                print(f"[Skill] success tool={tool_name}\n{summary_preview}")
                if raw_preview:
                    print(f"[Skill] raw tool={tool_name}\n{raw_preview}")
                result.used_tools.append(tool_name)
                result.tool_outputs.append(
                    {
                        "tool": tool_name,
                        "summary": execution.to_summary(),
                        "raw": execution.raw,
                        "status": "success",
                    }
                )
            else:
                print(f"[Skill] failed tool={tool_name}\n{summary_preview}")
                if raw_preview:
                    print(f"[Skill] raw tool={tool_name}\n{raw_preview}")
                result.failed_tools.append(
                    {
                        "tool": tool_name,
                        "summary": execution.to_summary(),
                        "raw": execution.raw,
                        "status": "failed",
                    }
                )
                result.warnings.append(execution.to_summary())

        return result

    @staticmethod
    def _serialize_for_log(raw: object) -> str:
        if raw is None:
            return ""
        if isinstance(raw, str):
            return raw.strip()
        try:
            return json.dumps(raw, ensure_ascii=False, indent=2)
        except TypeError:
            return str(raw)

    @staticmethod
    def _build_arguments(tool_name: str, profile):
        destination = (profile.destination or "").strip()
        origin = (profile.origin or "").strip()
        travel_date = (profile.travel_date or "").strip()
        accommodation_keyword = (profile.accommodation_preference.type or "酒店").strip() or "酒店"

        if tool_name == "weather_lookup":
            return {"city": destination, "travel_date": travel_date}
        if tool_name == "poi_search":
            keyword = profile.must_visit[0] if profile.must_visit else f"{destination} 景点"
            return {"city": destination, "keyword": keyword.strip()}
        if tool_name == "hotel_search":
            return {
                "city": destination,
                "destination": destination,
                "keyword": f"{destination} {accommodation_keyword}".strip(),
                "travel_date": travel_date,
            }
        if tool_name == "calendar_lookup":
            return {"date": travel_date}
        if tool_name == "flight_search":
            return {
                "origin": origin or "出发地待补充",
                "destination": destination,
                "travel_date": travel_date,
                "trip_type": "ONE_WAY",
                "cabin_grade": "ECONOMY",
            }
        return {"city": destination}
