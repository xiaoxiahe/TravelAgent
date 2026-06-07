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
            if tool_name == "calendar_lookup":
                self._run_calendar_lookup(arguments, result)
                continue

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

    def _run_calendar_lookup(self, arguments: dict, result: ExecutionResult) -> None:
        dates = arguments.get("dates") or []
        if not dates and arguments.get("date"):
            dates = [arguments["date"]]
        dates = [str(item).strip() for item in dates if str(item).strip()]
        if not dates:
            result.failed_tools.append(
                {
                    "tool": "calendar_lookup",
                    "status": "failed",
                    "summary": "缺少黄历查询日期",
                    "raw": None,
                }
            )
            result.warnings.append("calendar_lookup 缺少查询日期")
            return

        summaries: list[str] = []
        raw_items: list[dict] = []
        for date_value in dates[:3]:
            print(f"[Skill] calling tool=calendar_lookup args={json.dumps({'date': date_value}, ensure_ascii=False)}")
            execution = self.tool_manager.execute_tool("calendar_lookup", {"date": date_value})
            summary_preview = "\n".join((execution.to_summary() or "").splitlines()[:8]).strip()
            if execution.success:
                print(f"[Skill] success tool=calendar_lookup date={date_value}\n{summary_preview}")
                summaries.append(f"### {date_value}\n{execution.to_summary()}")
                raw_items.append({"date": date_value, "raw": execution.raw})
            else:
                print(f"[Skill] failed tool=calendar_lookup date={date_value}\n{summary_preview}")
                result.warnings.append(f"{date_value}: {execution.to_summary()}")

        if summaries:
            result.used_tools.append("calendar_lookup")
            result.tool_outputs.append(
                {
                    "tool": "calendar_lookup",
                    "summary": "\n\n".join(summaries),
                    "raw": raw_items,
                    "status": "success",
                }
            )
        else:
            result.failed_tools.append(
                {
                    "tool": "calendar_lookup",
                    "status": "failed",
                    "summary": "黄历查询全部失败",
                    "raw": raw_items or None,
                }
            )
            result.warnings.append("黄历查询全部失败")

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
            nights = max(1, int(profile.duration_days or 3) - 1)
            return {
                "city": destination,
                "destination": destination,
                "keyword": f"{destination} {accommodation_keyword}".strip(),
                "travel_date": travel_date,
                "stay_nights": nights,
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
