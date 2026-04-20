# storage_manager.py
import os
import json
import re
import shutil
from typing import Dict, List, Optional, Any, TypeVar
from datetime import datetime
from models import BaseObject, Narrator, Character, Location, Item, Event, Scenario, Emotion, GameProfile

T = TypeVar('T', bound=BaseObject)

def sanitize_filename(name: str) -> str:
    """Заменяет недопустимые для имени файла символы на подчёркивания."""
    return re.sub(r'[\\/*?:"<>|]', '_', name).strip()

class CampaignStorageManager:
    """
    Хранит данные по кампаниям в папке data/campaigns/<campaign_name>/
    Каждый тип объектов имеет свою подпапку: narrators, characters, locations, items, events, scenarios, emotions.
    Также управляет сессиями и профилями внутри кампании.
    """
    OBJ_TYPES = {
        "narrators": Narrator,
        "characters": Character,
        "locations": Location,
        "items": Item,
        "events": Event,
        "scenarios": Scenario,
        "emotions": Emotion,
    }
    PREFIX_MAP = {
        "narrators": "n",
        "characters": "c",
        "locations": "l",
        "items": "i",
        "events": "e",
        "scenarios": "s",
        "emotions": "em",
    }

    def __init__(self, base_dir: str = "data"):
        self.base_dir = base_dir
        self.campaigns_dir = os.path.join(base_dir, "campaigns")
        os.makedirs(self.campaigns_dir, exist_ok=True)
        self.current_campaign: Optional[str] = None
        # Кэш мета-информации (счётчики ID) по кампаниям
        self._meta_cache: Dict[str, Dict[str, Dict]] = {}

    # ---------- Управление кампаниями ----------
    def set_campaign(self, campaign_name: str):
        """Устанавливает активную кампанию. Если папки нет – создаёт."""
        self.current_campaign = sanitize_filename(campaign_name)
        campaign_path = os.path.join(self.campaigns_dir, self.current_campaign)
        os.makedirs(campaign_path, exist_ok=True)
        for obj_type in self.OBJ_TYPES:
            os.makedirs(os.path.join(campaign_path, obj_type), exist_ok=True)
        os.makedirs(os.path.join(campaign_path, "sessions"), exist_ok=True)
        os.makedirs(os.path.join(campaign_path, "profiles"), exist_ok=True)
        self._load_meta()

    def _get_campaign_path(self) -> str:
        if not self.current_campaign:
            raise RuntimeError("No campaign selected. Call set_campaign() first.")
        return os.path.join(self.campaigns_dir, self.current_campaign)

    def _get_type_path(self, obj_type: str) -> str:
        return os.path.join(self._get_campaign_path(), obj_type)

    def _meta_path(self, obj_type: str) -> str:
        return os.path.join(self._get_type_path(obj_type), "_meta.json")

    def _load_meta(self):
        """Загружает мета-данные для всех типов объектов текущей кампании."""
        if self.current_campaign not in self._meta_cache:
            self._meta_cache[self.current_campaign] = {}
        meta = self._meta_cache[self.current_campaign]
        for obj_type in self.OBJ_TYPES:
            meta_file = self._meta_path(obj_type)
            if os.path.exists(meta_file):
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta[obj_type] = json.load(f)
            else:
                meta[obj_type] = {"next_num": 1, "free_nums": []}

    def _save_meta(self, obj_type: str):
        meta = self._meta_cache[self.current_campaign]
        with open(self._meta_path(obj_type), "w", encoding="utf-8") as f:
            json.dump(meta[obj_type], f, ensure_ascii=False, indent=2)

    def _get_next_id(self, obj_type: str) -> str:
        prefix = self.PREFIX_MAP[obj_type]
        meta = self._meta_cache[self.current_campaign][obj_type]
        next_num = meta.get("next_num", 1)
        free = meta.get("free_nums", [])
        if free:
            num = free.pop(0)
            meta["free_nums"] = free
        else:
            num = next_num
            meta["next_num"] = next_num + 1
        self._save_meta(obj_type)
        return f"{prefix}{num}"

    def _free_id(self, obj_type: str, obj_id: str):
        prefix = self.PREFIX_MAP[obj_type]
        if not obj_id.startswith(prefix):
            return
        num_str = obj_id[1:]
        if num_str.isdigit():
            num = int(num_str)
            meta = self._meta_cache[self.current_campaign][obj_type]
            if "free_nums" not in meta:
                meta["free_nums"] = []
            if num not in meta["free_nums"]:
                meta["free_nums"].append(num)
                meta["free_nums"].sort()
            self._save_meta(obj_type)

    def _get_filename(self, obj: BaseObject) -> str:
        """Генерирует имя файла на основе названия объекта (с защитой)."""
        safe_name = sanitize_filename(obj.name)
        if not safe_name:
            safe_name = "unnamed"
        return f"{safe_name}.json"

    # ---------- Работа с объектами (NPC, локации и т.д.) ----------
    def save_object(self, obj_type: str, obj: BaseObject):
        """Сохраняет объект. Если у объекта нет ID, генерирует новый."""
        if not obj.id:
            obj.id = self._get_next_id(obj_type)
        filename = self._get_filename(obj)
        filepath = os.path.join(self._get_type_path(obj_type), filename)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
            if existing_data.get("id") != obj.id:
                base, ext = os.path.splitext(filename)
                filename = f"{base}_{obj.id}{ext}"
                filepath = os.path.join(self._get_type_path(obj_type), filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(obj.to_dict(), f, ensure_ascii=False, indent=2)

    def load_object(self, obj_type: str, obj_id: str) -> Optional[BaseObject]:
        """Загружает объект по ID."""
        type_path = self._get_type_path(obj_type)
        if not os.path.exists(type_path):
            return None
        for filename in os.listdir(type_path):
            if not filename.endswith(".json") or filename == "_meta.json":
                continue
            filepath = os.path.join(type_path, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("id") == obj_id:
                cls = self.OBJ_TYPES[obj_type]
                return cls.from_dict(data)
        return None

    def load_all_objects(self, obj_type: str) -> List[BaseObject]:
        type_path = self._get_type_path(obj_type)
        objects = []
        if not os.path.exists(type_path):
            print(f"DEBUG: Папка {type_path} не существует")
            return objects
        
        print(f"\n=== DEBUG: Загрузка {obj_type} из {type_path} ===")
        
        for filename in os.listdir(type_path):
            if filename.endswith(".json") and filename != "_meta.json":
                filepath = os.path.join(type_path, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    print(f"\n--- Файл: {filename} ---")
                    print(f"Содержимое data: {data}")
                    print(f"Ключи data: {list(data.keys())}")
                    if "background_image" in data:
                        print(f"background_image = '{data['background_image']}'")
                    else:
                        print("Ключ 'background_image' ОТСУТСТВУЕТ в data!")
                    
                    cls = self.OBJ_TYPES[obj_type]
                    obj = cls.from_dict(data)
                    
                    print(f"Объект после from_dict: id={obj.id}, name={obj.name}")
                    if obj_type == "locations":
                        print(f"obj.background_image = '{getattr(obj, 'background_image', 'НЕТ АТРИБУТА')}'")
                    
                    objects.append(obj)
                except Exception as e:
                    print(f"Ошибка загрузки {filename}: {e}")
        
        print(f"\n=== Итого загружено {len(objects)} объектов {obj_type} ===\n")
        objects.sort(key=lambda x: x.id)
        return objects


    def delete_object(self, obj_type: str, obj_id: str):
        """Удаляет объект по ID."""
        type_path = self._get_type_path(obj_type)
        if not os.path.exists(type_path):
            return
        for filename in os.listdir(type_path):
            if not filename.endswith(".json") or filename == "_meta.json":
                continue
            filepath = os.path.join(type_path, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("id") == obj_id:
                os.remove(filepath)
                self._free_id(obj_type, obj_id)
                break

    def list_campaigns(self) -> List[str]:
        """Возвращает список имён существующих кампаний."""
        if not os.path.exists(self.campaigns_dir):
            return []
        return [d for d in os.listdir(self.campaigns_dir)
                if os.path.isdir(os.path.join(self.campaigns_dir, d))]

    def create_campaign(self, name: str) -> bool:
        """Создаёт новую кампанию."""
        safe_name = sanitize_filename(name)
        if not safe_name:
            return False
        path = os.path.join(self.campaigns_dir, safe_name)
        if os.path.exists(path):
            return False
        os.makedirs(path)
        for obj_type in self.OBJ_TYPES:
            os.makedirs(os.path.join(path, obj_type), exist_ok=True)
        os.makedirs(os.path.join(path, "sessions"), exist_ok=True)
        os.makedirs(os.path.join(path, "profiles"), exist_ok=True)
        return True

    def delete_campaign(self, name: str):
        """Удаляет кампанию и все её данные."""
        safe_name = sanitize_filename(name)
        path = os.path.join(self.campaigns_dir, safe_name)
        if os.path.exists(path):
            shutil.rmtree(path)
            if self.current_campaign == safe_name:
                self.current_campaign = None
                self._meta_cache.pop(safe_name, None)

    # ---------- Работа с сессиями ----------
    def _get_sessions_dir(self) -> str:
        return os.path.join(self._get_campaign_path(), "sessions")

    def _session_file_path(self, session_id: str) -> str:
        return os.path.join(self._get_sessions_dir(), f"{session_id}.json")

    def save_session(self, session_id: str, data: dict):
        """Сохраняет данные сессии."""
        os.makedirs(self._get_sessions_dir(), exist_ok=True)
        filepath = self._session_file_path(session_id)
        temp_path = filepath + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, filepath)

    def load_session(self, session_id: str) -> Optional[dict]:
        """Загружает данные сессии."""
        filepath = self._session_file_path(session_id)
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError, IOError):
            return None

    def delete_session(self, session_id: str):
        """Удаляет файл сессии."""
        filepath = self._session_file_path(session_id)
        if os.path.exists(filepath):
            os.remove(filepath)

    def list_sessions(self) -> List[str]:
        """Возвращает список ID сессий в текущей кампании."""
        sessions_dir = self._get_sessions_dir()
        if not os.path.exists(sessions_dir):
            return []
        sessions = []
        for f in os.listdir(sessions_dir):
            if f.endswith(".json"):
                sessions.append(f[:-5])
        return sessions

    def rename_session(self, session_id: str, new_name: str):
        """Переименовывает сессию (изменяет поле 'name' в JSON)."""
        data = self.load_session(session_id)
        if data:
            data["name"] = new_name
            self.save_session(session_id, data)

    # ---------- Работа с профилями ----------
    def _get_profiles_dir(self) -> str:
        return os.path.join(self._get_campaign_path(), "profiles")

    def _profile_file_path(self, profile_name: str) -> str:
        safe_name = sanitize_filename(profile_name)
        return os.path.join(self._get_profiles_dir(), f"{safe_name}.json")

    def save_profile(self, profile: GameProfile):
        """Сохраняет профиль в файл."""
        os.makedirs(self._get_profiles_dir(), exist_ok=True)
        filepath = self._profile_file_path(profile.name)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)

    def load_profile(self, profile_name: str) -> Optional[GameProfile]:
        """Загружает профиль по имени."""
        filepath = self._profile_file_path(profile_name)
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return GameProfile.from_dict(data)

    def delete_profile(self, profile_name: str):
        """Удаляет файл профиля."""
        filepath = self._profile_file_path(profile_name)
        if os.path.exists(filepath):
            os.remove(filepath)

    def list_profiles(self) -> List[str]:
        """Возвращает список имён профилей в текущей кампании."""
        profiles_dir = self._get_profiles_dir()
        if not os.path.exists(profiles_dir):
            return []
        profiles = []
        for f in os.listdir(profiles_dir):
            if f.endswith(".json"):
                profiles.append(f[:-5])
        return profiles