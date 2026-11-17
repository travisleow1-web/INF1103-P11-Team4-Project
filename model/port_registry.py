import json
from pathlib import Path
from typing import Iterable, List, Optional, Union
from .port import Port

DEFAULT_PORTS_FILE = Path(__file__).resolve().parent.parent / "ports_reference_4.json"


class PortRegistry:
    def __init__(self, ports: Iterable[Port]):
        self.__ports = {p.code: p for p in ports}

    @classmethod
    def from_json(cls, path: Union[str, Path] = DEFAULT_PORTS_FILE) -> "PortRegistry":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)["ports"]
        return cls([Port(p["code"], p["name"], p["country"], p["lat"], p["lon"]) for p in data])

    def find(self, text: str) -> Optional[Port]:
        code = str(text).split(" - ")[0].strip().upper()
        return self.__ports.get(code)

    def labels(self) -> List[str]:
        return [p.label() for p in self.__ports.values()]
