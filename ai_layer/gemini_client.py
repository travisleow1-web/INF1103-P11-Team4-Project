import copy
import hashlib
import json
import logging
import random
import time
from typing import Optional
import requests
from .ai_service_error import AIServiceError
from .invalid_response_error import InvalidResponseError

log = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiClient:
    """Sends one prompt to Gemini and returns the JSON reply as a dict.

    The system prompt and response schema belong to the client. Timeouts, connection errors,
    429 and 5xx are retried with backoff; a missing key and other 4xx errors are not.
    """

    def __init__(self, api_key: Optional[str], model: str, system_prompt: str, response_schema: dict,
                 max_retries: int = 3, timeout: float = 40, http: Optional[requests.Session] = None):
        self.__api_key = api_key
        self.__model = model
        self.__system_prompt = system_prompt
        self.__response_schema = copy.deepcopy(response_schema)
        self.__max_retries = max_retries
        self.__timeout = timeout
        self.__http = http or requests.Session()

    def complete(self, prompt: str) -> dict:
        """Return the model's JSON reply. Raises AIServiceError or InvalidResponseError."""
        delay = 1.0
        for attempt in range(1, self.__max_retries + 1):
            try:
                return self.__send(prompt)
            except AIServiceError as error:
                if not error.retryable or attempt == self.__max_retries:
                    raise
                log.warning("Gemini attempt %d/%d failed: %s", attempt, self.__max_retries, error)
                time.sleep(delay + random.random())     # backoff with jitter
                delay *= 2
        raise AIServiceError("max_retries must be at least 1", retryable=False)

    def fingerprint(self) -> str:
        """Hash of the model, system prompt and schema. The cache uses it as its version."""
        text = self.__model + self.__system_prompt + json.dumps(self.__response_schema, sort_keys=True)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def __send(self, prompt: str) -> dict:
        if not self.__api_key:
            raise AIServiceError("GEMINI_API_KEY is not set", retryable=False)
        body = {
            "systemInstruction": {"parts": [{"text": self.__system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0, "seed": 0,
                "responseMimeType": "application/json",
                "responseSchema": self.__response_schema,
            },
        }
        try:
            reply = self.__http.post(GEMINI_URL.format(model=self.__model),
                                     headers={"x-goog-api-key": self.__api_key},
                                     json=body, timeout=self.__timeout)
        except (requests.Timeout, requests.ConnectionError) as error:
            raise AIServiceError(f"network problem: {error}", retryable=True) from error
        except requests.RequestException as error:
            raise AIServiceError(f"request failed: {error}", retryable=False) from error
        if reply.status_code == 429 or reply.status_code >= 500:
            raise AIServiceError(f"HTTP {reply.status_code}", retryable=True)
        if reply.status_code >= 400:
            raise AIServiceError(f"HTTP {reply.status_code}", retryable=False)
        try:
            return json.loads(reply.json()["candidates"][0]["content"]["parts"][0]["text"])
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise InvalidResponseError(f"unreadable model reply: {error}") from error
