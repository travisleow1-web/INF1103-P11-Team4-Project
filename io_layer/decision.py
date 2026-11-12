import copy


class Decision:
    """Placeholder until the Logic manager has its own class. Wraps today's decision dict."""

    def __init__(self, data):
        self.__data = copy.deepcopy(data)

    def to_dict(self):
        return copy.deepcopy(self.__data)
