from dataclasses import dataclass


@dataclass(frozen=True)
class Port:
    """One port from ports_reference_4.json: UN/LOCODE, name, country and position."""

    code: str
    name: str
    country: str
    lat: float
    lon: float

    def label(self) -> str:
        """The text shown in the forms, for example 'SGSIN - Singapore, SG'."""
        return f"{self.code} - {self.name}, {self.country}"
