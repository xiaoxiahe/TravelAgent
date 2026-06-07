"""Local skill execution layer for travel planning tools."""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from .registry import ToolDefinition, get_tool_registry

BASE_DIR = Path(__file__).resolve().parents[2]
LAOHUANGLI_SKILL_DIR = BASE_DIR / ".agents" / "skills" / "lao-huangli"
LAOHUANGLI_CALC_SCRIPT = LAOHUANGLI_SKILL_DIR / "scripts" / "huangli_calc.py"
LAOHUANGLI_SCRIPT_ENV = "TRAVEL_AGENT_HUANGLI_SCRIPT"
LAOHUANGLI_PROFILE_ENV = "TRAVEL_AGENT_HUANGLI_PROFILE"
ROLLINGGO_API_KEY_ENV = "ROLLINGGO_API_KEY"
AMAP_WEBSERVICE_KEY_ENV = "AMAP_WEBSERVICE_KEY"
NODEJS_PATH_ENV = "TRAVEL_AGENT_NODEJS_DIR"

HOTEL_PLACE_ALIASES: list[tuple[str, str, str]] = [
    ("东京", "Tokyo", "JP"),
    ("日本", "Tokyo", "JP"),
    ("大阪", "Osaka", "JP"),
    ("京都", "Kyoto", "JP"),
    ("横滨", "Yokohama", "JP"),
    ("首尔", "Seoul", "KR"),
    ("韩国", "Seoul", "KR"),
    ("曼谷", "Bangkok", "TH"),
    ("泰国", "Bangkok", "TH"),
    ("新加坡", "Singapore", "SG"),
]

FLIGHT_SKIP_NAME_KEYWORDS = ("Rail", "Station", "Bus", "Harbour", "Ferry", "Off Line", "火车站", "Bus Station")
FLIGHT_PREFERRED_AIRPORTS = frozenset(
    {"PEK", "PKX", "PVG", "SHA", "CAN", "SZX", "CTU", "HGH", "ICN", "NRT", "HND", "KIX", "GMP", "BKK", "SIN", "TPE", "HKG"}
)

# RollingGo 机场检索可能漏掉同城次要机场，查询失败时需额外尝试
FLIGHT_ALT_AIRPORTS_BY_CITY: dict[str, list[str]] = {
    "SEL": ["ICN", "GMP"],
    "SHA": ["PVG", "SHA"],
    "BJS": ["PEK", "PKX"],
    "TYO": ["NRT", "HND"],
    "OSA": ["KIX", "ITM"],
}

FLIGHT_ALT_AIRPORTS_BY_PLACE: dict[str, list[str]] = {
    "首尔": ["ICN", "GMP"],
    "上海": ["PVG", "SHA"],
    "北京": ["PEK", "PKX"],
    "东京": ["NRT", "HND"],
    "大阪": ["KIX", "ITM"],
}

FLIGHT_COUNTRY_PREFIXES = (
    "日本", "韩国", "泰国", "新加坡", "马来西亚", "越南",
    "美国", "英国", "法国", "澳大利亚", "中国",
)

