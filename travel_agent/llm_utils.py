"""LLM 辅助工具"""
from __future__ import annotations

import json
import re
import os
from typing import Any

import requests

from travel_agent.agent.config import get_config


def call_chat_llm(
    user_prompt: str,
    system_prompt: str = "你是一个专业的旅行规划顾问。",
    *,
    max_tokens: int = 512,
    temperature: float = 0.4,
    timeout: int = 60,
) -> str:
    cfg = get_config().llm
    api_key = cfg.api_key or os.getenv("DASHSCOPE_API_KEY", "")
    if not api_key:
        print("[ERROR] LLM API key missing: DASHSCOPE_API_KEY is not set")
        return ""

    url = f"{cfg.base_url}/chat/completions"
    payload = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        if not content:
            print("[WARN] LLM returned empty content")
        return content
    except Exception as e:
        print(f"[ERROR] LLM request failed: {type(e).__name__}: {e}")
        return ""


def safe_json_loads(text: str) -> Any:
    """从 LLM 输出中鲁棒提取 JSON（支持 markdown 块、嵌套文本）。"""
    if not text:
        return None

    # 优先尝试：markdown 代码块 ```json ... ```
    for match in re.finditer(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text):
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    # 其次：找出第一个 { 匹配到最后一个 }，逐层验证括号平衡
    first_brace = text.find("{")
    if first_brace == -1:
        return None

    # 从后往前找最后一个 }
    last_brace = text.rfind("}")
    if last_brace == -1 or last_brace <= first_brace:
        return None

    # 尝试从第一个 { 匹配到最后一个 }
    candidate = text[first_brace:last_brace + 1]

    # 括号平衡验证：扫描时忽略字符串内的 }
    depth = 0
    in_string = False
    escaped = False
    for ch in candidate:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"' and not escaped:
            in_string = not in_string
        elif not in_string:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1

    if depth == 0:
        try:
            return json.loads(candidate)
        except Exception:
            pass

    # 如果不平衡，尝试缩小范围（去掉首尾可能有问题的字符）
    for end in range(last_brace, first_brace, -1):
        for start in range(first_brace, end):
            sub = text[start:end + 1]
            if sub.count("{") == sub.count("}"):
                try:
                    return json.loads(sub)
                except Exception:
                    pass

    return None
