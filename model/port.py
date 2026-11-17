from dataclasses import dataclass


@dataclass(frozen=True)
class Port:
    code: str
    name: str
    country: str
    lat: float
    lon: float

    def label(self) -> str:
        return f"{self.code} - {self.name}, {self.country}"
