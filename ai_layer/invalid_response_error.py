from .ai_error import AIError


class InvalidResponseError(AIError):
    """The model answered, but the reply is unreadable or breaks the agreed schema."""
