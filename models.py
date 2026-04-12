# models.py
from dataclasses import dataclass, field, asdict
from typing import List

@dataclass
class BaseObject:
    id: str = ""
    name: str = ""
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)

@dataclass
class Narrator(BaseObject):
    pass

@dataclass
class Character(BaseObject):
    inventory: List[str] = field(default_factory=list)
    equipped: List[str] = field(default_factory=list)
    is_player: bool = False

@dataclass
class Location(BaseObject):
    characters: List[str] = field(default_factory=list)
    items: List[str] = field(default_factory=list)

@dataclass
class Item(BaseObject):
    pass

@dataclass
class GameProfile:
    name: str = "Default"
    enabled_narrators: List[str] = field(default_factory=list)
    enabled_characters: List[str] = field(default_factory=list)
    enabled_locations: List[str] = field(default_factory=list)
    enabled_items: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "enabled_narrators": self.enabled_narrators,
            "enabled_characters": self.enabled_characters,
            "enabled_locations": self.enabled_locations,
            "enabled_items": self.enabled_items
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            name=data.get("name", "Default"),
            enabled_narrators=data.get("enabled_narrators", []),
            enabled_characters=data.get("enabled_characters", []),
            enabled_locations=data.get("enabled_locations", []),
            enabled_items=data.get("enabled_items", [])
        )