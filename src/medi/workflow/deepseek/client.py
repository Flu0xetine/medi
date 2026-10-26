"""DeepSeek JSON 模式的传输边界及客户端配置。"""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


def _read_json_content(response: Any) -> dict[str, Any]:
    """读取 DeepSeek JSON 模式返回值，并拒绝空响应或非对象 JSON。"""

    content = response.choices[0].message.content
    if not content:
        raise ValueError("DeepSeek返回了空内容")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"DeepSeek返回的内容不是合法JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError("DeepSeek返回的JSON顶层必须是对象")
    return data


class DeepSeekClient:
    """共享 DeepSeek API 客户端及 JSON 调用配置。"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        client: OpenAI | None = None,
    ) -> None:
        key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if client is None and not key:
            raise ValueError("未设置DEEPSEEK_API_KEY环境变量")
        if client is None:
            try:
                key.encode("ascii")
            except UnicodeEncodeError as exc:
                raise ValueError(
                    "DEEPSEEK_API_KEY包含中文或其他非ASCII字符；"
                    "请把.env中的占位文字替换为DeepSeek控制台生成的真实API密钥"
                ) from exc
            if key.startswith("在这里") or any(character.isspace() for character in key):
                raise ValueError(
                    "DEEPSEEK_API_KEY仍是占位内容或含有空格；"
                    "请在.env中填写真实API密钥"
                )

        self.model = model or os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL)
        self.client = client or OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)

    def json_completion(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """调用 DeepSeek Chat Completions，并要求返回 JSON 对象。"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=16_000,
            temperature=0,
            stream=False,
            extra_body={"thinking": {"type": "disabled"}},
        )
        return _read_json_content(response)
