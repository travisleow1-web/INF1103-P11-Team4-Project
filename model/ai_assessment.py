import copy


class AIAssessment:
    """Placeholder until the AI manager has its own class. Wraps today's assessment dict."""

    def __init__(self, data):
        self.__data = copy.deepcopy(data)

    def to_dict(self):
        return copy.deepcopy(self.__data)

    def is_fallback(self):
        """True when the AI did not run for this shipment."""
        return self.__data.get("ai_status") == "FALLBACK"
