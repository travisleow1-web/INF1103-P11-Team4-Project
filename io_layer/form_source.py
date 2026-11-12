from .shipment_source import ShipmentSource


class FormSource(ShipmentSource):
    def __init__(self, fields):
        self.__fields = fields

    @classmethod
    def many(cls, fields: "dict[str, list[str]]") -> "list[FormSource]":
        """One source per typed row. fields maps each column to its values in row order, for example
        {"origin_port": ["SGSIN", "MYPKG"], ...}. Rows left completely blank are skipped."""
        count = max((len(values) for values in fields.values()), default=0)
        sources = []
        for index in range(count):
            row = {name: values[index] if index < len(values) else "" for name, values in fields.items()}
            if any(str(value).strip() for value in row.values()):
                sources.append(cls(row))
        return sources

    def read(self):
        return [dict(self.__fields)]
