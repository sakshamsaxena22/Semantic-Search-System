"""
Groq API client with automatic retry and rate-limit handling.
"""
import logging
import os
import re
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load .env from the project root regardless of cwd
_ROOT = Path(__file__).resolve().parents[3]  # SemanticSearchSystem/
load_dotenv(dotenv_path=_ROOT / ".env", override=True)

MAX_PROMPT_CHARS = 6000   # ~1500 tokens — safe for llama3-8b 8k context
_MAX_RETRIES     = 6
_RETRY_BASE_SEC  = 3      # exponential backoff: 3s, 6s, 12s...

_llm_cache = {}


def groq_call_llm(prompt: str) -> str:
    """
    Call the Groq LLM with automatic retry on 429 rate-limit responses.

    Truncates overly long prompts to avoid 400 errors on context overflow.
    Raises RuntimeError on unrecoverable errors.
    """
    # Check cache first to avoid rate-limiting on duplicate requests
    if prompt in _llm_cache:
        logging.info("Returning cached LLM response")
        return _llm_cache[prompt]

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        raise ValueError("GROQ_API_KEY is not set. Add your key to the .env file.")

    # Truncate prompt to avoid 400 errors
    if len(prompt) > MAX_PROMPT_CHARS:
        logging.warning(
            "Prompt too long (%d chars); truncating to %d.", len(prompt), MAX_PROMPT_CHARS
        )
        prompt = prompt[:MAX_PROMPT_CHARS] + "\n\n[...context truncated...]\n"

    url     = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    body    = {
        "model":      "llama-3.1-8b-instant",
        "messages":   [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
    }

    last_error = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = requests.post(url, headers=headers, json=body, timeout=30)

            # Rate limit — back off and retry
            if response.status_code == 429:
                wait = _RETRY_BASE_SEC * (2 ** (attempt - 1))
                # Check for standard Retry-After header
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait = float(retry_after)
                    except ValueError:
                        pass
                else:
                    # Attempt to parse retry duration from JSON error message
                    try:
                        err_json = response.json()
                        msg = err_json.get("error", {}).get("message", "")
                        match = re.search(r"try again in (\d+(\.\d+)?)s", msg)
                        if match:
                            wait = float(match.group(1)) + 0.5  # Add small buffer
                    except Exception:
                        pass

                logging.warning("Groq 429 rate limit on attempt %d — waiting %.2fs", attempt, wait)
                time.sleep(wait)
                last_error = f"Rate limited after {attempt} attempt(s)"
                continue

            response.raise_for_status()
            data = response.json()
            if "choices" in data and data["choices"]:
                content = data["choices"][0]["message"]["content"]
                _llm_cache[prompt] = content
                return content
            raise RuntimeError(f"Unexpected Groq response: {data}")

        except requests.HTTPError as e:
            # Non-429 HTTP errors are not retried
            raise
        except requests.RequestException as e:
            wait = _RETRY_BASE_SEC * (2 ** (attempt - 1))
            logging.warning("Groq request error attempt %d: %s — retrying in %ds", attempt, e, wait)
            time.sleep(wait)
            last_error = str(e)

    raise RuntimeError(f"Groq call failed after {_MAX_RETRIES} retries: {last_error}")
