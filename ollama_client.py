"""
Ollama Cloud client for AskBot AI.

This replaces the old local-only Ollama usage (http://localhost:11434) with
Ollama's hosted Cloud API (https://ollama.com/api), authenticated with an
API key instead of running a local model.

Docs: https://docs.ollama.com/api/authentication
Direct cloud calls use plain model names (no "-cloud" suffix), e.g. "gpt-oss:20b".
"""

import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "https://ollama.com").rstrip("/")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "").strip()
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gpt-oss:20b").strip()
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_TIMEOUT_SECONDS = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "120"))

SYSTEM_PROMPT = (
    "You are AskBot AI, a friendly and encouraging placement and interview "
    "preparation assistant for college students. Answer questions about "
    "programming, computer science fundamentals, aptitude, cloud computing, "
    "computer networks, and HR/behavioural interview topics. Keep answers "
    "clear, accurate, well-structured, and practical for someone preparing "
    "for a campus placement interview. Prefer concise explanations with "
    "examples over long essays."
)


class OllamaError(Exception):
    """Raised whenever Ollama Cloud can't be reached or is misconfigured."""


def is_configured():
    return bool(OLLAMA_API_KEY)


def stream_ollama_response(user_message):
    """
    Calls Ollama Cloud's /api/generate endpoint with streaming enabled and
    returns a generator that yields text chunks as they arrive.

    Raises OllamaError immediately (before any generator is returned) if the
    key is missing or the initial connection/auth fails, so callers can
    return a clean error response instead of starting a broken stream.
    """
    if not OLLAMA_API_KEY:
        raise OllamaError(
            "OLLAMA_API_KEY is not configured on the server. "
            "Add it to your .env file or Render environment variables."
        )

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": user_message,
        "system": SYSTEM_PROMPT,
        "stream": True,
    }

    headers = {
        "Authorization": f"Bearer {OLLAMA_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            OLLAMA_GENERATE_URL,
            json=payload,
            headers=headers,
            stream=True,
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise OllamaError(f"Could not reach Ollama Cloud: {exc}") from exc

    def _generator():
        try:
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue

                if data.get("error"):
                    yield f"\n\n[Ollama Cloud error: {data['error']}]"
                    break

                text = data.get("response", "")
                if text:
                    yield text

                if data.get("done", False):
                    break
        finally:
            response.close()

    return _generator()

