"""项目内 MCP 管理器 - 支持 SSE 与 Streamable HTTP。"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import DEFAULT_MCP_CONFIG_PATH, MCPServerConfig
from .registry import ToolDefinition, get_tool_registry

os.environ["NO_PROXY"] = os.environ.get("NO_PROXY", "") + ",modelscope.net,api-inference.modelscope.net"


@dataclass(slots=True)
class ToolExecutionResult:
    """单次工具执行结果。"""

    tool_name: str
    server_name: str | None
    success: bool
    content: str
    raw: dict[str, Any] | list[Any] | str | None = None
    error: str | None = None

    def to_summary(self) -> str:
        if self.success:
            return self.content.strip() or f"{self.tool_name} 调用成功。"
        return self.error or f"{self.tool_name} 调用失败。"


class MCPToolManager:
    """负责加载 MCP 服务配置并调用工具。"""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path) if config_path else DEFAULT_MCP_CONFIG_PATH
        self.registry = get_tool_registry()
        self.server_configs = self._load_server_configs()

    def _load_server_configs(self) -> dict[str, MCPServerConfig]:
        config_path = self.config_path
        if not config_path.exists():
            legacy_path = config_path.with_name("servers_config.json")
            config_path = legacy_path if legacy_path.exists() else config_path
        if not config_path.exists():
            return {}

        with config_path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)

        if isinstance(payload, dict) and isinstance(payload.get("mcp_servers"), list):
            servers = {
                item.get("name", f"server-{idx}"): item
                for idx, item in enumerate(payload["mcp_servers"])
                if isinstance(item, dict)
            }
        else:
            servers = payload.get("servers") or payload.get("mcpServers") or payload

        return {
            name: MCPServerConfig.from_dict(name, raw)
            for name, raw in servers.items()
            if isinstance(raw, dict)
        }

    def _run_async(self, coro) -> Any:
        try:
            asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=90)
        except RuntimeError:
            return asyncio.run(coro)

    def list_available_tools(self) -> list[ToolDefinition]:
        return list(self.registry.values())

    def is_tool_enabled(self, tool_name: str) -> bool:
        tool = self.registry.get(tool_name)
        if not tool or not tool.server_name:
            return False
        server = self.server_configs.get(tool.server_name)
        return bool(server and server.enabled and server.url)

    def get_tool_status(self, tool_name: str) -> tuple[bool, str]:
        tool = self.registry.get(tool_name)
        if not tool:
            return False, f"未知工具: {tool_name}"
        if not tool.server_name:
            return False, f"工具 {tool_name} 未绑定服务"
        server = self.server_configs.get(tool.server_name)
        if not server:
            return False, f"未找到服务配置: {tool.server_name}"
        if not server.enabled:
            return False, f"工具 {tool_name} 已在配置中禁用"
        if not server.url:
            return False, f"工具 {tool_name} 缺少服务 URL"
        return True, f"{tool_name} 已启用（{tool.server_name}）"

    def _get_server_for_tool(self, tool_name: str) -> str | None:
        tool = self.registry.get(tool_name)
        if tool and tool.server_name:
            return tool.server_name
        for name, cfg in self.server_configs.items():
            if cfg.tool_name == tool_name:
                return name
        return None

    @staticmethod
    def _looks_like_unknown_tool(content: str) -> bool:
        normalized = (content or "").strip().lower()
        return normalized.startswith("unknown tool:") or "unknown tool:" in normalized

    async def _create_server(self, server_name: str, server_cfg: MCPServerConfig):
        transport = (server_cfg.transport or "sse").lower()
        client_session_timeout_seconds = server_cfg.timeout_seconds or None
        common_kwargs = {
            "name": server_name,
            "client_session_timeout_seconds": client_session_timeout_seconds,
        }
        if transport == "streamable_http":
            from agents.mcp import MCPServerStreamableHttp

            return MCPServerStreamableHttp(
                params={
                    "url": server_cfg.url,
                    "headers": server_cfg.resolved_headers(),
                },
                **common_kwargs,
            )

        from agents.mcp import MCPServerSse

        return MCPServerSse(
            params={
                "url": server_cfg.url,
                "headers": server_cfg.resolved_headers(),
            },
            **common_kwargs,
        )

    async def _call_tool_once(
        self,
        tool_name: str,
        server_name: str,
        server_cfg: MCPServerConfig,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        tool = self.registry.get(tool_name)
        remote_tool_name = tool.remote_name if tool and tool.remote_name else tool_name
        try:
            server_ctx = await self._create_server(server_name, server_cfg)
            async with server_ctx as server:
                result = await server.call_tool(remote_tool_name, arguments=arguments)
                content = self._extract_result_content(result)
                if self._looks_like_unknown_tool(content):
                    return ToolExecutionResult(
                        tool_name=tool_name,
                        server_name=server_name,
                        success=False,
                        content=content,
                        raw=self._make_json_safe(result),
                        error=content.strip() or f"Unknown tool: {remote_tool_name}",
                    )
                return ToolExecutionResult(
                    tool_name=tool_name,
                    server_name=server_name,
                    success=True,
                    content=content,
                    raw=self._make_json_safe(result),
                )
        except Exception as exc:
            return ToolExecutionResult(
                tool_name=tool_name,
                server_name=server_name,
                success=False,
                content="",
                error=f"{type(exc).__name__}: {exc}",
            )

    def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        tool = self.registry.get(tool_name)
        if not tool:
            return ToolExecutionResult(
                tool_name=tool_name,
                server_name=None,
                success=False,
                content="",
                error=f"未知工具: {tool_name}",
            )

        normalized_arguments = self._normalize_arguments(tool_name, arguments)
        missing_fields = [f for f in tool.required_fields if not normalized_arguments.get(f)]
        if missing_fields:
            return ToolExecutionResult(
                tool_name=tool_name,
                server_name=tool.server_name,
                success=False,
                content="",
                error=f"缺少必填参数: {', '.join(missing_fields)}",
            )

        server_name = self._get_server_for_tool(tool_name)
        if not server_name:
            return ToolExecutionResult(
                tool_name=tool_name,
                server_name=None,
                success=False,
                content="",
                error=f"工具 {tool_name} 未绑定 MCP 服务",
            )

        server_cfg = self.server_configs.get(server_name)
        if not server_cfg or not server_cfg.enabled or not server_cfg.url:
            return ToolExecutionResult(
                tool_name=tool_name,
                server_name=server_name,
                success=False,
                content="",
                error=f"工具 {tool_name} 对应的 MCP 服务未启用",
            )

        return self._run_async(self._call_tool_once(tool_name, server_name, server_cfg, normalized_arguments))

    @staticmethod
    def _normalize_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(arguments or {})
        if tool_name == "train_search":
            return {
                "date": normalized.get("date") or normalized.get("travel_date") or "",
                "fromStation": normalized.get("fromStation") or normalized.get("origin") or "",
                "toStation": normalized.get("toStation") or normalized.get("destination") or "",
            }
        if tool_name == "flight_search":
            return {
                "departure_date": normalized.get("departure_date") or normalized.get("date") or normalized.get("travel_date") or "",
                "departure_city": normalized.get("departure_city") or normalized.get("origin") or "",
                "destination_city": normalized.get("destination_city") or normalized.get("arrival_city") or normalized.get("destination") or "",
            }
        return normalized

    @staticmethod
    def _extract_result_content(result: Any) -> str:
        if hasattr(result, "content") and result.content:
            first = result.content[0] if isinstance(result.content, list) else result.content
            if hasattr(first, "text"):
                return first.text or ""
            return str(first)
        if hasattr(result, "text"):
            return str(result.text or "")
        return json.dumps(MCPToolManager._make_json_safe(result), ensure_ascii=False, indent=2)

    @staticmethod
    def _make_json_safe(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, list):
            return [MCPToolManager._make_json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [MCPToolManager._make_json_safe(item) for item in value]
        if isinstance(value, dict):
            return {str(key): MCPToolManager._make_json_safe(item) for key, item in value.items()}
        if hasattr(value, "model_dump"):
            return MCPToolManager._make_json_safe(value.model_dump())
        if hasattr(value, "__dict__"):
            return MCPToolManager._make_json_safe(vars(value))
        return str(value)
