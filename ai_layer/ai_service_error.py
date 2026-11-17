from .ai_error import AIError


class AIServiceError(AIError):
    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.__retryable = retryable

    @property
    def retryable(self) -> bool:
        return self.__retryable
