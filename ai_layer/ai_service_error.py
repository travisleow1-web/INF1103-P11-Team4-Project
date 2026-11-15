from .ai_error import AIError


class AIServiceError(AIError):
    """The model service could not answer: no key, a network problem or an HTTP error."""

    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.__retryable = retryable

    @property
    def retryable(self) -> bool:
        """True when trying again may help (timeouts, 429 and 5xx); False for a missing key or other 4xx."""
        return self.__retryable
