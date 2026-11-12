import csv
import io
from .shipment_source import ShipmentSource
from .source_error import SourceError


class CsvSource(ShipmentSource):
    """Rows from an uploaded CSV file. Header names are trimmed and lower-cased."""

    def __init__(self, content: bytes):
        self.__content = content        # the uploaded file as bytes

    def read(self) -> "list[dict]":
        """Return one dict per data row. An unreadable or empty file raises SourceError."""
        try:
            text = self.__content.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            reader.fieldnames = [h.strip().lower() for h in reader.fieldnames or []]
            rows = list(reader)
        except (UnicodeDecodeError, csv.Error) as error:
            raise SourceError(f"Could not read file: {error}") from error
        if not rows:
            raise SourceError("The file has no shipments.")
        return rows
