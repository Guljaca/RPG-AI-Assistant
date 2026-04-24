# models.py
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict

@dataclass
class BaseObject:
    id: str = ""
    name: str = ""
    description: str = ""
    associative_checks: str = ""   # просто текст: инструкция для модели, на что обратить внимание

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "associative_checks": self.associative_checks
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            associative_checks=data.get("associative_checks", "")
        )


@dataclass
class Narrator(BaseObject):
    pass


@dataclass
class Emotion(BaseObject):
    avatar_image: str = ""
    sprite_image: str = ""

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            "avatar_image": self.avatar_image,
            "sprite_image": self.sprite_image
        })
        return data

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            associative_checks=data.get("associative_checks", ""),
            avatar_image=data.get("avatar_image", ""),
            sprite_image=data.get("sprite_image", "")
        )


@dataclass
class Character(BaseObject):
    inventory: List[str] = field(default_factory=list)
    equipped: List[str] = field(default_factory=list)
    is_player: bool = False
    avatar_image: str = ""
    sprite_image: str = ""
    emotion_images: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            "inventory": self.inventory,
            "equipped": self.equipped,
            "is_player": self.is_player,
            "avatar_image": self.avatar_image,
            "sprite_image": self.sprite_image,
            "emotion_images": self.emotion_images
        })
        return data

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            associative_checks=data.get("associative_checks", ""),
            inventory=data.get("inventory", []),
            equipped=data.get("equipped", []),
            is_player=data.get("is_player", False),
            avatar_image=data.get("avatar_image", ""),
            sprite_image=data.get("sprite_image", ""),
            emotion_images=data.get("emotion_images", {})
        )


@dataclass
class Location(BaseObject):
    characters: List[str] = field(default_factory=list)
    items: List[str] = field(default_factory=list)
    background_image: str = ""

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            "characters": self.characters,
            "items": self.items,
            "background_image": self.background_image
        })
        return data

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            associative_checks=data.get("associative_checks", ""),
            characters=data.get("characters", []),
            items=data.get("items", []),
            background_image=data.get("background_image", "")
        )


@dataclass
class Item(BaseObject):
    pass


@dataclass
class Event(BaseObject):
    pass


@dataclass
class Scenario(BaseObject):
    pass


@dataclass
class GameProfile:
    name: str = "Default"
    enabled_narrators: List[str] = field(default_factory=list)
    enabled_characters: List[str] = field(default_factory=list)
    enabled_locations: List[str] = field(default_factory=list)
    enabled_items: List[str] = field(default_factory=list)
    enabled_events: List[str] = field(default_factory=list)
    enabled_scenarios: List[str] = field(default_factory=list)
    enabled_emotions: List[str] = field(default_factory=list)
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
            "enabled_emotions": self.enabled_emotions,
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
            enabled_emotions=data.get("enabled_emotions", []),
            player_character_id=data.get("player_character_id")
        )