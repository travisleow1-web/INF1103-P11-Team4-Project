import json
from pathlib import Path
from .port import Port

DEFAULT_PORTS_FILE = Path(__file__).resolve().parent.parent / "ports_reference_4.json"


class PortRegistry:
    def __init__(self, ports):
        self.__ports = {p.code: p for p in ports}

    @classmethod
    def from_json(cls, path=DEFAULT_PORTS_FILE):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)["ports"]
        return cls([Port(p["code"], p["name"], p["country"], p["lat"], p["lon"]) for p in data])

    def find(self, text):
        """Accept 'SGSIN' or the full label 'SGSIN - Singapore, SG'. Return a Port or None."""
        code = str(text).split(" - ")[0].strip().upper()
        return self.__ports.get(code)

    def labels(self):
        return [p.label() for p in self.__ports.values()]
