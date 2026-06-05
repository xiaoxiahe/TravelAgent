"""Local skill execution layer for travel planning tools."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from .registry import ToolDefinition, get_tool_registry

BASE_DIR = Path(__file__).resolve().parents[2]
LAOHUANGLI_SCRIPT = BASE_DIR / "scripts" / "huangli"
LAOHUANGLI_SCRIPT_ENV = "TRAVEL_AGENT_HUANGLI_SCRIPT"
ROLLINGGO_API_KEY_ENV = "ROLLINGGO_API_KEY"
AMAP_WEBSERVICE_KEY_ENV = "AMAP_WEBSERVICE_KEY"


@dataclass(slots=True)
class SkillExecutionResult:
    tool_name: str
    skill_name: str | None
    success: bool
    content: str
    raw: dict[str, Any] | list[Any] | str | None = None
    error: str | None = None

    def to_summary(self) -> str:
        if self.success:
            return self.content.strip() or f"{self.tool_name} 调用成功。"
        return self.error or f"{self.tool_name} 调用失败。"


class SkillRunner:
    """Executes local skill-backed tools while preserving existing tool names."""

    def __init__(self) -> None:
        self.registry = get_tool_registry()
        self.calendar_command = self._resolve_command_path(
            default_path=LAOHUANGLI_SCRIPT,
            env_var=LAOHUANGLI_SCRIPT_ENV,
        )

    def list_available_tools(self) -> list[ToolDefinition]:
        return list(self.registry.values())

    def is_tool_enabled(self, tool_name: str) -> bool:
        enabled, _ = self.get_tool_status(tool_name)
        return enabled

    def get_tool_status(self, tool_name: str) -> tuple[bool, str]:
        tool = self.registry.get(tool_name)
        if not tool:
            return False, f"未知工具: {tool_name}"

        if tool_name in {"weather_lookup", "poi_search"}:
            if not os.getenv(AMAP_WEBSERVICE_KEY_ENV):
                return False, f"缺少环境变量 {AMAP_WEBSERVICE_KEY_ENV}"
            return True, f"{tool_name} 已启用（{tool.skill_name}）"

        if tool_name in {"hotel_search", "flight_search"}:
            if not os.getenv(ROLLINGGO_API_KEY_ENV):
                return False, f"缺少环境变量 {ROLLINGGO_API_KEY_ENV}"
            return True, f"{tool_name} 已启用（{tool.skill_name}）"

        if tool_name == "calendar_lookup":
            if not self.calendar_command.exists():
                return False, f"未找到黄历脚本: {self.calendar_command}（可用环境变量 {LAOHUANGLI_SCRIPT_ENV} 覆盖）"
            return True, f"{tool_name} 已启用（{tool.skill_name}）"

        return True, f"{tool_name} 已启用（{tool.skill_name or 'local'}）"

    def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> SkillExecutionResult:
        tool = self.registry.get(tool_name)
        if not tool:
            return SkillExecutionResult(tool_name=tool_name, skill_name=None, success=False, content="", error=f"未知工具: {tool_name}")

        normalized_arguments = self._normalize_arguments(tool_name, arguments)
        missing_fields = [field for field in tool.required_fields if not normalized_arguments.get(field)]
        if missing_fields:
            return SkillExecutionResult(
                tool_name=tool_name,
                skill_name=tool.skill_name,
                success=False,
                content="",
                error=f"缺少必填参数: {', '.join(missing_fields)}",
            )

        enabled, status = self.get_tool_status(tool_name)
        if not enabled:
            return SkillExecutionResult(tool_name=tool_name, skill_name=tool.skill_name, success=False, content="", error=status)

        try:
            handler = getattr(self, f"_handle_{tool_name}")
        except AttributeError:
            return SkillExecutionResult(
                tool_name=tool_name,
                skill_name=tool.skill_name,
                success=False,
                content="",
                error=f"未实现的 skill 工具: {tool_name}",
            )

        try:
            payload = handler(normalized_arguments)
            return SkillExecutionResult(
                tool_name=tool_name,
                skill_name=tool.skill_name,
                success=True,
                content=self._build_summary(tool_name, payload),
                raw=payload,
            )
        except Exception as exc:
            return SkillExecutionResult(
                tool_name=tool_name,
                skill_name=tool.skill_name,
                success=False,
                content="",
                error=f"{type(exc).__name__}: {exc}",
            )

    @staticmethod
    def _resolve_command_path(default_path: Path, env_var: str) -> Path:
        raw = (os.getenv(env_var) or "").strip()
        return Path(raw) if raw else default_path

    @staticmethod
    def _normalize_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(arguments or {})
        if tool_name == "flight_search":
            normalized["origin"] = normalized.get("origin") or normalized.get("departure_city") or ""
            normalized["destination"] = normalized.get("destination") or normalized.get("arrival_city") or normalized.get("destination_city") or ""
            normalized["travel_date"] = normalized.get("travel_date") or normalized.get("date") or normalized.get("departure_date") or ""
            normalized["trip_type"] = normalized.get("trip_type") or "ONE_WAY"
            normalized["cabin_grade"] = normalized.get("cabin_grade") or "ECONOMY"
            normalized["adult_number"] = normalized.get("adult_number") or 1
            normalized["child_number"] = normalized.get("child_number") or 0
        elif tool_name == "hotel_search":
            check_in, check_out = SkillRunner._derive_hotel_dates(normalized.get("travel_date") or normalized.get("check_in_date") or "")
            normalized["destination"] = normalized.get("destination") or normalized.get("city") or ""
            normalized["check_in_date"] = normalized.get("check_in_date") or check_in
            normalized["check_out_date"] = normalized.get("check_out_date") or check_out
        return normalized

    @staticmethod
    def _derive_hotel_dates(travel_date: str) -> tuple[str, str]:
        if not travel_date:
            today = datetime.now().date()
            return today.isoformat(), (today + timedelta(days=1)).isoformat()
        start = datetime.strptime(travel_date, "%Y-%m-%d").date()
        return start.isoformat(), (start + timedelta(days=1)).isoformat()

    @staticmethod
    def _build_summary(tool_name: str, payload: Any) -> str:
        if tool_name == "weather_lookup":
            lives = payload.get("lives") or []
            if lives:
                first = lives[0]
                return f"{first.get('province', '')}{first.get('city', '')} 当前天气：{first.get('weather', '未知')}，气温 {first.get('temperature', '--')}℃，风向 {first.get('winddirection', '--')}。"
            return json.dumps(payload, ensure_ascii=False)

        if tool_name == "poi_search":
            pois = payload.get("pois") or []
            top = [f"{item.get('name', '未知')}（{item.get('address', '地址待补充')}）" for item in pois[:5]]
            if top:
                return "POI 搜索结果：" + "；".join(top)
            return json.dumps(payload, ensure_ascii=False)

        if tool_name == "hotel_search":
            hotels = payload.get("hotels") or []
            top = [f"{item.get('name', '未知酒店')}（评分 {item.get('starRating') or item.get('rating') or '待补充'}）" for item in hotels[:5]]
            if top:
                return "酒店候选：" + "；".join(top)
            return payload.get("stdout") or json.dumps(payload, ensure_ascii=False)

        if tool_name == "calendar_lookup":
            return payload.get("stdout") or json.dumps(payload, ensure_ascii=False)

        if tool_name == "flight_search":
            flights = payload.get("flights") or []
            top = []
            for item in flights[:5]:
                route = f"{item.get('departureCityName') or item.get('fromCityName') or '--'}->{item.get('arrivalCityName') or item.get('toCityName') or '--'}"
                airline = item.get("airlineName") or item.get("carrierName") or "未知航司"
                dep = item.get("departureTime") or item.get("takeoffTime") or "--"
                arr = item.get("arrivalTime") or item.get("landingTime") or "--"
                price = item.get("price") or item.get("settlePrice") or item.get("ticketPrice") or "待补充"
                top.append(f"{airline} {route} {dep}-{arr} ¥{price}")
            if top:
                return "机票候选：" + "；".join(top)
            return payload.get("stdout") or payload.get("summary") or json.dumps(payload, ensure_ascii=False)

        return json.dumps(payload, ensure_ascii=False)

    def _handle_weather_lookup(self, arguments: dict[str, Any]) -> dict[str, Any]:
        url = "https://restapi.amap.com/v3/weather/weatherInfo"
        response = requests.get(
            url,
            params={
                "key": os.getenv(AMAP_WEBSERVICE_KEY_ENV, ""),
                "city": arguments["city"],
                "extensions": "base",
                "output": "JSON",
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "1":
            raise ValueError(payload.get("info") or "高德天气查询失败")
        return payload

    def _handle_poi_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        url = "https://restapi.amap.com/v5/place/text"
        response = requests.get(
            url,
            params={
                "key": os.getenv(AMAP_WEBSERVICE_KEY_ENV, ""),
                "keywords": arguments["keyword"],
                "region": arguments["city"],
                "show_fields": "business,photos,indoor,navi,children,sites,discounts,events,opentime,deep_info",
                "page_size": 10,
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if str(payload.get("status")) not in {"1", "True", "true"}:
            raise ValueError(payload.get("info") or "高德 POI 查询失败")
        return payload

    def _handle_hotel_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        command = [
            self._resolve_cli_command("npx"),
            "--yes",
            "--package",
            "rollinggo@latest",
            "rollinggo",
            "search-hotels",
            "--origin-query",
            arguments.get("keyword") or f"{arguments['destination']} 酒店",
            "--place",
            arguments["destination"],
            "--place-type",
            "城市",
        ]
        output = self._run_subprocess(command, env={ROLLINGGO_API_KEY_ENV: os.getenv(ROLLINGGO_API_KEY_ENV, "")}, timeout=90)
        payload = self._try_parse_json(output["stdout"])
        if not isinstance(payload, dict):
            payload = {"stdout": output["stdout"], "stderr": output["stderr"], "hotels": []}
        return payload

    def _handle_calendar_lookup(self, arguments: dict[str, Any]) -> dict[str, Any]:
        target = datetime.strptime(arguments["date"], "%Y-%m-%d")
        command = [
            str(self.calendar_command),
            str(target.year),
            str(target.month),
            str(target.day),
            "12",
            "--profile",
            "market-folk-v1",
            "--format",
            "markdown",
        ]
        output = self._run_subprocess(command, timeout=90)
        return output

    def _handle_flight_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        airport_lookup = self._search_airports(arguments["origin"], arguments["destination"])
        command = [
            self._resolve_cli_command("rollinggo-flight"),
            "search-flights",
            "--api-key",
            os.getenv(ROLLINGGO_API_KEY_ENV, ""),
            "--from-city",
            airport_lookup["origin_code"],
            "--to-city",
            airport_lookup["destination_code"],
            "--from-date",
            arguments["travel_date"],
            "--trip-type",
            arguments["trip_type"],
            "--adult-number",
            str(arguments["adult_number"]),
            "--child-number",
            str(arguments["child_number"]),
            "--cabin-grade",
            arguments["cabin_grade"],
        ]
        output = self._run_subprocess(command, timeout=120)
        payload = self._try_parse_json(output["stdout"])
        if not isinstance(payload, dict):
            payload = {
                "stdout": output["stdout"],
                "stderr": output["stderr"],
                "summary": f"已调用 rollinggo-flight 查询 {arguments['origin']} -> {arguments['destination']}，请查看原始输出。",
                "flights": [],
            }
        payload.setdefault("origin_code", airport_lookup["origin_code"])
        payload.setdefault("destination_code", airport_lookup["destination_code"])
        payload.setdefault("travel_date", arguments["travel_date"])
        payload.setdefault("summary", f"已调用 rollinggo-flight 查询 {arguments['origin']} -> {arguments['destination']}。")
        return payload

    def _search_airports(self, origin: str, destination: str) -> dict[str, str]:
        origin_code = self._resolve_city_code(origin)
        destination_code = self._resolve_city_code(destination)
        return {"origin_code": origin_code, "destination_code": destination_code}

    def _resolve_city_code(self, keyword: str) -> str:
        command = [
            self._resolve_cli_command("rollinggo-flight"),
            "search-airports",
            "--api-key",
            os.getenv(ROLLINGGO_API_KEY_ENV, ""),
            "--keyword",
            keyword,
        ]
        output = self._run_subprocess(command, timeout=90)
        payload = self._try_parse_json(output["stdout"])
        code = self._extract_city_code(payload)
        if not code:
            raise ValueError(f"未能解析城市/机场代码：{keyword}")
        return code

    @staticmethod
    def _extract_city_code(payload: Any) -> str | None:
        if isinstance(payload, dict):
            for key in ("data", "items", "airports", "result", "results"):
                value = payload.get(key)
                code = SkillRunner._extract_city_code(value)
                if code:
                    return code
            for key in ("cityCode", "city_code", "city", "code"):
                value = payload.get(key)
                if isinstance(value, str) and len(value.strip()) == 3:
                    return value.strip().upper()
            return None
        if isinstance(payload, list):
            for item in payload:
                code = SkillRunner._extract_city_code(item)
                if code:
                    return code
        return None

    @staticmethod
    def _resolve_cli_command(command: str) -> str:
        if os.name == "nt" and not command.lower().endswith(".cmd"):
            return f"{command}.cmd"
        return command

    @staticmethod
    def _run_subprocess(command: list[str], env: dict[str, str] | None = None, timeout: int = 60) -> dict[str, str]:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=merged_env,
            cwd=str(BASE_DIR),
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or completed.stdout.strip() or "skill command failed"
            quoted = " ".join(shlex.quote(part) for part in command)
            raise RuntimeError(f"命令执行失败({completed.returncode}): {quoted}\n{stderr}")
        return {"stdout": completed.stdout.strip(), "stderr": completed.stderr.strip()}

    @staticmethod
    def _try_parse_json(raw_text: str) -> Any:
        text = (raw_text or "").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
