import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class AIClientError(Exception):
    """Raised when the model client is misconfigured or the API call fails."""


def _require_env(name: str, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None or not str(value).strip():
        raise AIClientError(f"未检测到 {name}，请先在 .env 中配置。")
    return str(value).strip()


def get_deepseek_client() -> OpenAI:
    api_key = _require_env("DEEPSEEK_API_KEY")
    base_url = _require_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    return OpenAI(api_key=api_key, base_url=base_url)


def generate_text_with_deepseek(
    system_prompt: str,
    user_prompt: str,
    model: str = "deepseek-chat",
    temperature: float = 0.2,
    max_tokens: int = 1800,
) -> str:
    client = get_deepseek_client()
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise AIClientError("DeepSeek 返回为空。")
        return content.strip()
    except Exception as e:
        raise AIClientError(f"DeepSeek 调用失败：{e}") from e
