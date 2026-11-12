from .ai_error import AIError


class AIServiceError(AIError):
    """The model service could not answer: no key, a network problem or an HTTP error.

    `retryable` says whether trying again may help (timeouts, 429 and 5xx) or not (missing key, 4xx).
    """

    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.__retryable = retryable

    @property
    def retryable(self) -> bool:
        """True when the same request may succeed if sent again."""
        return self.__retryable
