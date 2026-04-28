import requests
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root regardless of cwd
_ROOT = Path(__file__).resolve().parents[3]  # SemanticSearchSystem/
load_dotenv(dotenv_path=_ROOT / ".env", override=True)

MAX_PROMPT_CHARS = 6000  # ~1500 tokens — safe for llama3-8b-8192 8k context


def groq_call_llm(prompt: str) -> str:
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        raise ValueError(
            "GROQ_API_KEY is not set. Add your key to the .env file."
        )

    # Truncate prompt to avoid 400 errors
    if len(prompt) > MAX_PROMPT_CHARS:
        logging.warning(
            f"Prompt too long ({len(prompt)} chars); truncating to {MAX_PROMPT_CHARS}."
        )
        prompt = prompt[:MAX_PROMPT_CHARS] + "\n\n[...context truncated...]\n"

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    body = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
    }
    response = requests.post(url, headers=headers, json=body, timeout=30)
    response.raise_for_status()   # raises HTTPError — let caller handle
    data = response.json()
    if "choices" in data and data["choices"]:
        return data["choices"][0]["message"]["content"]
    raise RuntimeError(f"Unexpected Groq response: {data}")
