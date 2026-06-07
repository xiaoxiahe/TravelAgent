"""项目内 MCP 配置。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MCP_CONFIG_PATH = BASE_DIR / "config" / "mcp_servers.json"
LEGACY_MCP_CONFIG_PATH = BASE_DIR / "config" / "servers_config.json"


@dataclass(slots=True)
class MCPServerConfig:
    """单个 MCP 服务配置。"""

    name: str
    transport: str = "sse"
    url: str = ""
    enabled: bool = False
    timeout_seconds: float = 20.0
    headers: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    tool_name: str = ""

    @classmethod
    def from_dict(cls, name: str, raw: dict[str, Any]) -> "MCPServerConfig":
        enabled = raw.get("enabled")
        if enabled is None:
            enabled = raw.get("required", False)
        return cls(
            name=name,
            transport=raw.get("transport", "sse"),
            url=str(raw.get("url", "")).replace(" ", ""),
            enabled=bool(enabled),
            timeout_seconds=float(raw.get("timeout_seconds", 20.0)),
            headers=dict(raw.get("headers", {})),
            metadata=dict(raw.get("metadata", {})),
            tool_name=raw.get("tool_name", ""),
        )

    def resolved_headers(self) -> dict[str, str]:
        resolved: dict[str, str] = {}
        for key, value in self.headers.items():
            if isinstance(value, str) and value.startswith("env:"):
                resolved[key] = os.getenv(value[4:], "")
            else:
                resolved[key] = value
        return {key: value for key, value in resolved.items() if value}
