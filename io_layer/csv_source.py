import csv
import io
from .shipment_source import ShipmentSource
from .shipment_validator import ShipmentValidator
from .source_error import SourceError


class CsvSource(ShipmentSource):
    """Rows from an uploaded CSV file. Header names are trimmed and lower-cased."""

    UNREADABLE = "This file is not a readable CSV (UTF-8 text)."

    def __init__(self, content: bytes):
        self.__content = content        # the uploaded file as bytes

    def read(self) -> "list[dict]":
        """Return one dict per data row. An unreadable file, missing columns or no rows raise SourceError."""
        try:
            text = self.__content.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            reader.fieldnames = [h.strip().lower() for h in reader.fieldnames or []]
            rows = list(reader)
        except (UnicodeDecodeError, csv.Error) as error:
            raise SourceError(self.UNREADABLE) from error
        if not reader.fieldnames:
            raise SourceError("The file has no shipments.")
        missing = [name for name in ShipmentValidator.REQUIRED if name not in reader.fieldnames]
        if missing:
            raise SourceError(f"The file is missing the columns: {', '.join(missing)}.")
        if not rows:
            raise SourceError("The file has no shipments.")
        return rows