FLIGHT_KEYWORD_ALIASES: dict[str, str] = {
    "上海": "Shanghai",
    "北京": "Beijing",
    "广州": "Guangzhou",
    "深圳": "Shenzhen",
    "杭州": "Hangzhou",
    "成都": "Chengdu",
    "重庆": "Chongqing",
    "西安": "Xian",
    "南京": "Nanjing",
    "武汉": "Wuhan",
    "厦门": "Xiamen",
    "青岛": "Qingdao",
    "天津": "Tianjin",
    "东京": "Tokyo",
    "大阪": "Osaka",
    "京都": "Kyoto",
    "首尔": "Seoul",
    "釜山": "Busan",
    "曼谷": "Bangkok",
    "新加坡": "Singapore",
    "吉隆坡": "Kuala Lumpur",
    "香港": "Hong Kong",
    "台北": "Taipei",
    "伦敦": "London",
    "巴黎": "Paris",
    "纽约": "New York",
    "洛杉矶": "Los Angeles",
    "悉尼": "Sydney",
}


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
        self.calendar_skill_dir = self._resolve_calendar_skill_dir()
        self.calendar_script = self._resolve_calendar_script()

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
            if not self.calendar_script.exists():
                return False, (
                    f"未找到黄历脚本: {self.calendar_script}"
                    f"（可用环境变量 {LAOHUANGLI_SCRIPT_ENV} 覆盖）"
                )
            src_module = self.calendar_skill_dir / "src" / "lao_huangli"
            flat_module = self.calendar_skill_dir / "src" / "calendar_core.py"
            if not src_module.is_dir() and not flat_module.exists():
                return False, (
                    f"缺少老黄历核心模块: {src_module}"
                    f"（请将 calendar_core.py 等文件放在 src/lao_huangli/ 目录下）"
                )
            profile_file = self.calendar_skill_dir / "rules" / "profiles" / "market-folk-v1.json"
            if not profile_file.exists():
                return False, f"缺少黄历 profile 配置: {profile_file}"
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

    @classmethod
    def _resolve_calendar_skill_dir(cls) -> Path:
        raw = (os.getenv(LAOHUANGLI_SCRIPT_ENV) or "").strip()
        if raw:
            path = Path(raw)
            if path.is_file():
                if path.parent.name == "scripts":
                    return path.parent.parent
                return path.parent
            if path.is_dir():
                if (path / "scripts" / "huangli_calc.py").exists():
                    return path
                if path.name == "scripts" and (path / "huangli_calc.py").exists():
                    return path.parent
                return path
        return LAOHUANGLI_SKILL_DIR

    @classmethod
    def _resolve_calendar_script(cls) -> Path:
        skill_dir = cls._resolve_calendar_skill_dir()
        raw = (os.getenv(LAOHUANGLI_SCRIPT_ENV) or "").strip()
        if raw:
            path = Path(raw)
            if path.is_file():
                if path.suffix == ".py":
                    return path
                calc_script = path.parent / "huangli_calc.py"
                if calc_script.exists():
                    return calc_script
                return path
        calc_script = skill_dir / "scripts" / "huangli_calc.py"
        if calc_script.exists():
            return calc_script
        legacy = BASE_DIR / "scripts" / "huangli"
        if legacy.exists():
            return legacy
        return calc_script

    def _build_calendar_command(self, target: datetime) -> tuple[list[str], str]:
        profile = (os.getenv(LAOHUANGLI_PROFILE_ENV) or "market-folk-v1").strip() or "market-folk-v1"
        cwd = str(self.calendar_skill_dir)
        args_tail = [
            str(target.year),
            str(target.month),
            str(target.day),
            "12",
            "--profile",
            profile,
            "--format",
            "markdown",
        ]

        script = self.calendar_script
        if script.suffix == ".py":
            return [sys.executable, str(script), *args_tail], cwd

        if os.name == "nt":
            calc_script = script.parent / "huangli_calc.py"
            if calc_script.exists():
                return [sys.executable, str(calc_script), *args_tail], cwd

        return [str(script), *args_tail], cwd

    @staticmethod
    def _normalize_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(arguments or {})
        if tool_name == "flight_search":
            normalized["origin"] = SkillRunner._normalize_flight_place(
                normalized.get("origin") or normalized.get("departure_city") or ""
            )
            normalized["destination"] = SkillRunner._normalize_flight_place(
                normalized.get("destination") or normalized.get("arrival_city") or normalized.get("destination_city") or ""
            )
            travel_date = normalized.get("travel_date") or normalized.get("date") or normalized.get("departure_date") or ""
            normalized["travel_date"] = SkillRunner._coerce_future_date(str(travel_date)) if travel_date else ""
            normalized["trip_type"] = normalized.get("trip_type") or "ONE_WAY"
            normalized["cabin_grade"] = normalized.get("cabin_grade") or "ECONOMY"
            # 始终按 1 成人查询，仅展示班次/时刻/参考价，与同行人数无关
            normalized["adult_number"] = 1
            normalized["child_number"] = 0
        elif tool_name == "hotel_search":
            check_in, check_out = SkillRunner._derive_hotel_dates(normalized.get("travel_date") or normalized.get("check_in_date") or "")
            check_in = SkillRunner._coerce_future_date(check_in)
            check_out = SkillRunner._derive_checkout_date(check_in, normalized.get("stay_nights"))
            normalized["destination"] = normalized.get("destination") or normalized.get("city") or ""
            normalized["check_in_date"] = normalized.get("check_in_date") or check_in
            normalized["check_out_date"] = normalized.get("check_out_date") or check_out
            normalized["stay_nights"] = max(1, int(normalized.get("stay_nights") or SkillRunner._stay_nights_from_dates(check_in, check_out)))
        return normalized

    @staticmethod
    def _coerce_future_date(date_str: str) -> str:
        if not date_str:
            return ""
        try:
            dt = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
        except ValueError:
            return date_str
        today = datetime.now().date()
        candidate = dt.replace(year=today.year)
        if candidate < today:
            candidate = dt.replace(year=today.year + 1)
        return candidate.isoformat()

    @staticmethod
    def _stay_nights_from_dates(check_in: str, check_out: str) -> int:
        if not check_in or not check_out:
            return 1
        start = datetime.strptime(check_in, "%Y-%m-%d").date()
        end = datetime.strptime(check_out, "%Y-%m-%d").date()
        return max(1, (end - start).days)

    @staticmethod
    def _derive_checkout_date(check_in: str, stay_nights: Any) -> str:
        if not check_in:
            today = datetime.now().date()
            return (today + timedelta(days=1)).isoformat()
        nights = max(1, int(stay_nights or 1))
        start = datetime.strptime(check_in, "%Y-%m-%d").date()
        return (start + timedelta(days=nights)).isoformat()

    @staticmethod
    def _resolve_hotel_place(destination: str) -> tuple[str, str | None]:
        dest = (destination or "").strip()
        if not dest:
            return dest, None
        for keyword, place, country_code in HOTEL_PLACE_ALIASES:
            if keyword in dest:
                return place, country_code
        return dest.split()[0], None

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
            hotels = payload.get("hotels") or payload.get("hotelInformationList") or []
            message = str(payload.get("message") or "").strip()
            if "失败" in message or not hotels:
                return message or "酒店搜索无结果"
            top = []
            for item in hotels[:5]:
                name = item.get("name", "未知酒店")
                rating = item.get("starRating") or item.get("rating") or "待补充"
                price_info = item.get("price") or {}
                price = price_info.get("lowestPrice") or item.get("price") or "待补充"
                top.append(f"{name}（评分 {rating}，约 ¥{price}/晚）")
            if top:
                return "酒店候选：" + "；".join(top)
            return message or json.dumps(payload, ensure_ascii=False)

        if tool_name == "calendar_lookup":
            return payload.get("stdout") or json.dumps(payload, ensure_ascii=False)

        if tool_name == "flight_search":
            flights = payload.get("flights") or payload.get("flightInformationList") or []
            message = str(payload.get("message") or "").strip()
            if "失败" in message or not flights:
                return message or "机票搜索无结果"
            top = []
            for item in flights[:5]:
                segments = item.get("fromSegments") or item.get("segments") or []
                first_seg = segments[0] if segments else {}
                last_seg = segments[-1] if segments else first_seg
                if len(segments) > 1:
                    route_parts = [segments[0].get("depAirport") or "--"]
                    for seg in segments:
                        route_parts.append(seg.get("arrAirport") or "--")
                    route = "->".join(part for part in route_parts if part)
                    transfer = f"中转{len(segments) - 1}次"
                else:
                    dep_airport = first_seg.get("depAirport") or item.get("depAirport") or "--"
                    arr_airport = last_seg.get("arrAirport") or item.get("arrAirport") or "--"
                    route = f"{dep_airport}->{arr_airport}"
                    transfer = "直飞"
                airline = item.get("validatingCarrier") or item.get("airlineName") or item.get("carrierName") or "未知航司"
                flight_no = first_seg.get("flightNumber") or item.get("flightNo") or item.get("flightNumber") or ""
                if airline and flight_no.upper().startswith(str(airline).upper()):
                    flight_label = flight_no
                else:
                    flight_label = f"{airline}{flight_no}".strip()
                dep = (first_seg.get("depTime") or item.get("departureTime") or item.get("takeoffTime") or "--")[:16].replace("T", " ")
                arr = (last_seg.get("arrTime") or item.get("arrivalTime") or item.get("landingTime") or "--")[:16].replace("T", " ")
                price = item.get("totalAdultPrice") or item.get("settlePrice") or item.get("ticketPrice")
                if price is None:
                    price_info = item.get("price") or {}
                    price = price_info.get("settlePrice") or price_info.get("ticketPrice") or "待补充"
                label = f"{flight_label} {route}（{transfer}）{dep}-{arr} 参考价¥{price}".strip()
                top.append(label)
            if top:
                origin = payload.get("origin_airport") or payload.get("origin_code") or ""
                destination = payload.get("destination_airport") or payload.get("destination_code") or ""
                prefix = f"{origin}->{destination} " if origin and destination else ""
                note = payload.get("price_note") or "以下为1成人参考价，仅展示班次与时刻"
                return prefix + "机票候选（" + note + "）：" + "；".join(top)
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
        place, country_code = self._resolve_hotel_place(arguments["destination"])
        command = [
            self._resolve_cli_command("npx"),
            "--yes",
            "--package",
            "rollinggo@latest",
            "rollinggo",
            "search-hotels",
            "--origin-query",
            arguments.get("keyword") or f"{place} hotel",
            "--place",
            place,
            "--place-type",
            "城市",
            "--check-in-date",
            arguments["check_in_date"],
            "--stay-nights",
            str(arguments.get("stay_nights") or 1),
            "--format",
            "json",
        ]
        if country_code:
            command.extend(["--country-code", country_code])
        output = self._run_subprocess(command, env={ROLLINGGO_API_KEY_ENV: os.getenv(ROLLINGGO_API_KEY_ENV, "")}, timeout=90)
        payload = self._try_parse_json(output["stdout"])
        if not isinstance(payload, dict):
            payload = {"stdout": output["stdout"], "stderr": output["stderr"], "hotels": []}
        message = str(payload.get("message") or "").strip()
        hotels = payload.get("hotelInformationList") or payload.get("hotels") or []
        if "失败" in message or not hotels:
            raise RuntimeError(message or "酒店搜索无结果")
        return payload

    def _handle_calendar_lookup(self, arguments: dict[str, Any]) -> dict[str, Any]:
        target = datetime.strptime(arguments["date"], "%Y-%m-%d")
        command, cwd = self._build_calendar_command(target)
        output = self._run_subprocess(command, timeout=90, cwd=cwd)
        return output

    def _build_rollinggo_flight_command(self, *subcommand_args: str) -> list[str]:
        return [
            self._resolve_cli_command("npx"),
            "--yes",
            "--package",
            "rollinggo-flight@latest",
            "rollinggo-flight",
            *subcommand_args,
        ]

    @staticmethod
    def _normalize_flight_place(keyword: str) -> str:
        text = (keyword or "").strip()
        if not text:
            return text
        for cn in sorted(FLIGHT_KEYWORD_ALIASES.keys(), key=len, reverse=True):
            if cn in text:
                return cn
        stripped = text
        for prefix in FLIGHT_COUNTRY_PREFIXES:
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix):].strip()
                break
        for cn in sorted(FLIGHT_KEYWORD_ALIASES.keys(), key=len, reverse=True):
            if cn in stripped or stripped == cn:
                return cn
        return stripped or text

    @staticmethod
    def _resolve_flight_keyword(keyword: str) -> str:
        text = SkillRunner._normalize_flight_place(keyword)
        if re.search(r"[\u4e00-\u9fff]", text):
            return text
        for cn, en in FLIGHT_KEYWORD_ALIASES.items():
            if cn in text or text.lower() == en.lower():
                return cn
        return text

    def _handle_flight_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        route = self._resolve_route_airports(arguments["origin"], arguments["destination"])
        strategies = self._build_flight_search_strategies(
            arguments["origin"],
            arguments["destination"],
            route,
        )

        last_error = "机票搜索无结果"
        for mode, route_args in strategies:
            command = self._build_flight_search_command(
                travel_date=arguments["travel_date"],
                trip_type=arguments["trip_type"],
                cabin_grade=arguments["cabin_grade"],
                **route_args,
            )
            output = self._run_subprocess(
                command,
                env={ROLLINGGO_API_KEY_ENV: os.getenv(ROLLINGGO_API_KEY_ENV, "")},
                timeout=120,
            )
            payload = self._parse_flight_payload(output["stdout"])
            if payload:
                payload.update(route)
                payload["travel_date"] = arguments["travel_date"]
                payload["query_mode"] = mode
                payload["query_origin_airport"] = route_args.get("from_airport") or route["origin_airport"]
                payload["query_destination_airport"] = route_args.get("to_airport") or route["destination_airport"]
                payload["price_note"] = "1成人参考价，班次与时刻供选，与出行人数无关"
                return payload
            parsed = self._try_parse_json(output["stdout"])
            if isinstance(parsed, dict):
                last_error = str(parsed.get("message") or last_error)

        raise RuntimeError(last_error)

    def _build_flight_search_strategies(
        self,
        origin: str,
        destination: str,
        route: dict[str, str],
    ) -> list[tuple[str, dict[str, str]]]:
        """构建航班查询策略；部分航线（如上海→仁川）需尝试同城多机场组合。"""
        origin_airports = self._expand_airport_codes(
            self._list_airport_codes(origin, route.get("origin_airport")),
            route.get("origin_code"),
            origin,
        )
        dest_airports = self._expand_airport_codes(
            self._list_airport_codes(destination, route.get("destination_airport")),
            route.get("destination_code"),
            destination,
        )

        strategies: list[tuple[str, dict[str, str]]] = []
        seen: set[tuple[str, str]] = set()
        for from_airport in origin_airports:
            for to_airport in dest_airports:
                key = (from_airport, to_airport)
                if key in seen:
                    continue
                seen.add(key)
                strategies.append(("airport", {"from_airport": from_airport, "to_airport": to_airport}))

        if route.get("origin_code") and route.get("destination_code"):
            strategies.append(
                (
                    "city",
                    {"from_city": route["origin_code"], "to_city": route["destination_code"]},
                )
            )
        return strategies

    def _list_airport_codes(self, keyword: str, preferred: str | None = None, limit: int = 4) -> list[str]:
        airports = self._fetch_airport_list(keyword)
        scored: list[tuple[int, str]] = []
        seen: set[str] = set()
        for item in airports:
            airport_code = str(item.get("airportCode") or "").strip().upper()
            if len(airport_code) != 3 or airport_code in seen:
                continue
            name = str(item.get("airportName") or item.get("airport_name") or "")
            if any(skip in name for skip in FLIGHT_SKIP_NAME_KEYWORDS):
                continue
            score = 0
            if airport_code in FLIGHT_PREFERRED_AIRPORTS:
                score += 20
            if airport_code == (preferred or "").upper():
                score += 30
            if "国际" in name or "International" in name:
                score += 10
            if "机场" in name or "Airport" in name:
                score += 5
            if "空军" in name or "Air Base" in name or "Base" in name:
                score -= 15
            scored.append((score, airport_code))
            seen.add(airport_code)
        scored.sort(key=lambda item: item[0], reverse=True)
        codes = [code for _, code in scored[:limit]]
        if preferred and preferred.upper() not in codes:
            codes.insert(0, preferred.upper())
        return codes or ([preferred.upper()] if preferred else [])

    def _expand_airport_codes(self, codes: list[str], city_code: str | None, keyword: str) -> list[str]:
        extras: list[str] = []
        extras.extend(FLIGHT_ALT_AIRPORTS_BY_CITY.get((city_code or "").upper(), []))
        normalized = self._normalize_flight_place(keyword)
        extras.extend(FLIGHT_ALT_AIRPORTS_BY_PLACE.get(normalized, []))
        extras.extend(FLIGHT_ALT_AIRPORTS_BY_PLACE.get(keyword, []))

        merged: list[str] = []
        seen: set[str] = set()
        for code in [*codes, *extras]:
            airport_code = code.upper()
            if airport_code in seen:
                continue
            seen.add(airport_code)
            merged.append(airport_code)
        return merged

    def _build_flight_search_command(
        self,
        *,
        travel_date: str,
        trip_type: str,
        cabin_grade: str,
        from_city: str = "",
        to_city: str = "",
        from_airport: str = "",
        to_airport: str = "",
    ) -> list[str]:
        command = [
            "search-flights",
            "--api-key",
            os.getenv(ROLLINGGO_API_KEY_ENV, ""),
            "--from-date",
            travel_date,
            "--trip-type",
            trip_type,
            "--adult-number",
            "1",
            "--child-number",
            "0",
            "--cabin-grade",
            cabin_grade,
            "--format",
            "json",
        ]
        if from_airport and to_airport:
            command.extend(["--from-airport", from_airport, "--to-airport", to_airport])
        elif from_city and to_city:
            command.extend(["--from-city", from_city, "--to-city", to_city])
        else:
            raise ValueError("缺少航班查询起降地参数")
        return self._build_rollinggo_flight_command(*command)

    @staticmethod
    def _parse_flight_payload(stdout: str) -> dict[str, Any] | None:
        payload = SkillRunner._try_parse_json_static(stdout)
        if not isinstance(payload, dict):
            return None
        message = str(payload.get("message") or "").strip()
        flights = payload.get("flightInformationList") or payload.get("flights") or []
        if "失败" in message or not flights:
            return None
        return payload

    @staticmethod
    def _try_parse_json_static(text: str) -> Any:
        text = (text or "").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def _resolve_route_airports(self, origin: str, destination: str) -> dict[str, str]:
        origin_info = self._lookup_primary_airport(origin)
        destination_info = self._lookup_primary_airport(destination)
        return {
            "origin_code": origin_info["city_code"],
            "origin_airport": origin_info["airport_code"],
            "origin_name": origin_info["airport_name"],
            "destination_code": destination_info["city_code"],
            "destination_airport": destination_info["airport_code"],
            "destination_name": destination_info["airport_name"],
        }

    def _lookup_primary_airport(self, keyword: str) -> dict[str, str]:
        airports = self._fetch_airport_list(keyword)
        if not airports:
            raise ValueError(f"未能解析城市/机场代码：{keyword}")
        city_code, airport_code, airport_name = self._pick_primary_airport(airports)
        if not city_code and not airport_code:
            raise ValueError(f"未能解析城市/机场代码：{keyword}")
        return {
            "city_code": city_code or "",
            "airport_code": airport_code or "",
            "airport_name": airport_name or keyword,
        }

    def _fetch_airport_list(self, keyword: str) -> list[dict[str, Any]]:
        command = self._build_rollinggo_flight_command(
            "search-airports",
            "--api-key",
            os.getenv(ROLLINGGO_API_KEY_ENV, ""),
            "--keyword",
            self._resolve_flight_keyword(keyword),
            "--format",
            "json",
        )
        output = self._run_subprocess(
            command,
            env={ROLLINGGO_API_KEY_ENV: os.getenv(ROLLINGGO_API_KEY_ENV, "")},
            timeout=90,
        )
        payload = self._try_parse_json(output["stdout"])
        if not isinstance(payload, dict):
            return []
        airports = payload.get("airPortInformationList") or payload.get("airports") or []
        return [item for item in airports if isinstance(item, dict)]

    @staticmethod
    def _pick_primary_airport(airports: list[dict[str, Any]]) -> tuple[str, str, str]:
        scored: list[tuple[int, str, str, str]] = []
        for item in airports:
            airport_code = str(item.get("airportCode") or "").strip().upper()
            city_code = str(item.get("cityCode") or "").strip().upper()
            name = str(item.get("airportName") or item.get("airport_name") or "")
            if len(airport_code) != 3:
                continue
            if any(keyword in name for keyword in FLIGHT_SKIP_NAME_KEYWORDS):
                continue
            score = 0
            if airport_code in FLIGHT_PREFERRED_AIRPORTS:
                score += 20
            if "国际" in name or "International" in name:
                score += 10
            if "机场" in name or "Airport" in name:
                score += 5
            if "空军" in name or "Air Base" in name or "Base" in name:
                score -= 15
            scored.append((score, city_code, airport_code, name))
        scored.sort(key=lambda item: item[0], reverse=True)
        if scored:
            _, city_code, airport_code, name = scored[0]
            return city_code, airport_code, name
        first = airports[0]
        return (
            str(first.get("cityCode") or "").strip().upper(),
            str(first.get("airportCode") or "").strip().upper(),
            str(first.get("airportName") or ""),
        )

    def _search_airports(self, origin: str, destination: str) -> dict[str, str]:
        return self._resolve_route_airports(origin, destination)

    def _resolve_city_code(self, keyword: str) -> str:
        info = self._lookup_primary_airport(keyword)
        return info["city_code"] or info["airport_code"]

    @staticmethod
    def _extract_city_code(payload: Any) -> str | None:
        if isinstance(payload, dict):
            for key in ("airPortInformationList", "data", "items", "airports", "result", "results"):
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
    def _resolve_nodejs_dir() -> str:
        """Prefer a system Node.js install over older conda-shipped Node versions."""
        explicit = (os.getenv(NODEJS_PATH_ENV) or "").strip()
        if explicit:
            path = Path(explicit)
            if path.is_file():
                return str(path.parent)
            if path.is_dir():
                return str(path)

        if os.name != "nt":
            return ""

        candidates = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs",
            Path(os.environ.get("LocalAppData", "")) / "Programs" / "node",
        ]
        for candidate in candidates:
            if (candidate / "node.exe").exists():
                return str(candidate)
        return ""

    @classmethod
    def _prepare_subprocess_env(cls, env: dict[str, str] | None = None) -> dict[str, str]:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        if os.name == "nt":
            merged_env.setdefault("PYTHONUTF8", "1")

        nodejs_dir = cls._resolve_nodejs_dir()
        if nodejs_dir:
            path_key = merged_env.get("PATH", os.environ.get("PATH", ""))
            merged_env["PATH"] = f"{nodejs_dir}{os.pathsep}{path_key}"
        return merged_env

    @classmethod
    def _run_subprocess(
        cls,
        command: list[str],
        env: dict[str, str] | None = None,
        timeout: int = 60,
        cwd: str | None = None,
    ) -> dict[str, str]:
        merged_env = cls._prepare_subprocess_env(env)
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=merged_env,
            cwd=cwd or str(BASE_DIR),
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
