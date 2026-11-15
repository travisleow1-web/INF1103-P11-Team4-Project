from .shipment_source import ShipmentSource


class FormSource(ShipmentSource):
    """One shipment row typed into the web form."""

    def __init__(self, fields: dict):
        self.__fields = fields

    @classmethod
    def many(cls, fields: "dict[str, list[str]]") -> "list[FormSource]":
        """One source per typed row; fields maps each column to its values in row order. Blank rows are skipped."""
        count = max((len(values) for values in fields.values()), default=0)
        rows = [{name: values[i] if i < len(values) else "" for name, values in fields.items()} for i in range(count)]
        return [cls(row) for row in rows if any(str(value).strip() for value in row.values())]

    def read(self) -> "list[dict]":
        """Return the row as a one-item list (a copy, so callers cannot change the source)."""
        return [dict(self.__fields)]
