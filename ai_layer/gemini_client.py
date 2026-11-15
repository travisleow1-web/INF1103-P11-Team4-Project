import copy
import hashlib
import json
import logging
import random
import time
from typing import Optional
import requests
from .ai_service_error import AIServiceError
from .ai_settings import GEMINI_TIMEOUT, MAX_RETRIES
from .invalid_response_error import InvalidResponseError

log = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
REASON_LIMIT = 200      # longest part of Google's error message kept in an AIServiceError


class GeminiClient:
    """Sends one prompt to Gemini and returns the JSON reply as a dict.

    Timeouts, connection errors, 429 and 5xx are retried with backoff; a missing key and other 4xx are not.
    """

    def __init__(self, api_key: Optional[str], model: str, system_prompt: str, response_schema: dict,
                 max_retries: int = MAX_RETRIES, timeout: float = GEMINI_TIMEOUT,
                 http: Optional[requests.Session] = None):
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1")
        self.__api_key, self.__model, self.__system_prompt = self.__clean_key(api_key), model, system_prompt
        self.__response_schema = copy.deepcopy(response_schema)
        self.__max_retries, self.__timeout = max_retries, timeout
        self.__http = http or requests.Session()    # shared by threads; the key goes per request in a header

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

    def fingerprint(self) -> str:
        """Hash of the model, system prompt and schema. The cache uses it as its version."""
        text = self.__model + self.__system_prompt + json.dumps(self.__response_schema, sort_keys=True)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def __clean_key(api_key: Optional[str]) -> Optional[str]:
        """The key without surrounding spaces, or None if it is empty or not plain printable ASCII."""
        key = (api_key or "").strip()
        return key if key and key.isascii() and key.isprintable() else None

    def __send(self, prompt: str) -> dict:
        if self.__api_key is None:
            raise AIServiceError("GEMINI_API_KEY is not set or invalid", retryable=False)
        body = {"systemInstruction": {"parts": [{"text": self.__system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "seed": 0, "responseMimeType": "application/json",
                                     "responseSchema": self.__response_schema}}
        try:
            reply = self.__http.post(GEMINI_URL.format(model=self.__model), headers={"x-goog-api-key": self.__api_key},
                                     json=body, timeout=self.__timeout)
        # Only the error's type goes in the message: some requests errors quote the header (the key).
        except (requests.Timeout, requests.ConnectionError, requests.exceptions.ChunkedEncodingError) as error:
            raise AIServiceError(f"network problem: {type(error).__name__}", retryable=True) from None
        except (requests.RequestException, ValueError, UnicodeError) as error:
            raise AIServiceError(f"request failed: {type(error).__name__}", retryable=False) from None
        if reply.status_code >= 400:
            raise AIServiceError(f"HTTP {reply.status_code}{self.__reason(reply)}",
                                 retryable=reply.status_code == 429 or reply.status_code >= 500)
        try:
            return json.loads(reply.json()["candidates"][0]["content"]["parts"][0]["text"])
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise InvalidResponseError(f"unreadable model reply: {error}") from error

    def __reason(self, reply: requests.Response) -> str:
        """Google's error status and message, e.g. ' (INVALID_ARGUMENT: API key not valid)', or '' if none.

        Shortened to REASON_LIMIT characters, and the key is masked just in case.
        """
        try:
            error = reply.json()["error"]
            parts = [str(error.get(name) or "").strip() for name in ("status", "message")]
        except (KeyError, TypeError, ValueError, AttributeError):
            return ""
        reason = " ".join(": ".join(part for part in parts if part).split())
        if not reason:
            return ""
        if self.__api_key:
            reason = reason.replace(self.__api_key, "***")
        return f" ({reason[:REASON_LIMIT - 3] + '...' if len(reason) > REASON_LIMIT else reason})"
