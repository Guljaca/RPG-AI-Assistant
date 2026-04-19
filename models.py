# models.py
from dataclasses import dataclass, field, asdict
from typing import List, Optional

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
class Event(BaseObject):
    """Событие — описание возможной ситуации, действия, происшествия."""
    pass

@dataclass
class Scenario(BaseObject):
    """
    Сценарий — описание общей последовательности событий (например, «Сегодня мы идём в школу»).
    Модель не обязана строго следовать сценарию, но может использовать его как направляющую.
    """
    pass

@dataclass
class GameProfile:
    name: str = "Default"
    enabled_narrators: List[str] = field(default_factory=list)
    enabled_characters: List[str] = field(default_factory=list)
    enabled_locations: List[str] = field(default_factory=list)
    enabled_items: List[str] = field(default_factory=list)
    enabled_events: List[str] = field(default_factory=list)
    enabled_scenarios: List[str] = field(default_factory=list)   # НОВОЕ
    player_character_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "enabled_narrators": self.enabled_narrators,
            "enabled_characters": self.enabled_characters,
            "enabled_locations": self.enabled_locations,
            "enabled_items": self.enabled_items,
            "enabled_events": self.enabled_events,
            "enabled_scenarios": self.enabled_scenarios,
            "player_character_id": self.player_character_id
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            name=data.get("name", "Default"),
            enabled_narrators=data.get("enabled_narrators", []),
            enabled_characters=data.get("enabled_characters", []),
            enabled_locations=data.get("enabled_locations", []),
            enabled_items=data.get("enabled_items", []),
            enabled_events=data.get("enabled_events", []),
            enabled_scenarios=data.get("enabled_scenarios", []),
            player_character_id=data.get("player_character_id")
        )