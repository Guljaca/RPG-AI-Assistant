import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog, simpledialog
import json
import os
import threading
import requests
import re
import uuid
import random
import ast
from typing import Dict, List, Optional, Any, Generator, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime

# ---------- Data Models (без изменений) ----------
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

# ---------- Storage Manager (без изменений) ----------
class StorageManager:
    def __init__(self, base_dir: str = "data"):
        self.base_dir = base_dir
        self.dirs = {
            "narrators": os.path.join(base_dir, "narrators"),
            "characters": os.path.join(base_dir, "characters"),
            "locations": os.path.join(base_dir, "locations"),
            "items": os.path.join(base_dir, "items"),
            "sessions": os.path.join(base_dir, "sessions"),
            "profiles": os.path.join(base_dir, "profiles"),
            "prompts": os.path.join(base_dir, "prompts"),
        }
        self._ensure_dirs()
        self.meta: Dict[str, Dict] = {}
        self._load_meta()
        self._migrate_old_ids()

    def _ensure_dirs(self):
        for d in self.dirs.values():
            os.makedirs(d, exist_ok=True)

    def _get_prefix(self, obj_type: str) -> str:
        return {"narrators": "n", "characters": "c", "locations": "l", "items": "i"}[obj_type]

    def _get_next_id(self, obj_type: str) -> str:
        prefix = self._get_prefix(obj_type)
        meta = self.meta[obj_type]
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
        prefix = self._get_prefix(obj_type)
        if not obj_id.startswith(prefix):
            return
        num_str = obj_id[1:]
        if num_str.isdigit():
            num = int(num_str)
            meta = self.meta[obj_type]
            if "free_nums" not in meta:
                meta["free_nums"] = []
            if num not in meta["free_nums"]:
                meta["free_nums"].append(num)
                meta["free_nums"].sort()
            self._save_meta(obj_type)

    def _load_meta(self):
        for obj_type in ["narrators", "characters", "locations", "items"]:
            meta_file = self._meta_path(obj_type)
            if os.path.exists(meta_file):
                with open(meta_file, "r", encoding="utf-8") as f:
                    self.meta[obj_type] = json.load(f)
            else:
                self.meta[obj_type] = {"next_num": 1, "free_nums": []}

    def _save_meta(self, obj_type: str):
        with open(self._meta_path(obj_type), "w", encoding="utf-8") as f:
            json.dump(self.meta[obj_type], f, ensure_ascii=False, indent=2)

    def _meta_path(self, obj_type: str) -> str:
        return os.path.join(self.dirs[obj_type], "_meta.json")

    def save_object(self, obj_type: str, obj: BaseObject):
        if not obj.id:
            obj.id = self._get_next_id(obj_type)
        filename = os.path.join(self.dirs[obj_type], f"{obj.id}.json")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(obj.to_dict(), f, ensure_ascii=False, indent=2)

    def load_object(self, obj_type: str, obj_id: str) -> Optional[BaseObject]:
        filename = os.path.join(self.dirs[obj_type], f"{obj_id}.json")
        if not os.path.exists(filename):
            return None
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        if obj_type == "narrators":
            return Narrator.from_dict(data)
        elif obj_type == "characters":
            if "is_player" not in data:
                data["is_player"] = False
            return Character.from_dict(data)
        elif obj_type == "locations":
            return Location.from_dict(data)
        elif obj_type == "items":
            return Item.from_dict(data)
        return None

    def load_all_objects(self, obj_type: str) -> List[BaseObject]:
        dir_path = self.dirs[obj_type]
        objects = []
        if not os.path.exists(dir_path):
            return objects
        for filename in os.listdir(dir_path):
            if filename.endswith(".json") and not filename.startswith("_meta"):
                obj_id = filename[:-5]
                obj = self.load_object(obj_type, obj_id)
                if obj:
                    objects.append(obj)
        objects.sort(key=lambda x: x.id)
        return objects

    def delete_object(self, obj_type: str, obj_id: str):
        filename = os.path.join(self.dirs[obj_type], f"{obj_id}.json")
        if os.path.exists(filename):
            os.remove(filename)
            self._free_id(obj_type, obj_id)

    def _migrate_old_ids(self):
        id_mapping = {}
        for obj_type in ["narrators", "characters", "locations", "items"]:
            prefix = self._get_prefix(obj_type)
            dir_path = self.dirs[obj_type]
            if not os.path.exists(dir_path):
                continue
            for filename in os.listdir(dir_path):
                if filename.endswith(".json") and not filename.startswith("_meta"):
                    filepath = os.path.join(dir_path, filename)
                    old_id = filename[:-5]
                    if old_id[0] in ('n','c','l','i'):
                        continue
                    if old_id.isdigit():
                        new_id = f"{prefix}{old_id}"
                        new_path = os.path.join(dir_path, f"{new_id}.json")
                        os.rename(filepath, new_path)
                        with open(new_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        data['id'] = new_id
                        if obj_type == 'characters':
                            if 'inventory' in data:
                                data['inventory'] = [f"i{str(i)}" if isinstance(i, int) else i for i in data['inventory']]
                            if 'equipped' in data:
                                data['equipped'] = [f"i{str(i)}" if isinstance(i, int) else i for i in data['equipped']]
                            if 'is_player' not in data:
                                data['is_player'] = False
                        elif obj_type == 'locations':
                            if 'characters' in data:
                                data['characters'] = [f"c{str(c)}" if isinstance(c, int) else c for c in data['characters']]
                            if 'items' in data:
                                data['items'] = [f"i{str(i)}" if isinstance(i, int) else i for i in data['items']]
                        with open(new_path, 'w', encoding='utf-8') as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        id_mapping[(obj_type, int(old_id))] = new_id
                        meta = self.meta[obj_type]
                        num = int(old_id)
                        if num >= meta.get("next_num", 1):
                            meta["next_num"] = num + 1
                        if num in meta.get("free_nums", []):
                            meta["free_nums"].remove(num)
                        self._save_meta(obj_type)

        for sess_file in os.listdir(self.dirs["sessions"]):
            if sess_file.endswith(".json"):
                sess_path = os.path.join(self.dirs["sessions"], sess_file)
                with open(sess_path, "r", encoding="utf-8") as f:
                    sess_data = json.load(f)
                updated = False
                profile = sess_data.get("profile", {})
                for key, prefix in [("enabled_narrators","n"), ("enabled_characters","c"), ("enabled_locations","l"), ("enabled_items","i")]:
                    old_list = profile.get(key, [])
                    new_list = []
                    for old in old_list:
                        if isinstance(old, int):
                            t = key.split("_")[1][:-1]
                            map_key = (t+"s", old)
                            if map_key in id_mapping:
                                new_list.append(id_mapping[map_key])
                            else:
                                new_list.append(f"{prefix}{old}")
                            updated = True
                        else:
                            new_list.append(old)
                    if updated:
                        profile[key] = new_list
                if updated:
                    sess_data["profile"] = profile
                    with open(sess_path, "w", encoding="utf-8") as f:
                        json.dump(sess_data, f, ensure_ascii=False, indent=2)

        for prof_file in os.listdir(self.dirs["profiles"]):
            if prof_file.endswith(".json"):
                prof_path = os.path.join(self.dirs["profiles"], prof_file)
                with open(prof_path, "r", encoding="utf-8") as f:
                    prof_data = json.load(f)
                updated = False
                for key, prefix in [("enabled_narrators","n"), ("enabled_characters","c"), ("enabled_locations","l"), ("enabled_items","i")]:
                    old_list = prof_data.get(key, [])
                    new_list = []
                    for old in old_list:
                        if isinstance(old, int):
                            t = key.split("_")[1][:-1]
                            map_key = (t+"s", old)
                            if map_key in id_mapping:
                                new_list.append(id_mapping[map_key])
                            else:
                                new_list.append(f"{prefix}{old}")
                            updated = True
                        else:
                            new_list.append(old)
                    if updated:
                        prof_data[key] = new_list
                if updated:
                    with open(prof_path, "w", encoding="utf-8") as f:
                        json.dump(prof_data, f, ensure_ascii=False, indent=2)

    def save_session(self, session_id: str, session_data: dict):
        filename = os.path.join(self.dirs["sessions"], f"{session_id}.json")
        temp_filename = filename + ".tmp"
        try:
            # Сначала пишем во временный файл
            with open(temp_filename, "w", encoding="utf-8") as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            # Затем атомарно заменяем (переименовываем)
            os.replace(temp_filename, filename)
        except Exception:
            # Если ошибка — удаляем временный файл, чтобы не засорять
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
            raise

    def load_session(self, session_id: str) -> Optional[dict]:
        filename = os.path.join(self.dirs["sessions"], f"{session_id}.json")
        if not os.path.exists(filename):
            return None
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError, IOError):
            # Файл повреждён или нечитаем
            return None

    def list_sessions(self) -> List[str]:
        dir_path = self.dirs["sessions"]
        sessions = []
        for f in os.listdir(dir_path):
            if f.endswith(".json"):
                sessions.append(f[:-5])
        return sessions

    def delete_session(self, session_id: str):
        filename = os.path.join(self.dirs["sessions"], f"{session_id}.json")
        if os.path.exists(filename):
            os.remove(filename)

    def save_profile(self, profile: GameProfile):
        filename = os.path.join(self.dirs["profiles"], f"{profile.name}.json")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)

    def load_profile(self, name: str) -> Optional[GameProfile]:
        filename = os.path.join(self.dirs["profiles"], f"{name}.json")
        if not os.path.exists(filename):
            return None
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        return GameProfile.from_dict(data)

    def list_profiles(self) -> List[str]:
        dir_path = self.dirs["profiles"]
        profiles = []
        for f in os.listdir(dir_path):
            if f.endswith(".json"):
                profiles.append(f[:-5])
        return profiles

# ---------- Prompt Manager (добавлены мини-промты) ----------
class PromptManager:
    def __init__(self, storage: StorageManager):
        self.storage = storage
        self.prompts_dir = storage.dirs["prompts"]
        self.default_prompts = {
            # Мини-промты для поэтапной генерации
            "stage1_request_descriptions": (
                "Ты — рассказчик в TTRPG.\n"
                "Игрок написал: '{user_message}'\n\n"
                "Доступные объекты (ID и названия):\n{available_objects}\n\n"
                "Алгоритм:\n"
                "1. Вызови send_object_info с массивом object_ids кандидатов.\n"
                "2. После получения описаний напиши рассуждения (какие объекты подходят, какие нет).\n"
                "3  Проведи предварительный анализ"
                "4. Если событие устраивает: вызови confirm_scene с location_id, character_ids, item_ids по примеру confirm_scene(location_id=\"l1\", character_ids=[\"c1\",\"c3\"], item_ids=[\"i1\",\"i3\"]"
                
            ),
            "stage1_player_action": (
                "Ты — рассказчик в TTRPG.\n"
                "Игрок написал: '{user_message}'\n\n"
                "Описания объектов:\n{descriptions}\n\n"
                "Правила бросков d20:\n{dice_rules}\n"
                "{truth_violation}\n"
                "Задача:\n"
                "1. Вызови roll_dice('d20').\n"
                "2. Опиши результат (1-2 предложения, на русском, без упоминания броска). Если есть нарушение, обыграй его (например, попытка солгать провалилась, действие не удалось, NPC заметил обман).\n"
                "3. ОБЯЗАТЕЛЬНО ИЛИ ВСЕ СЛОМАЕТСЯ! Вызови report_player_action с параметрами dice_value и description по примеру: report_player_action(dice_value=15, description=Ты с силой толкаешь дверь, и она с грохотом распахивается, открывая тёмный коридор.)"
            ),
            "stage1_random_event": (
                "Ты — рассказчик в TTRPG.\n\n"
                "Описания объектов:\n{descriptions}\n\n"
                "Действие игрока: {player_action}\n\n"
                "Правила:\n- Бросок d100: если 1-30 → событие происходит.\n- Если событие произошло, брось d20 для качества: 1-4 негативное, 5-15 нейтральное, 16-20 позитивное.\n\n"
                "ШАГ 1. Вызови roll_dice('d100').\n"
                "ШАГ 2. Если результат <= 30: вызови roll_dice('d20'), придумай ОДНО предложение события, вызови report_random_event(dice_value=..., event_occurred=true, description='...').\n"
                "ШАГ 3. Если результат > 30: вызови report_random_event(dice_value=..., event_occurred=false, description='').\n"
                "Никакого лишнего текста, только вызовы инструментов и описание в report_random_event."
            ),
            "stage1_turn_order": (
                "Ты — рассказчик.\n\n"
                "Информация о текущей сцене:\n{scene_info}\n\n"
                "Список NPC на сцене:\n{npcs_list}\n\n"
                "Определи порядок ходов этих NPC (кроме игрока).\n"
                "Учти особенности локации, произошедшее событие, успех/провал действия игрока.\n"
                "НЕ вызывай roll_dice, НЕ бросай кубики. Просто оцени ситуацию.\n"
                "Вызови report_turn_order с параметром character_ids (массив ID NPC в порядке очереди)."
            ),
            "stage2_npc_action": (
                "Ты — рассказчик в TTRPG. Сейчас твоя задача — описать, что думает и планирует сделать персонаж {npc_name} (ID {npc_id}) в текущей ситуации.\n\n"
                "Описания объектов:\n{descriptions}\n\n"
                "Действие игрока (то, что он попытался сделать): {player_action}\n"
                "Случайное событие (если произошло): {event_description}\n"
                "Предыдущие намерения других NPC:\n{previous_actions}\n\n"
                "Опиши кратко (1-2 предложения) на русском языке:\n"
                "- Что этот NPC думает о происходящем?\n"
                "- Что он намерен сделать или сказать в ответ?\n"
                "Не упоминай броски кубиков и ID объектов. Только внутренние мысли и планы."
            ),
            "stage3_final": (
                "Ты — рассказчик в TTRPG. Опиши результат действий игрока и NPC.\n\n"
                "Локация и описание окружения:\n{location_desc}\n\n"
                "Действие игрока (уже произошло):\n{player_action_outcome}\n\n"
                "Случайное событие:\n{event_description}\n\n"
                "Планируемые действия NPC (это только их НАМЕРЕНИЯ, а не фактические события):\n{npcs_actions}\n\n"
                "РЕЗУЛЬТАТЫ БРОСКОВ D20 ДЛЯ КАЖДОГО NPC (ты НЕ ДОЛЖЕН их бросать, они уже даны):\n{dice_results}\n\n"
                "Правила интерпретации бросков:\n{dice_rules}\n\n"
                "ВАЖНО:\n"
                "- НЕ ВЫЗЫВАЙ roll_dice. Значения бросков уже предоставлены выше.\n"
                "- НЕ ВЫЗЫВАЙ finish_stage или другие функции.\n"
                "- Напиши связный рассказ от второго лица ('ты'), 4-8 предложений.\n"
                "- Не упоминай броски кубиков и ID объектов в ответе.\n"
                "- Не пересказывай намерения NPC — описывай только то, что реально произошло (движения, слова, звуки, последствия).\n"
                "- Для каждого NPC используй его результат броска, чтобы определить, насколько успешно он выполнил своё намерение.\n"
                "Просто напиши рассказ, без вызовов функций."
            ),
            # Старые промты оставлены для совместимости (не используются в новом потоке)
            "dice_rules": (
                "d20: 1=крит.провал, 2-4=провал, 5-15=успех, 16-19=большой успех, 20=крит.успех.\n"
                "d100: 1-100. Событие происходит, если выпавшее значение <= шанса.\n"
                "d6: 1-2 плохо, 3-4 нормально, 5-6 хорошо."
            ),
            "stage1_random_event_continue": ( "Ты — рассказчик. Случайное событие произошло.\n\nОписания объектов:\n{descriptions}\n\nДействие игрока: {player_action}\n\nБросок d20 для определения качества события: {dice20}.\n\nПравила интерпретации d20:\n1-4: негативное событие\n5-15: нейтральное событие\n16-20: позитивное событие\n\nОпиши событие кратко (1-2 предложения) и вызови report_random_event с параметрами:\n- dice_value: {dice20}\n- event_occurred: true\n- description: '<описание события>'"
            ),
            "stage4_summary": (
                "Ты — помощник, который выделяет ОДНО КЛЮЧЕВОЕ ИЗМЕНЕНИЕ из последнего обмена.\n"
                "ОТВЕТ ДОЛЖЕН БЫТЬ ТОЛЬКО ИЗ ЭТИХ СЛОВ (без кавычек, без 'Краткая память:', без имён):\n"
                "- Максимум 10 слов на русском.\n"
                "- Только факт: что изменилось в мире, состоянии NPC или игрока.\n"
                "- Не пиши 'Игрок сделал...', 'Рассказчик сказал...'.\n"
                "- Не пиши эмоции, намерения, диалоги — только результат.\n\n"
                "Примеры правильных ответов:\n"
                "Действие: 'Я выбиваю дверь' → Ответ: 'Замок двери сломан'\n"
                "Действие: 'Я спрашиваю у стража дорогу' → Ответ: 'Казначейство находится слева'\n"
                "Действие: 'Я толкаю сестру, чтобы разбудить' → Ответ: 'Сестра разозлилась'\n\n"
                "Твоя очередь. Действие игрока: {user_message}\n"
                "Ответ рассказчика: {assistant_message}\n"
                "Краткий факт (до 10 слов, без лишнего):"
            ),
            "stage1_truth_check": (
                "Ты — рассказчик, который проверяет правдивость сообщения игрока.\n"
                "Игрок написал: '{user_message}'\n\n"
                "Доступные объекты сцены и их описания:\n{descriptions}\n\n"
                "Задача:\n"
                "1. Проверь, не противоречит ли сообщение игрока известным фактам (описаниям объектов, их состоянию, инвентарю и т.д.).\n"
                "2. Если игрок пытается солгать, придумать невозможное действие или манипулировать, опиши это нарушение коротко (1-2 предложения).\n"
                "3. Если всё соответствует действительности, оставь поле violation пустым.\n"
                "4. Вызови функцию report_truth_check с параметрами:\n"
                "   - violation (строка): описание нарушения или пустая строка.\n"
                "Не добавляй лишний текст, только вызов функции."
            ),
                        
        }
        self._ensure_prompts()

    def _ensure_prompts(self):
        for name, default_content in self.default_prompts.items():
            filepath = os.path.join(self.prompts_dir, f"{name}.json")
            if not os.path.exists(filepath):
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump({"name": name, "content": default_content}, f, ensure_ascii=False, indent=2)

    def load_prompt(self, name: str) -> str:
        filepath = os.path.join(self.prompts_dir, f"{name}.json")
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("content", self.default_prompts.get(name, ""))
        return self.default_prompts.get(name, "")

    def save_prompt(self, name: str, content: str):
        filepath = os.path.join(self.prompts_dir, f"{name}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({"name": name, "content": content}, f, ensure_ascii=False, indent=2)

    def list_prompts(self) -> List[str]:
        prompts = []
        for f in os.listdir(self.prompts_dir):
            if f.endswith(".json"):
                prompts.append(f[:-5])
        return prompts

    def get_prompt_content(self, name: str) -> str:
        return self.load_prompt(name)

    def create_prompt(self, name: str, content: str = ""):
        if not name:
            return False
        filepath = os.path.join(self.prompts_dir, f"{name}.json")
        if os.path.exists(filepath):
            return False
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({"name": name, "content": content}, f, ensure_ascii=False, indent=2)
        return True

    def delete_prompt(self, name: str):
        filepath = os.path.join(self.prompts_dir, f"{name}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False

# ---------- LM Studio Client (добавлены новые tools) ----------
class LMStudioClient:
    def __init__(self, base_url: str = "http://localhost:1234/v1"):
        self.base_url = base_url
        self.default_max_tokens = 4096
        self.default_temperature = 0.7

    def set_default_params(self, max_tokens: int, temperature: float):
        self.default_max_tokens = max_tokens
        self.default_temperature = temperature

    def chat_completion_stream(
        self,
        messages: List[Dict],
        model: str,
        temperature: float = None,
        max_tokens: int = None,
        timeout: int = 180,
        tools: List[Dict] = None
    ) -> Generator[Dict, None, None]:
        url = f"{self.base_url}/chat/completions"
        temp = temperature if temperature is not None else self.default_temperature
        mt = max_tokens if max_tokens is not None else self.default_max_tokens

        if tools is None:
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "confirm_scene",
                        "description": "Подтверждает окончательный состав сцены после проверки описаний объектов.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location_id": {
                                    "type": "string",
                                    "description": "ID локации, где происходит сцена (может быть null, если не определена)"
                                },
                                "character_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Массив ID персонажей, которые действительно присутствуют в сцене"
                                },
                                "item_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Массив ID предметов, присутствующих в сцене"
                                }
                            },
                            "required": ["location_id", "character_ids", "item_ids"]
                        }
                    }
                },
                    {
                    "type": "function",
                    "function": {
                        "name": "send_object_info",
                        "description": "Запрашивает полные описания объектов по их ID.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "object_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Массив ID объектов (например, ['c1', 'c2', 'l1'])"
                                }
                            },
                            "required": ["object_ids"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "roll_dice",
                        "description": "Бросает кубик указанного типа и возвращает результат.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "dice_type": {
                                    "type": "string",
                                    "enum": ["d20", "d100", "d6"],
                                    "description": "Тип кубика"
                                }
                            },
                            "required": ["dice_type"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "generate_random_event",
                        "description": "Генерирует случайное событие на основе броска кубика.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "dice_type": {
                                    "type": "string",
                                    "enum": ["d20", "d100", "d6"],
                                    "description": "Тип кубика для броска"
                                },
                                "chance": {
                                    "type": "integer",
                                    "description": "Шанс события в процентах (0-100)."
                                }
                            },
                            "required": ["dice_type"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "report_player_action",
                        "description": "Сообщает результат действия игрока после броска d20.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "dice_value": {"type": "integer"},
                                "description": {"type": "string"}
                            },
                            "required": ["dice_value", "description"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "report_random_event",
                        "description": "Сообщает результат проверки случайного события.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "dice_value": {"type": "integer"},
                                "event_occurred": {"type": "boolean"},
                                "description": {"type": "string"}
                            },
                            "required": ["dice_value", "event_occurred", "description"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "report_turn_order",
                        "description": "Сообщает порядок ходов NPC.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "character_ids": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                }
                            },
                            "required": ["character_ids"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "report_npc_action",
                        "description": "Сообщает действие NPC после броска d20.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "character_id": {"type": "string"},
                                "dice_value": {"type": "integer"},
                                "description": {"type": "string"}
                            },
                            "required": ["character_id", "dice_value", "description"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "finish_stage",
                        "description": "Завершает текущий этап генерации.",
                        "parameters": {
                            "type": "object",
                            "properties": {}
                        }
                    }
                }
            ]

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temp,
            "max_tokens": mt,
            "tools": tools,
            "tool_choice": "auto",
            "parallel_tool_calls": True,
            "stream": True
        }

        try:
            response = requests.post(url, json=payload, stream=True, timeout=timeout)
            response.raise_for_status()

            for line in response.iter_lines():
                if not line:
                    continue
                line = line.decode('utf-8')
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    choice = chunk.get("choices", [{}])[0]
                    delta = choice.get("delta", {})

                    reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                    if reasoning:
                        yield {"type": "reasoning", "text": reasoning}

                    if "tool_calls" in delta:
                        yield {"type": "tool_calls", "tool_calls": delta["tool_calls"]}

                    if "content" in delta and delta["content"]:
                        yield {"type": "content", "text": delta["content"]}

                    if "usage" in chunk:
                        yield {"type": "done", "usage": chunk["usage"]}
                except json.JSONDecodeError:
                    continue
            yield {"type": "done", "usage": None}
        except Exception as e:
            yield {"type": "error", "message": str(e)}

# ---------- Context Menu (без изменений) ----------
def add_context_menu(widget):
    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label="Вырезать", command=lambda: widget.event_generate("<<Cut>>"))
    menu.add_command(label="Копировать", command=lambda: widget.event_generate("<<Copy>>"))
    menu.add_command(label="Вставить", command=lambda: widget.event_generate("<<Paste>>"))
    menu.add_separator()
    menu.add_command(label="Выделить всё", command=lambda: widget.event_generate("<<SelectAll>>"))

    def show_menu(event):
        try:
            if widget.selection_present():
                menu.entryconfig("Вырезать", state="normal")
                menu.entryconfig("Копировать", state="normal")
            else:
                menu.entryconfig("Вырезать", state="disabled")
                menu.entryconfig("Копировать", state="disabled")
            menu.entryconfig("Вставить", state="normal")
        except:
            pass
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    widget.bind("<Button-3>", show_menu)
    widget.bind("<Control-a>", lambda e: widget.tag_add(tk.SEL, "1.0", tk.END) if hasattr(widget, 'tag_add') else widget.select_range(0, tk.END))
    widget.bind("<Control-A>", lambda e: widget.tag_add(tk.SEL, "1.0", tk.END) if hasattr(widget, 'tag_add') else widget.select_range(0, tk.END))

# ---------- Main Application (переработан) ----------
class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RPG AI Assistant")
        self.geometry("1200x700")
        self.minsize(900, 600)
        self.stage_names = [
            "stage1_request_descriptions",
            "stage1_truth_check",
            "stage1_player_action",
            "stage1_random_event",
            "stage1_turn_order",
            "stage2_npc_action",
            "stage3_final",
            "stage4_summary"
        ]

        self.memory_summary = ""

        self.settings_file = "settings.json"
        self.settings = self.load_settings()

        self.storage = StorageManager()
        self.prompt_manager = PromptManager(self.storage)

        self.logs_dir = os.path.join(self.storage.base_dir, "logs")
        self.max_log_files = 20
        os.makedirs(self.logs_dir, exist_ok=True)
        self.current_debug_log_path = None

        self.narrators: Dict[str, Narrator] = {}
        self.characters: Dict[str, Character] = {}
        self.locations: Dict[str, Location] = {}
        self.items: Dict[str, Item] = {}

        self.current_session_id: Optional[str] = None
        self.current_profile: GameProfile = GameProfile(name="Default")
        self.conversation_history: List[Dict] = []
        self.last_user_message: str = ""
        self.max_history_messages: int = self.settings.get("max_history_messages", 10)

        self.local_descriptions: Dict[str, str] = {}

        self.last_original_response: Optional[str] = None
        self.last_translated_response: Optional[str] = None

        self.enable_memory_summary = self.settings.get("enable_memory_summary", False)
        self.max_memory_summaries = self.settings.get("max_memory_summaries", 5)
        self.memory_summaries: List[str] = []   # заполнится при загрузке сессии

        self.lm_client = LMStudioClient(base_url=self.settings.get("api_url", "http://localhost:1234/v1"))

        self.is_generating = False
        self.stop_generation_flag = False

        self.current_dice_sequences = ([], [], [])
        self.dice_indices = [0, 0, 0]

        # Состояние поэтапной генерации
        self.stage = None          # текущий этап: "stage1_request_descriptions", "stage1_player_action", ...
        self.stage_data = {
            "user_message": "",
            "descriptions": {},
            "scene_location_id": None,
            "scene_character_ids": [],
            "scene_item_ids": [],
            "scene_summary": "",
            "player_action_dice": None,
            "player_action_desc": "",
            "event_dice": None,
            "event_occurred": False,
            "event_desc": "",
            "turn_order": [],
            "npc_actions": {},
            "current_npc_index": 0,
            "final_response": "",
            "truth_violation": ""     
        }

        self.stage_retries = {} 
        # Мультимодельные настройки
        self.use_two_models = self.settings.get("use_two_models", False)
        self.primary_model = self.settings.get("primary_model", "local-model")
        self.translator_model = self.settings.get("translator_model", "local-model")
        self.enable_assistant_translation = self.settings.get("enable_assistant_translation", False)
        self.model_name = self.settings.get("model_name", "local-model")
        self.primary_temperature = self.settings.get("primary_temperature", 0.7)
        self.primary_max_tokens = self.settings.get("primary_max_tokens", 4096)
        self.translator_temperature = self.settings.get("translator_temperature", 0.3)
        self.translator_max_tokens = self.settings.get("translator_max_tokens", 4096)

        self.last_original_response: Optional[str] = None
        self.last_translated_response: Optional[str] = None

        self.lm_client = LMStudioClient(base_url=self.settings.get("api_url", "http://localhost:1234/v1"))
        self.lm_client.set_default_params(
            max_tokens=self.settings.get("max_tokens", 4096),
            temperature=self.settings.get("temperature", 0.7)
        )

        self.left_panel = None
        self.center_panel = None
        self.right_panel = None

        self.stage_prompts_config = self.settings.get("stage_prompts_config", {})

        self.event_handlers = {
            "send_message": self._handle_send_message,
            "start_game": self._handle_start_game,
            "stop_generation": self._handle_stop_generation,
            "new_session": self._handle_new_session,
            "load_session": self._handle_load_session,
            "delete_session": self._handle_delete_session,
            "rename_session": self._handle_rename_session,
            "save_current_session": self._handle_save_current_session,
            "regenerate_last_response": self._handle_regenerate_last_response,
            "regenerate_translation": self._handle_regenerate_translation,
            "delete_last_user_message": self._handle_delete_last_user_message,
            "update_narrator": self._handle_update_narrator,
            "delete_narrator": self._handle_delete_narrator,
            "create_character": self._handle_create_character,
            "update_character": self._handle_update_character,
            "delete_character": self._handle_delete_character,
            "create_location": self._handle_create_location,
            "update_location": self._handle_update_location,
            "delete_location": self._handle_delete_location,
            "create_item": self._handle_create_item,
            "update_item": self._handle_update_item,
            "delete_item": self._handle_delete_item,
            "refresh_ui": self._handle_refresh_ui,
            "update_settings": self._handle_update_settings,
            "update_profile": self._handle_update_profile,
            "save_profile": self._handle_save_profile,
            "load_profile": self._handle_load_profile,
            "new_profile": self._handle_new_profile,
            "update_prompt": self._handle_update_prompt,
            "create_prompt": self._handle_create_prompt,
            "delete_prompt": self._handle_delete_prompt,
            "clear_chat": self._handle_clear_chat,
            "set_local_description": self._handle_set_local_description,
            "clear_local_description": self._handle_clear_local_description,
            # Новые события для поэтапной генерации
            "stage1_request_descriptions": self._stage1_request_descriptions,
            "stage1_player_action": self._stage1_player_action,
            "stage1_random_event": self._stage1_random_event,
            "stage1_turn_order": self._stage1_turn_order,
            "stage2_process_npc": self._stage2_process_npc,
            "stage3_final": self._stage3_final,
            "stage4_summary": self._stage4_summary,
            "stage1_truth_check": self._stage1_truth_check,
        }

        self._build_ui()
        self._load_all_data()
        self._load_last_session()
        self.update_idletasks()
        self.after(100, self._refresh_all_ui)
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _cleanup_old_logs(self):
        """Оставляет не более self.max_log_files самых свежих debug_*.txt в папке logs."""
        if not os.path.exists(self.logs_dir):
            return
        # Получаем все файлы, подходящие под шаблон
        files = []
        for f in os.listdir(self.logs_dir):
            if f.startswith("debug_") and f.endswith(".txt"):
                full = os.path.join(self.logs_dir, f)
                files.append((full, os.path.getmtime(full)))
        # Сортируем по времени модификации (новые — в конце)
        files.sort(key=lambda x: x[1])
        # Если превышаем лимит, удаляем старые
        if len(files) > self.max_log_files:
            to_delete = files[:len(files) - self.max_log_files]
            for full_path, _ in to_delete:
                try:
                    os.remove(full_path)
                except Exception:
                    pass

    def _cleanup_stage_prompts_narrators(self):
        """Вызывается при изменении профиля или удалении рассказчика."""
        if self.right_panel and self.current_tab == "stage_prompts":
            stage_tab = self.right_panel.tab_frames.get("stage_prompts")
            if stage_tab and hasattr(stage_tab, "cleanup_inactive_narrators"):
                stage_tab.cleanup_inactive_narrators()

    def save_stage_prompts_config(self):
        self.settings["stage_prompts_config"] = self.stage_prompts_config
        self.save_settings()

    def _log_debug_step(self, step: str, content: str = "", error: str = None):
        self._log_debug(step, content, error)

    def update(self, event_type: str, data: Any = None):
        handler = self.event_handlers.get(event_type)
        if handler:
            handler(data)

    # ---------- Вспомогательные методы (без изменений) ----------
    def _on_closing(self):
        if self.current_session_id:
            self._handle_save_current_session()
        self.destroy()

    def _start_debug_log(self, user_message: str):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"debug_{timestamp}.txt"
        self.current_debug_log_path = os.path.join(self.logs_dir, filename)
        with open(self.current_debug_log_path, "w", encoding="utf-8") as f:
            f.write(f"=== DEBUG LOG ===\nUser message at {datetime.now().isoformat()}:\n{user_message}\n\n")
        self._cleanup_old_logs()

    def _log_debug(self, step_name: str, content: str = "", error: str = None):
        if not self.current_debug_log_path:
            return
        try:
            with open(self.current_debug_log_path, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat()}] {step_name}\n")
                if content:
                    if len(content) > 50000:
                        f.write(content[:50000] + "\n... (truncated)\n")
                    else:
                        f.write(content)
                    f.write("\n")
                if error:
                    f.write(f"ERROR: {error}\n")
                f.write("\n")
        except Exception:
            pass

    def load_settings(self) -> dict:
        default = {
            "api_url": "http://localhost:1234/v1",
            "model_name": "",
            "max_history_messages": 10,
            "show_thinking": True,
            "dice_d20_count": 10,
            "dice_d100_count": 10,
            "dice_d6_count": 100,
            "use_two_models": False,
            "primary_model": "",
            "translator_model": "",
            "enable_assistant_translation": False,
            "max_tokens": 4096,
            "temperature": 0.7,
            "primary_temperature": 0.7,
            "primary_max_tokens": 4096,
            "translator_temperature": 0.3,
            "translator_max_tokens": 4096,
            "stage_prompts_config": {}
        }
        if os.path.exists(self.settings_file):
            with open(self.settings_file, "r") as f:
                loaded = json.load(f)
                default.update(loaded)
        if not default["model_name"] or default["model_name"] == "local-model":
            try:
                temp_client = LMStudioClient(base_url=default["api_url"])
                url = default["api_url"].rstrip('/').replace('/v1', '') + '/v1/models'
                resp = requests.get(url, timeout=2)
                if resp.status_code == 200:
                    data = resp.json()
                    models = []
                    if "data" in data:
                        models = [m["id"] for m in data["data"] if m.get("id")]
                    if models:
                        default["model_name"] = models[0]
                    else:
                        default["model_name"] = "local-model"
                else:
                    default["model_name"] = "local-model"
            except Exception:
                default["model_name"] = "local-model"
        if not default["primary_model"] or default["primary_model"] == "local-model":
            default["primary_model"] = default["model_name"]
        if not default["translator_model"] or default["translator_model"] == "local-model":
            default["translator_model"] = default["model_name"]
        return default

    def save_settings(self):
        with open(self.settings_file, "w") as f:
            json.dump(self.settings, f, indent=2)

    def generate_dice_sequences(self):
        d20_cnt = self.settings.get("dice_d20_count", 10)
        d100_cnt = self.settings.get("dice_d100_count", 10)
        d6_cnt = self.settings.get("dice_d6_count", 100)
        return (
            [random.randint(1, 20) for _ in range(d20_cnt)],
            [random.randint(1, 100) for _ in range(d100_cnt)],
            [random.randint(1, 6) for _ in range(d6_cnt)]
        )

    def get_next_dice_value(self, dice_type: str) -> Optional[int]:
        if dice_type == "d20":
            seq = self.current_dice_sequences[0]
            idx = self.dice_indices[0]
            if idx < len(seq):
                self.dice_indices[0] += 1
                return seq[idx]
        elif dice_type == "d100":
            seq = self.current_dice_sequences[1]
            idx = self.dice_indices[1]
            if idx < len(seq):
                self.dice_indices[1] += 1
                return seq[idx]
        elif dice_type == "d6":
            seq = self.current_dice_sequences[2]
            idx = self.dice_indices[2]
            if idx < len(seq):
                self.dice_indices[2] += 1
                return seq[idx]
        return None

    def _safe_stop_generation(self, callback=None):
        if self.is_generating:
            self.stop_generation_flag = True
            self._wait_for_generation_stop(callback)
        else:
            if callback:
                callback()

    def _wait_for_generation_stop(self, callback):
        if not self.is_generating:
            if callback:
                callback()
        else:
            self.after(100, lambda: self._wait_for_generation_stop(callback))

    # ---------- Обработчики сессий (без изменений) ----------
    def _save_current_session_safe(self):
        if not self.current_session_id:
            return
        session_data = self.storage.load_session(self.current_session_id)
        if not session_data:
            session_data = {
                "name": "Безымянный чат",
                "profile": self.current_profile.to_dict(),
                "history": self.conversation_history,
                "created": datetime.now().isoformat(),
                "local_descriptions": self.local_descriptions,
                "memory_summaries": self.memory_summaries      # новое поле
            }
        else:
            session_data["profile"] = self.current_profile.to_dict()
            session_data["history"] = self.conversation_history
            session_data["local_descriptions"] = self.local_descriptions
            session_data["memory_summaries"] = self.memory_summaries   # новое поле
        session_data["last_used"] = datetime.now().isoformat()
        self.storage.save_session(self.current_session_id, session_data)

    def _load_last_session(self):
        sessions = self.storage.list_sessions()
        if not sessions:
            self._handle_new_session()
            return
        latest_sid = None
        latest_time = None
        for sid in sessions:
            data = self.storage.load_session(sid)
            if data is None:
                continue  # повреждённая сессия — пропускаем
            last_used = data.get("last_used")
            if last_used:
                try:
                    dt = datetime.fromisoformat(last_used)
                    if latest_time is None or dt > latest_time:
                        latest_time = dt
                        latest_sid = sid
                except:
                    pass
        if latest_sid is None:
            # Все сессии повреждены — создаём новую
            self._handle_new_session()
        else:
            self._handle_load_session({"session_id": latest_sid})

    def _handle_save_current_session(self, data=None):
        self._save_current_session_safe()

    def _handle_clear_chat(self, data=None):
        if messagebox.askyesno("Очистить чат", "Вся история сообщений будет удалена без возможности восстановления. Продолжить?"):
            if self.is_generating:
                self.stop_generation_flag = True
            self.conversation_history = []
            self.last_user_message = ""
            # Сброс stage_data
            self.stage_data.update({
                "user_message": "",
                "descriptions": {},
                "scene_location_id": None,
                "scene_character_ids": [],
                "scene_item_ids": [],
                "scene_summary": "",
                "player_action_dice": None,
                "player_action_desc": "",
                "event_dice": None,
                "event_occurred": False,
                "event_desc": "",
                "turn_order": [],
                "npc_actions": {},
                "current_npc_index": 0,
                "final_response": ""
            })
            self.local_descriptions = {}
            self.memory_summaries = []
            self.last_original_response = None
            self.last_translated_response = None
            self._save_current_session_safe()
            self.center_panel.clear_chat()
            self.center_panel.display_message("Чат очищен.\n", "system")
            self.center_panel.update_translation_button_state()
            self.center_panel.update_token_count(0, 0)
            self._log_debug("MEMORY_CLEARED", "All memory summaries cleared")

    def _handle_delete_last_user_message(self, data=None):
        if self.is_generating:
            messagebox.showwarning("Генерация", "Сначала остановите генерацию (кнопка Стоп).")
            return
        if not self.conversation_history:
            return
        last_user_index = -1
        for i in range(len(self.conversation_history)-1, -1, -1):
            if self.conversation_history[i]["role"] == "user":
                last_user_index = i
                break
        if last_user_index == -1:
            messagebox.showinfo("Удаление", "Нет сообщений пользователя для удаления.")
            return
        self.conversation_history = self.conversation_history[:last_user_index]
        self._sync_last_user_message()              # <-- синхронизация после удаления
        self.last_original_response = None
        self.last_translated_response = None
        self._save_current_session_safe()
        self.center_panel.clear_chat()
        for msg in self.conversation_history:
            role = "Вы" if msg["role"] == "user" else "Ассистент"
            tag = "user" if msg["role"] == "user" else "assistant"
            self.center_panel.display_message(f"{role}: {msg['content']}\n\n", tag)
        self.center_panel.update_translation_button_state()
        messagebox.showinfo("Удаление", "Последнее сообщение пользователя и ответы на него удалены.")

    def _handle_new_session(self, data=None):
        def do_new():
            if self.current_session_id:
                self._save_current_session_safe()
            session_id = str(uuid.uuid4())
            default_name = f"Чат {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            new_profile = GameProfile(
                name=f"Profile_{session_id[:8]}",
                enabled_narrators=self.current_profile.enabled_narrators.copy(),
                enabled_characters=self.current_profile.enabled_characters.copy(),
                enabled_locations=self.current_profile.enabled_locations.copy(),
                enabled_items=self.current_profile.enabled_items.copy()
            )
            session_data = {
                "name": default_name,
                "profile": new_profile.to_dict(),
                "history": [],
                "created": datetime.now().isoformat(),
                "last_used": datetime.now().isoformat(),
                "local_descriptions": {}
            }
            self.storage.save_session(session_id, session_data)
            self.current_session_id = session_id
            self.current_profile = new_profile
            self.conversation_history = []
            self.local_descriptions = {}
            self.memory_summaries = []
            self.last_original_response = None
            self.last_translated_response = None
            self._sync_profile_with_objects()
            self.left_panel.refresh_session_list()
            self.center_panel.clear_chat()
            self.center_panel.display_message("Новая игровая сессия создана.\n", "system")
            self._refresh_all_ui()
            self.center_panel.update_translation_button_state()
            self.center_panel.update_token_count(0, 0)
        self._safe_stop_generation(do_new)

    def _sync_last_user_message(self):
        """Устанавливает last_user_message как последнее сообщение пользователя из истории."""
        for msg in reversed(self.conversation_history):
            if msg["role"] == "user":
                self.last_user_message = msg["content"]
                return
        self.last_user_message = ""

    def _handle_load_session(self, data):
        session_id = data.get("session_id")
        if not session_id:
            return
        def do_load():
            if self.current_session_id:
                self._save_current_session_safe()
            session_data = self.storage.load_session(session_id)
            if session_data is None:
                messagebox.showerror("Ошибка", "Сессия повреждена и не может быть загружена.\nПопробуйте удалить её вручную из папки data/sessions/")
                # Обновляем список сессий, чтобы повреждённая не отображалась
                self.left_panel.refresh_session_list()
                return
            self.current_session_id = session_id
            self.current_profile = GameProfile.from_dict(session_data.get("profile", {}))
            self.conversation_history = session_data.get("history", [])
            self.local_descriptions = session_data.get("local_descriptions", {})
            self.memory_summaries = session_data.get("memory_summaries", [])
            self._log_debug("MEMORY_LOADED", f"Loaded {len(self.memory_summaries)} summaries: {self.memory_summaries}")
            if self.memory_summaries:
                self.center_panel.display_system_message(f"🧠 Загружено {len(self.memory_summaries)} кратких резюме из памяти.\n")
            self._sync_last_user_message()          # <-- синхронизация последнего сообщения пользователя
            self.last_original_response = None
            self.last_translated_response = None
            self._sync_profile_with_objects()
            self.left_panel.refresh_session_list()
            self.center_panel.clear_chat()
            for msg in self.conversation_history:
                role = "Вы" if msg["role"] == "user" else "Ассистент"
                tag = "user" if msg["role"] == "user" else "assistant"
                self.center_panel.display_message(f"{role}: {msg['content']}\n\n", tag)
            self.center_panel.display_message(f"Загружена сессия: {session_data.get('name', 'Без имени')}\n", "system")
            self._refresh_all_ui()
            self.center_panel.update_translation_button_state()
            self.center_panel.update_token_count(0, 0)
            session_data["last_used"] = datetime.now().isoformat()
            self.storage.save_session(session_id, session_data)
        self._safe_stop_generation(do_load)

    def _handle_delete_session(self, data):
        session_id = data.get("session_id")
        if not session_id:
            return
        def do_delete():
            if messagebox.askyesno("Удаление", f"Удалить сессию '{self.left_panel.get_session_name(session_id)}'?"):
                self.storage.delete_session(session_id)
                if session_id == self.current_session_id:
                    sessions = self.storage.list_sessions()
                    if sessions:
                        self._load_last_session()
                    else:
                        self._handle_new_session()
                else:
                    self.left_panel.refresh_session_list()
        self._safe_stop_generation(do_delete)

    def _handle_rename_session(self, data):
        session_id = data.get("session_id")
        new_name = data.get("new_name")
        if not session_id or not new_name:
            return
        session_data = self.storage.load_session(session_id)
        if session_data:
            session_data["name"] = new_name
            self.storage.save_session(session_id, session_data)
            self.left_panel.refresh_session_list()

    # ---------- Regenerate ----------
    def _handle_regenerate_last_response(self, data=None):
        if self.is_generating:
            messagebox.showwarning("Генерация", "Модель уже генерирует ответ.")
            return
        if not self.last_user_message:
            messagebox.showinfo("Перегенерация", "Нет последнего сообщения пользователя.")
            return

        # Удаляем последний ответ ассистента из истории, если он есть
        if self.conversation_history and self.conversation_history[-1]["role"] == "assistant":
            self.conversation_history.pop()
            self._save_current_session_safe()

        # Очищаем чат и заново отображаем всю историю (кроме последнего ответа)
        self.center_panel.clear_chat()
        for msg in self.conversation_history:
            role = "Вы" if msg["role"] == "user" else "Ассистент"
            tag = "user" if msg["role"] == "user" else "assistant"
            self.center_panel.display_message(f"{role}: {msg['content']}\n\n", tag)

        # --- ПОЛНЫЙ СБРОС stage_data ---
        self.stage_data = {
            "user_message": self.last_user_message,   # сохраняем исходное сообщение
            "descriptions": {},
            "scene_location_id": None,
            "scene_character_ids": [],
            "scene_item_ids": [],
            "scene_summary": "",
            "player_action_dice": None,
            "player_action_desc": "",
            "event_dice": None,
            "event_occurred": False,
            "event_desc": "",
            "turn_order": [],
            "npc_actions": {},
            "current_npc_index": 0,
            "final_response": ""
        }

        self.last_original_response = None
        self.last_translated_response = None
        self.center_panel.update_translation_button_state()


        self._start_debug_log(f"REGENERATE: {self.last_user_message}")
        self._start_generation(self.last_user_message)

    def _handle_regenerate_translation(self, data=None):
        if self.is_generating:
            messagebox.showwarning("Генерация", "Модель уже генерирует ответ.")
            return
        if not self.enable_assistant_translation or not self.use_two_models:
            messagebox.showinfo("Перегенерация перевода", "Режим перевода не активен.")
            return
        if not self.last_original_response:
            messagebox.showinfo("Перегенерация перевода", "Нет сохранённого оригинального ответа.")
            return
        if self.conversation_history and self.conversation_history[-1]["role"] == "assistant":
            self.conversation_history.pop()
            self._save_current_session_safe()
        self.center_panel.remove_last_response()
        self._translate_response_stream(self.last_original_response, response_start_index=None)

    # ---------- Обработчики UI ----------
    def _handle_send_message(self, data):
        message = data.get("message", "").strip()
        if not message:
            return
        self.conversation_history.append({"role": "user", "content": message})
        self.last_user_message = message
        self._save_current_session_safe()
        self._start_debug_log(message)
        self._start_generation(message)

    def _handle_start_game(self, data=None):
        if messagebox.askyesno("Начать игру", "При начале игры вся текущая история чата будет удалена. Продолжить?"):
            self._handle_save_current_session()
            self.center_panel.clear_chat()
            self.conversation_history = []
            self.stage_data = {k: ([] if isinstance(v, list) else {} if isinstance(v, dict) else "" if isinstance(v, str) else None) for k, v in self.stage_data.items()}
            self.last_user_message = ""
            self.last_original_response = None
            self.last_translated_response = None
            self.center_panel.update_translation_button_state()
            self._start_debug_log("SYSTEM: Начнем игру")
            self.current_dice_sequences = self.generate_dice_sequences()
            self.dice_indices = [0, 0, 0]
            start_message = "Начнем игру. Пожалуйста, опиши, где находится персонаж игрока и что он видит."
            self._start_generation(start_message)

    def _handle_stop_generation(self, data=None):
        if self.is_generating:
            self.stop_generation_flag = True
            self._log_debug("USER_STOPPED_GENERATION")

    # ---------- Запуск поэтапной генерации ----------
    def _start_generation(self, user_message: str):
        if self.is_generating:
            messagebox.showwarning("Генерация", "Модель уже генерирует ответ.")
            return
        self.is_generating = True
        self.stop_generation_flag = False
        self.center_panel.set_input_state(tk.DISABLED)
        self.center_panel.start_new_response(clear_thinking=True)

        # Обновляем существующий словарь, а не создаём новый
        self.stage_data.update({
            "user_message": user_message,
            "descriptions": {},
            "scene_location_id": None,
            "scene_character_ids": [],
            "scene_item_ids": [],
            "scene_summary": "",
            "player_action_dice": None,
            "player_action_desc": "",
            "event_dice": None,
            "event_occurred": False,
            "event_desc": "",
            "turn_order": [],
            "npc_actions": {},
            "current_npc_index": 0,
            "final_response": ""
        })
        
        # Запускаем первый этап
        self.update("stage1_request_descriptions")

    # ---------- Этап 1: Запрос описаний объектов ----------
    def _stage1_request_descriptions(self, data=None, retry_count=0):
        # Извлекаем retry_count из data, если передан
        if isinstance(data, dict):
            retry_count = data.get("retry_count", 0)
        self._log_debug(f"=== STAGE1: request_descriptions (attempt {retry_count+1}) ===")
        self.center_panel.display_system_message(f"🔍 Этап 1/8: Определение объектов сцены (попытка {retry_count+1})...\n")
        
        objects_text = []
        for lid in self.current_profile.enabled_locations:
            loc = self.locations.get(lid)
            if loc:
                objects_text.append(f"Локация: {lid} - {loc.name}")
        for cid in self.current_profile.enabled_characters:
            char = self.characters.get(cid)
            if char:
                objects_text.append(f"Персонаж: {cid} - {char.name}{' (ИГРОК)' if char.is_player else ''}")
        for iid in self.current_profile.enabled_items:
            item = self.items.get(iid)
            if item:
                objects_text.append(f"Предмет: {iid} - {item.name}")
        available = "\n".join(objects_text) if objects_text else "Нет доступных объектов."

        prompt_template = self.prompt_manager.get_prompt_content("stage1_request_descriptions")
        main_prompt = prompt_template.format(
            user_message=self.stage_data["user_message"],
            available_objects=available
        )

        system_messages = self._build_context_messages(
            stage_name="stage1_request_descriptions",
            main_prompt=main_prompt
        )

        messages = [
            {"role": "user", "content": f"Сообщение игрока: {self.stage_data['user_message']}"}
        ] + system_messages

        self._send_model_request(messages, self._after_stage1_descriptions, extra={"retry_count": retry_count}, stage_name="stage1_request_descriptions")

    def _after_stage1_descriptions(self, tool_calls, content, extra=None):
        retry_count = extra.get("retry_count", 0) if extra else 0
        self._log_debug("AFTER stage1_descriptions", f"tool_calls: {tool_calls}\ncontent: {content[:500] if content else ''}")

        confirm_call = None
        for tc in tool_calls:
            if tc["function"]["name"] == "confirm_scene":
                confirm_call = tc
                break

        if not confirm_call:
            if retry_count < 2:
                self.center_panel.display_message(f"⚠️ Модель не вызвала confirm_scene. Повторная попытка ({retry_count+1}/2)...\n", "error")
                self.update("stage1_request_descriptions", {"retry_count": retry_count+1})
                return
            else:
                self.center_panel.display_message("❌ Модель не вызвала confirm_scene после 3 попыток. Генерация прервана.\n", "error")
                self.is_generating = False
                self.center_panel.set_input_state(tk.NORMAL)
                return

        try:
            args = json.loads(confirm_call["function"]["arguments"])
            location_id = args.get("location_id")
            character_ids = args.get("character_ids", [])
            item_ids = args.get("item_ids", [])

            self.stage_data["scene_location_id"] = location_id if location_id else None
            self.stage_data["scene_character_ids"] = character_ids
            self.stage_data["scene_item_ids"] = item_ids

            scene_parts = []
            if location_id:
                loc = self.locations.get(location_id)
                loc_name = loc.name if loc else location_id
                scene_parts.append(f"Локация: {loc_name} (ID: {location_id})")
            if character_ids:
                char_names = []
                for cid in character_ids:
                    char = self.characters.get(cid)
                    char_names.append(f"{char.name} (ID: {cid})" if char else cid)
                scene_parts.append(f"Персонажи: {', '.join(char_names)}")
            if item_ids:
                item_names = []
                for iid in item_ids:
                    item = self.items.get(iid)
                    item_names.append(f"{item.name} (ID: {iid})" if item else iid)
                scene_parts.append(f"Предметы: {', '.join(item_names)}")
            summary = "\n".join(scene_parts)
            self.stage_data["scene_summary"] = summary
            self.center_panel.display_system_message(f"✅ Сцена подтверждена моделью:\n{summary}\n")

            all_ids = [oid for oid in character_ids + item_ids + ([location_id] if location_id else []) if oid]
            for oid in all_ids:
                if oid not in self.stage_data["descriptions"]:
                    obj = self._get_object_by_id(oid)
                    if obj:
                        desc = self.get_object_description_with_local(oid)
                        self.stage_data["descriptions"][oid] = desc

            if self.stage_data["user_message"].startswith(("Начнем игру", "SYSTEM:")):
                self.center_panel.display_system_message("🎬 Генерация начальной сцены...\n")
                self.update("stage3_final")
            else:
                self.update("stage1_truth_check")
        except Exception as e:
            self._log_debug("ERROR", f"confirm_scene parse error: {e}")
            if retry_count < 2:
                self.center_panel.display_message(f"⚠️ Ошибка при обработке confirm_scene: {e}. Повтор ({retry_count+1}/2)...\n", "error")
                self.update("stage1_request_descriptions", {"retry_count": retry_count+1})
            else:
                self.center_panel.display_message(f"❌ Ошибка после 3 попыток: {e}. Генерация прервана.\n", "error")
                self.is_generating = False
                self.center_panel.set_input_state(tk.NORMAL)

    def _stage1_truth_check(self, data=None, retry_count=0):
        if isinstance(data, dict):
            retry_count = data.get("retry_count", 0)
        self._log_debug(f"=== STAGE1: truth_check (attempt {retry_count+1}) ===")
        self.center_panel.display_system_message(f"🔍 Этап 2/8: Проверка правдивости сообщения (попытка {retry_count+1})...\n")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        prompt_template = self.prompt_manager.get_prompt_content("stage1_truth_check")
        main_prompt = prompt_template.format(
            user_message=self.stage_data["user_message"],
            descriptions=descriptions_text
        )

        system_messages = self._build_context_messages(
            stage_name="stage1_truth_check",
            main_prompt=main_prompt
        )
        messages = [
            {"role": "user", "content": f"Проверь сообщение игрока на правдивость: {self.stage_data['user_message']}"}
        ] + system_messages

        self._send_model_request(messages, self._after_stage1_truth_check, extra={"retry_count": retry_count}, stage_name="stage1_truth_check")

    def _after_stage1_truth_check(self, tool_calls, content, extra=None):
        retry_count = extra.get("retry_count", 0) if extra else 0
        self._log_debug("AFTER stage1_truth_check", f"tool_calls: {tool_calls}")

        report_call = None
        for tc in tool_calls:
            if tc["function"]["name"] == "report_truth_check":
                report_call = tc
                break

        if not report_call:
            if retry_count < 2:
                self.center_panel.display_message(f"⚠️ Модель не вызвала report_truth_check. Повтор ({retry_count+1}/2)...\n", "error")
                self.update("stage1_truth_check", {"retry_count": retry_count+1})
                return
            else:
                self.center_panel.display_message("❌ Модель не вызвала report_truth_check после 3 попыток. Продолжаем без проверки.\n", "error")
                self.stage_data["truth_violation"] = ""
                self.update("stage1_player_action")
                return

        try:
            args = json.loads(report_call["function"]["arguments"])
            violation = args.get("violation", "")
            self.stage_data["truth_violation"] = violation
            if violation:
                self.center_panel.display_system_message(f"⚠️ Обнаружено нарушение: {violation[:200]}...\n")
            else:
                self.center_panel.display_system_message("✅ Сообщение игрока не противоречит известным фактам.\n")
            self.update("stage1_player_action")
        except Exception as e:
            self._log_debug("ERROR", f"report_truth_check parse error: {e}")
            if retry_count < 2:
                self.center_panel.display_message(f"⚠️ Ошибка обработки report_truth_check: {e}. Повтор ({retry_count+1}/2)...\n", "error")
                self.update("stage1_truth_check", {"retry_count": retry_count+1})
            else:
                self.center_panel.display_message(f"❌ Ошибка после 3 попыток: {e}. Продолжаем без проверки.\n", "error")
                self.stage_data["truth_violation"] = ""
                self.update("stage1_player_action")

    # ---------- Этап 2: Действие игрока и бросок d20 ----------
    def _stage1_player_action(self, data=None, retry_count=0):
        if isinstance(data, dict):
            retry_count = data.get("retry_count", 0)
        self._log_debug(f"=== STAGE1: player_action (attempt {retry_count+1}) ===")
        self.center_panel.display_system_message(f"🎲 Этап 3/8: Обработка действия игрока (попытка {retry_count+1})...\n")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        dice_rules = self.prompt_manager.get_prompt_content("dice_rules")
        violation_text = self.stage_data.get("truth_violation", "")
        violation_section = f"\nВНИМАНИЕ: Игрок попытался смошенничать или противоречить фактам:\n{violation_text}\n" if violation_text else ""
        prompt_template = self.prompt_manager.get_prompt_content("stage1_player_action")
        main_prompt = prompt_template.format(
            user_message=self.stage_data["user_message"],
            descriptions=descriptions_text,
            dice_rules=dice_rules,
            truth_violation=violation_section
        )

        system_messages = self._build_context_messages(
            stage_name="stage1_player_action",
            main_prompt=main_prompt
        )

        messages = [
            {"role": "user", "content": f"Игрок хочет: {self.stage_data['user_message']}. Вызови roll_dice(dice_type='d20'), получи результат, опиши действие и вызови report_player_action. Учти информацию о нарушении, если она есть."}
        ] + system_messages

        self._send_model_request(messages, self._after_stage1_player_action, extra={"retry_count": retry_count}, expect_tool_calls=True, stage_name="stage1_player_action")

    def _after_stage1_player_action(self, tool_calls, content, extra=None):
        retry_count = extra.get("retry_count", 0) if extra else 0
        self._log_debug("AFTER stage1_player_action", f"tool_calls: {tool_calls}")

        report_call = None
        for tc in tool_calls:
            if tc["function"]["name"] == "report_player_action":
                report_call = tc
                break

        if not report_call:
            if retry_count < 2:
                self.center_panel.display_message(f"⚠️ Модель не вызвала report_player_action. Повтор ({retry_count+1}/2)...\n", "error")
                self.update("stage1_player_action", {"retry_count": retry_count+1})
                return
            else:
                self.center_panel.display_message("❌ Модель не вызвала report_player_action после 3 попыток. Генерация прервана.\n", "error")
                self.is_generating = False
                self.center_panel.set_input_state(tk.NORMAL)
                return

        try:
            args = json.loads(report_call["function"]["arguments"])
            dice_value = args.get("dice_value")
            description = args.get("description", "")
            self.stage_data["player_action_dice"] = dice_value
            self.stage_data["player_action_desc"] = description
            self.center_panel.display_system_message(f"🎲 Бросок d20: {dice_value}\n")
            self.center_panel.display_system_message(f"✍️ Результат: {description[:100]}...\n")
            self.update("stage1_random_event")
        except Exception as e:
            self._log_debug("ERROR", f"report_player_action parse error: {e}")
            if retry_count < 2:
                self.center_panel.display_message(f"⚠️ Ошибка обработки report_player_action: {e}. Повтор ({retry_count+1}/2)...\n", "error")
                self.update("stage1_player_action", {"retry_count": retry_count+1})
            else:
                self.center_panel.display_message(f"❌ Ошибка после 3 попыток: {e}. Генерация прервана.\n", "error")
                self.is_generating = False
                self.center_panel.set_input_state(tk.NORMAL)

    # ---------- Этап 3: Случайное событие ----------
    def _stage1_random_event(self, data=None, retry_count=0):
        if isinstance(data, dict):
            retry_count = data.get("retry_count", 0)
        self._log_debug(f"=== STAGE1: random_event (attempt {retry_count+1}) ===")
        self.center_panel.display_system_message(f"🎲 Этап 4/8: Проверка случайного события (попытка {retry_count+1})...\n")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        prompt_template = self.prompt_manager.get_prompt_content("stage1_random_event")
        main_prompt = prompt_template.format(
            descriptions=descriptions_text,
            player_action=self.stage_data["player_action_desc"]
        )

        system_messages = self._build_context_messages(
            stage_name="stage1_random_event",
            main_prompt=main_prompt
        )
        messages = [
            {"role": "user", "content": f"Проверь случайное событие. Сначала вызови roll_dice(dice_type='d100'), определи, произошло ли событие. Если да – вызови roll_dice(dice_type='d20') для качества, затем report_random_event. Если нет – report_random_event с event_occurred=false."}
        ] + system_messages

        self._send_model_request(messages, self._after_stage1_random_event, extra={"retry_count": retry_count}, stage_name="stage1_random_event")

    def _after_stage1_random_event(self, tool_calls, content, extra=None):
        retry_count = extra.get("retry_count", 0) if extra else 0
        self._log_debug("AFTER stage1_random_event", f"tool_calls: {tool_calls}")

        report_call = None
        for tc in tool_calls:
            if tc["function"]["name"] == "report_random_event":
                report_call = tc
                break

        if not report_call:
            # fallback: пытаемся извлечь из текста
            if content and isinstance(content, str):
                import re
                d100_match = re.search(r'd100[^\d]*(\d{1,3})', content, re.IGNORECASE)
                no_event_keywords = ["не произошло", "не случилось", "ничего не", "события нет", "не было"]
                event_occurred = not any(kw in content.lower() for kw in no_event_keywords)
                if d100_match:
                    dice_val = int(d100_match.group(1))
                    if dice_val > 30 and not event_occurred:
                        self.stage_data["event_occurred"] = False
                        self.stage_data["event_desc"] = ""
                        self.stage_data["event_dice"] = dice_val
                        self.center_panel.display_system_message("✅ Случайное событие не произошло (определено по тексту).\n")
                        self.update("stage1_turn_order")
                        return
                    desc_match = re.search(r'(?:описание|событие|произошло)[:：]\s*(.+?)(?=\n|$)', content, re.IGNORECASE)
                    event_desc = desc_match.group(1).strip() if desc_match else "Произошло что-то неопределённое."
                    self.stage_data["event_occurred"] = True
                    self.stage_data["event_desc"] = event_desc[:200]
                    self.stage_data["event_dice"] = dice_val
                    self.center_panel.display_system_message(f"✨ Событие (из текста): {event_desc[:100]}...\n")
                    self.update("stage1_turn_order")
                    return

            # Если не удалось
            if retry_count < 2:
                self.center_panel.display_message(f"⚠️ Модель не вызвала report_random_event. Повтор ({retry_count+1}/2)...\n", "error")
                self.update("stage1_random_event", {"retry_count": retry_count+1})
                return
            else:
                self.center_panel.display_message("❌ Модель не вызвала report_random_event после 3 попыток. Генерация прервана.\n", "error")
                self.is_generating = False
                self.center_panel.set_input_state(tk.NORMAL)
                return

        try:
            args = json.loads(report_call["function"]["arguments"])
            dice_value = args.get("dice_value")
            event_occurred = args.get("event_occurred", False)
            event_desc = args.get("description", "")
            self.stage_data["event_occurred"] = event_occurred
            self.stage_data["event_desc"] = event_desc
            self.stage_data["event_dice"] = dice_value
            if event_occurred:
                self.center_panel.display_system_message(f"✨ Событие: {event_desc[:100]}...\n")
            else:
                self.center_panel.display_system_message("✅ Случайное событие не произошло.\n")
            self.update("stage1_turn_order")
        except Exception as e:
            self._log_debug("ERROR", f"report_random_event parse error: {e}")
            if retry_count < 2:
                self.center_panel.display_message(f"⚠️ Ошибка обработки report_random_event: {e}. Повтор ({retry_count+1}/2)...\n", "error")
                self.update("stage1_random_event", {"retry_count": retry_count+1})
            else:
                self.center_panel.display_message(f"❌ Ошибка после 3 попыток: {e}. Генерация прервана.\n", "error")
                self.is_generating = False
                self.center_panel.set_input_state(tk.NORMAL)

    # ---------- Этап 4: Определение порядка ходов NPC ----------
    def _stage1_turn_order(self, data=None, retry_count=0):
        if isinstance(data, dict):
            retry_count = data.get("retry_count", 0)
        self._log_debug(f"=== STAGE1: turn_order (attempt {retry_count+1}) ===")
        self.center_panel.display_system_message(f"📋 Этап 5/8: Определение порядка NPC (попытка {retry_count+1})...\n")

        npc_ids = [cid for cid in self.stage_data.get("scene_character_ids", [])
                if not self.characters.get(cid, Character()).is_player]
        if not npc_ids:
            self.center_panel.display_system_message("Нет NPC в сцене. Переход к финальному этапу.\n")
            self.update("stage3_final")
            return

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        scene_info = f"""
        Локация: {self.stage_data.get('scene_location_id', 'не определена')}
        Персонажи на сцене: {', '.join(self.stage_data.get('scene_character_ids', []))}
        Предметы: {', '.join(self.stage_data.get('scene_item_ids', []))}
        Результат действия игрока: {self.stage_data.get('player_action_desc', 'нет')}
        Случайное событие: {self.stage_data.get('event_desc', 'нет') if self.stage_data.get('event_occurred') else 'нет'}
        """
        prompt_template = self.prompt_manager.get_prompt_content("stage1_turn_order")
        main_prompt = prompt_template.format(
            scene_info=scene_info,
            npcs_list="\n".join([f"{cid}: {self.characters.get(cid, Character()).name}" for cid in npc_ids])
        )

        system_messages = self._build_context_messages(
            stage_name="stage1_turn_order",
            main_prompt=main_prompt
        )
        messages = [
            {"role": "user", "content": f"Определи порядок ходов для NPC на основе описания сцены. Вызови report_turn_order с массивом character_ids."}
        ] + system_messages

        self._send_model_request(messages, self._after_stage1_turn_order, extra={"retry_count": retry_count}, stage_name="stage1_turn_order")

    def _after_stage1_turn_order(self, tool_calls, content, extra=None):
        retry_count = extra.get("retry_count", 0) if extra else 0
        for tc in tool_calls:
            if tc["function"]["name"] == "report_turn_order":
                try:
                    args = json.loads(tc["function"]["arguments"])
                    self.stage_data["turn_order"] = args.get("character_ids", [])
                    self.center_panel.display_system_message(f"✅ Порядок ходов: {', '.join([self.characters.get(cid, Character()).name for cid in self.stage_data['turn_order']])}\n")
                    self.update("stage2_process_npc")
                    return
                except Exception as e:
                    self._log_debug("ERROR", f"report_turn_order parse error: {e}")

        # fallback
        npc_ids = [cid for cid in self.stage_data.get("scene_character_ids", [])
                if not self.characters.get(cid, Character()).is_player]
        if retry_count < 2:
            self.center_panel.display_message(f"⚠️ Модель не вызвала report_turn_order. Повтор ({retry_count+1}/2)...\n", "error")
            self.update("stage1_turn_order", {"retry_count": retry_count+1})
        else:
            self.stage_data["turn_order"] = sorted(npc_ids)
            self.center_panel.display_message("⚠️ Модель не вызвала report_turn_order. Использован порядок по умолчанию.\n", "error")
            self.update("stage2_process_npc")

    # ---------- Этап 5: Обработка действий NPC (по одному за раз) ----------
    def _stage2_process_npc(self, data=None, retry_count=0):
        if isinstance(data, dict):
            retry_count = data.get("retry_count", 0)
        self._log_debug(f"=== STAGE2: process_npc (attempt {retry_count+1}) ===")
        self.center_panel.display_system_message(f"🎭 Этап 6/8: Обработка NPC (попытка {retry_count+1})...\n")
        if self.stage_data["current_npc_index"] >= len(self.stage_data["turn_order"]):
            self.center_panel.display_system_message("✅ Все NPC обработаны. Переход к финальному этапу.\n")
            self.update("stage3_final")
            return

        npc_id = self.stage_data["turn_order"][self.stage_data["current_npc_index"]]
        npc = self.characters.get(npc_id)
        if not npc:
            self.stage_data["current_npc_index"] += 1
            self.update("stage2_process_npc")
            return

        self._log_debug(f"=== STAGE2: processing NPC {npc_id} ({npc.name}) attempt {retry_count+1} ===")
        self.center_panel.display_system_message(f"🎭 Планирование действий NPC: {npc.name} (попытка {retry_count+1})...\n")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        previous_actions = "\n".join([f"{self.characters.get(cid, Character()).name}: {act}" 
                                    for cid, act in self.stage_data["npc_actions"].items()])

        prompt_template = self.prompt_manager.get_prompt_content("stage2_npc_action")
        main_prompt = prompt_template.format(
            npc_name=npc.name,
            npc_id=npc_id,
            descriptions=descriptions_text,
            player_action=self.stage_data["player_action_desc"],
            event_description=self.stage_data["event_desc"] if self.stage_data["event_occurred"] else "Нет события",
            previous_actions=previous_actions if previous_actions else "Нет"
        )

        system_messages = self._build_context_messages(
            stage_name="stage2_npc_action",
            main_prompt=main_prompt
        )
        messages = [
            {"role": "user", "content": f"Опиши мысли и намерения {npc.name}."}
        ] + system_messages

        self._send_model_request(messages, self._after_stage2_npc_action, 
                                extra={"npc_id": npc_id, "retry_count": retry_count}, 
                                expect_tool_calls=False, 
                                stage_name="stage2_npc_action")

    def _after_stage2_npc_action(self, tool_calls, content, extra):
        npc_id = extra["npc_id"]
        retry_count = extra.get("retry_count", 0)
        self._log_debug(f"AFTER stage2_npc_action for {npc_id}", f"content: {content[:500] if content else ''}")
        if content.strip():
            self.stage_data["npc_actions"][npc_id] = content.strip()
            self.center_panel.display_system_message(f"✍️ {self.characters.get(npc_id, Character()).name}: {self.stage_data['npc_actions'][npc_id][:100]}...\n")
            self.stage_data["current_npc_index"] += 1
            self.update("stage2_process_npc")
        else:
            if retry_count < 2:
                self.center_panel.display_message(f"⚠️ Модель не вернула описание для {self.characters.get(npc_id, Character()).name}. Повтор ({retry_count+1}/2)...\n", "error")
                self.update("stage2_process_npc", {"retry_count": retry_count+1})
            else:
                self.stage_data["npc_actions"][npc_id] = f"{self.characters.get(npc_id, Character()).name} задумался, но не предпринимает явных действий."
                self.center_panel.display_system_message(f"⚠️ {self.characters.get(npc_id, Character()).name} не получил описания, используется значение по умолчанию.\n")
                self.stage_data["current_npc_index"] += 1
                self.update("stage2_process_npc")

    # ---------- Этап 6: Финальное повествование ----------
    def _stage3_final(self, data=None, retry_count=0):
        if isinstance(data, dict):
            retry_count = data.get("retry_count", 0)
        self._log_debug(f"=== STAGE3: final narration (attempt {retry_count+1}) ===")
        self.center_panel.display_system_message(f"📖 Этап 7/8: Генерация финального ответа (попытка {retry_count+1})...\n")

        location_id = self.stage_data.get("scene_location_id")
        location_desc = self.stage_data["descriptions"].get(location_id, "Локация не описана") if location_id else "Локация не определена"

        npc_actions_text = ""
        npc_ids = self.stage_data.get("turn_order", [])
        for npc_id in npc_ids:
            npc = self.characters.get(npc_id)
            if npc and npc_id in self.stage_data["npc_actions"]:
                npc_actions_text += f"{npc.name}: {self.stage_data['npc_actions'][npc_id]}\n"

        is_game_start = self.stage_data["user_message"].startswith(("Начнем игру", "SYSTEM:"))
        if is_game_start:
            player_action_outcome = "Ты только начинаешь своё приключение."
            event_description = "Вокруг тихо и спокойно."
        else:
            player_action_outcome = self.stage_data["player_action_desc"]
            event_description = self.stage_data["event_desc"] if self.stage_data["event_occurred"] else "Ничего не произошло"

        dice_rules = self.prompt_manager.get_prompt_content("dice_rules")

        # Автоматические броски для NPC (без участия модели)
        dice_results = []
        for npc_id in npc_ids:
            npc = self.characters.get(npc_id)
            if not npc:
                continue
            dice_val = self.get_next_dice_value("d20") or random.randint(1, 20)
            result_text = {1:"крит.провал",2:"провал",3:"провал",4:"провал"}.get(dice_val, 
                        "успех" if 5 <= dice_val <= 15 else "большой успех" if dice_val <= 19 else "крит.успех")
            dice_results.append(f"{npc.name}: бросок d20 = {dice_val} → {result_text}")
            self.stage_data.setdefault("npc_dice", {})[npc_id] = dice_val
        dice_summary = "\n".join(dice_results) if dice_results else "Нет NPC."

        # Промт без требований вызывать функции
        prompt = (
            f"Ты — рассказчик. Опиши результат действий игрока и NPC.\n\n"
            f"Локация: {location_desc}\n"
            f"Действие игрока: {player_action_outcome}\n"
            f"Событие: {event_description}\n"
            f"Намерения NPC:\n{npc_actions_text}\n"
            f"Результаты бросков NPC (уже известны):\n{dice_summary}\n"
            f"Правила: {dice_rules}\n\n"
            "Напиши связный рассказ от второго лица ('ты'), 4-8 предложений.\n"
            "Не упоминай броски кубиков и ID объектов.\n"
            "Описывай только реальные действия, слова, звуки, последствия (не намерения).\n"
            "Просто текст, без вызовов функций."
        )

        messages = [{"role": "user", "content": prompt}] + self._build_context_messages(stage_name="stage3_final", main_prompt="")
        self.center_panel.start_temp_response()
        self._send_model_request(messages, self._after_stage3_final, extra={"retry_count": retry_count}, stage_name="stage3_final", use_temp=True, expect_tool_calls=False)

    def _after_stage3_final(self, tool_calls, content, extra=None):
        retry_count = extra.get("retry_count", 0) if extra else 0
        self._log_debug("AFTER stage3_final", f"content: {content[:500] if content else ''}")

        final_text = content.strip()
        if not final_text:
            if retry_count < 2:
                self.center_panel.display_message("⚠️ Модель не сгенерировала ответ. Повтор...\n", "error")
                self.update("stage3_final", {"retry_count": retry_count+1})
                return
            else:
                final_text = "(Рассказчик молчит)"

        self.center_panel.clear_temp_response()
        self.center_panel.display_message(f"\nАссистент: {final_text}\n\n", "assistant")
        self.conversation_history.append({"role": "assistant", "content": final_text})
        self.stage_data["final_response"] = final_text

        # Переход к генерации памяти
        self.update("stage4_summary")

    def _stage4_summary(self, data=None, retry_count=0):
        if isinstance(data, dict):
            retry_count = data.get("retry_count", 0)
        self._log_debug(f"=== STAGE4: memory summary (attempt {retry_count+1}) ===")
        self.center_panel.display_system_message(f"📝 Этап 8/8: Сохранение краткой памяти (попытка {retry_count+1})...\n")

        last_user_msg = self.last_user_message
        last_assistant_msg = self.stage_data.get("final_response", "")
        if not last_assistant_msg and self.conversation_history:
            for msg in reversed(self.conversation_history):
                if msg["role"] == "assistant":
                    last_assistant_msg = msg["content"]
                    break

        prompt = (
            "Ты — помощник, который ведёт краткую историю игры.\n"
            "На основе последнего действия игрока и ответа рассказчика напиши **одно предложение** (на русском),\n"
            "которое резюмирует ключевое изменение в мире, действии игрока или состоянии NPC.\n"
            "Не пиши ничего лишнего, только факт.\n\n"
            f"Действие игрока: {last_user_msg}\n"
            f"Ответ рассказчика: {last_assistant_msg}\n\n"
            "Краткая история (одно предложение):"
        )

        messages = [
            {"role": "system", "content": "Ты — полезный ассистент, который кратко резюмирует события."},
            {"role": "user", "content": prompt}
        ]

        # Используем временный вывод, чтобы итоговый summary не попал в основной чат
        self.center_panel.start_temp_response()
        self._send_model_request(
            messages,
            self._after_stage4_summary,
            extra={"retry_count": retry_count},
            expect_tool_calls=False,
            stage_name="stage4_summary",
            use_temp=True   # <-- временный вывод, потом очистим
        )

    def _after_stage4_summary(self, tool_calls, content, extra=None):
        retry_count = extra.get("retry_count", 0) if extra else 0
        self._log_debug("AFTER stage4_summary", f"content: {content[:200] if content else ''}")

        # Очищаем временный вывод (сам summary)
        self.center_panel.clear_temp_response()

        summary = content.strip()
        if not summary:
            if retry_count < 2:
                self.center_panel.display_message("⚠️ Не удалось получить краткую память. Повтор...\n", "error")
                self.update("stage4_summary", {"retry_count": retry_count+1})
                return
            else:
                summary = "Игрок продолжил свои действия."

        self.memory_summary = summary
        self.stage_data["memory_summary"] = summary
        self._save_current_session_safe()

        # Выводим только системное сообщение, без дублирования summary
        self.center_panel.display_system_message(f"🧠 Краткая память сохранена: {summary[:100]}...\n")

        self.is_generating = False
        self.center_panel.set_input_state(tk.NORMAL)
        self.center_panel.update_translation_button_state()
        self.current_debug_log_path = None
        self._log_debug("GENERATION_COMPLETED_WITH_MEMORY", summary)

    def _continue_random_event_with_dice(self, dice20_value: int):
        """Продолжает генерацию события, отправляя модели результат броска d20."""
        self.center_panel.display_system_message(f"🎲 Бросок d20 для события: {dice20_value}\n")
        
        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        prompt_template = self.prompt_manager.get_prompt_content("stage1_random_event_continue")  # новый промт
        main_prompt = prompt_template.format(
            dice20=dice20_value,
            descriptions=descriptions_text,
            player_action=self.stage_data["player_action_desc"]
        )
        
        system_messages = self._build_context_messages(
            stage_name="stage1_random_event_continue",
            main_prompt=main_prompt
        )
        messages = [
            {"role": "user", "content": f"Результат броска d20 для события: {dice20_value}. Опиши событие и вызови report_random_event."}
        ] + system_messages
        
        # Отправляем новый запрос, ожидая report_random_event
        self._send_model_request(messages, self._after_stage1_random_event, stage_name="stage1_random_event_continue")

    def _handle_generate_random_event(self, arguments: dict) -> dict:
        """Генерирует бросок d20 и возвращает результат модели."""
        dice_type = arguments.get("dice_type", "d20")
        if dice_type != "d20":
            dice_type = "d20"
        dice_value = self.get_next_dice_value("d20")
        if dice_value is None:
            dice_value = random.randint(1, 20)
        return {"dice_type": dice_type, "dice_value": dice_value}

    def _send_model_request(self, messages: List[Dict], callback, extra=None, expect_tool_calls=True, stage_name: str = None, use_temp: bool = False, tools_override=None):
        """
        Отправляет запрос к модели с поддержкой интерактивных tool calls.
        Если модель вызывает roll_dice или send_object_info, скрипт выполняет их и продолжает диалог.
        Другие инструменты (report_*) просто сохраняются и передаются в callback.
        
        Параметры:
            tools_override: если передан, используется этот список инструментов вместо стандартного.
                            Например, [] или [{"type":"function","function":{...}}]
        """
        if self.use_two_models:
            model = self.primary_model
            temp = self.primary_temperature
            max_tok = self.primary_max_tokens
        else:
            model = self.model_name
            temp = self.settings.get("temperature", 0.7)
            max_tok = self.settings.get("max_tokens", 4096)

        # Формируем читаемый лог
        full_prompt_lines = []
        full_prompt_lines.append(f"=== МОДЕЛЬ: {model} ===")
        full_prompt_lines.append(f"Температура: {temp}, Max tokens: {max_tok}\n")
        for i, msg in enumerate(messages, 1):
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")
            full_prompt_lines.append(f"[{i}] {role}:")
            for line in content.split('\n'):
                full_prompt_lines.append(f"  {line}")
            full_prompt_lines.append("")
        full_prompt = "\n".join(full_prompt_lines)
        self.center_panel.log_system_prompt(full_prompt, stage_name)
        self._log_debug("SEND_MODEL_REQUEST", full_prompt)

        # Рекурсивный внутренний цикл для обработки tool calls
        def _chat_loop(current_messages, depth=0):
            if depth > 10:
                self.after(0, lambda: self.center_panel.display_message("\n[Ошибка: слишком много итераций tool calls]\n", "error"))
                self.after(0, lambda: setattr(self, 'is_generating', False))
                self.after(0, lambda: self.center_panel.set_input_state(tk.NORMAL))
                return

            def stream_and_process():
                full_content = ""
                tool_calls = []
                reasoning_buffer = ""
                error = None
                try:
                    # Определяем список инструментов для этого запроса
                    if tools_override is not None:
                        tools = tools_override
                    else:
                        # Стандартный список инструментов (как в LMStudioClient, но мы берём его из атрибута или создаём)
                        # Чтобы не дублировать, можно получить из self.lm_client, но проще определить здесь же
                        tools = [
                            {
                                "type": "function",
                                "function": {
                                    "name": "confirm_scene",
                                    "description": "Подтверждает окончательный состав сцены после проверки описаний объектов.",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {
                                            "location_id": {"type": "string", "description": "ID локации"},
                                            "character_ids": {"type": "array", "items": {"type": "string"}},
                                            "item_ids": {"type": "array", "items": {"type": "string"}}
                                        },
                                        "required": ["location_id", "character_ids", "item_ids"]
                                    }
                                }
                            },
                            {
                                "type": "function",
                                "function": {
                                    "name": "report_truth_check",
                                    "description": "Сообщает результат проверки правдивости сообщения игрока.",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {
                                            "violation": {"type": "string", "description": "Описание нарушения или пустая строка"}
                                        },
                                        "required": ["violation"]
                                    }
                                }
                            },
                            {
                                "type": "function",
                                "function": {
                                    "name": "send_object_info",
                                    "description": "Запрашивает полные описания объектов по их ID.",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {
                                            "object_ids": {"type": "array", "items": {"type": "string"}}
                                        },
                                        "required": ["object_ids"]
                                    }
                                }
                            },
                            {
                                "type": "function",
                                "function": {
                                    "name": "roll_dice",
                                    "description": "Бросает кубик указанного типа и возвращает результат.",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {
                                            "dice_type": {"type": "string", "enum": ["d20", "d100", "d6"]}
                                        },
                                        "required": ["dice_type"]
                                    }
                                }
                            },
                            {
                                "type": "function",
                                "function": {
                                    "name": "generate_random_event",
                                    "description": "Генерирует случайное событие на основе броска кубика.",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {
                                            "dice_type": {"type": "string", "enum": ["d20", "d100", "d6"]},
                                            "chance": {"type": "integer", "description": "Шанс события в процентах (0-100)"}
                                        },
                                        "required": ["dice_type"]
                                    }
                                }
                            },
                            {
                                "type": "function",
                                "function": {
                                    "name": "report_player_action",
                                    "description": "Сообщает результат действия игрока после броска d20.",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {
                                            "dice_value": {"type": "integer"},
                                            "description": {"type": "string"}
                                        },
                                        "required": ["dice_value", "description"]
                                    }
                                }
                            },
                            {
                                "type": "function",
                                "function": {
                                    "name": "report_random_event",
                                    "description": "Сообщает результат проверки случайного события.",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {
                                            "dice_value": {"type": "integer"},
                                            "event_occurred": {"type": "boolean"},
                                            "description": {"type": "string"}
                                        },
                                        "required": ["dice_value", "event_occurred", "description"]
                                    }
                                }
                            },
                            {
                                "type": "function",
                                "function": {
                                    "name": "report_turn_order",
                                    "description": "Сообщает порядок ходов NPC.",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {
                                            "character_ids": {"type": "array", "items": {"type": "string"}}
                                        },
                                        "required": ["character_ids"]
                                    }
                                }
                            },
                            {
                                "type": "function",
                                "function": {
                                    "name": "report_npc_action",
                                    "description": "Сообщает действие NPC после броска d20.",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {
                                            "character_id": {"type": "string"},
                                            "dice_value": {"type": "integer"},
                                            "description": {"type": "string"}
                                        },
                                        "required": ["character_id", "dice_value", "description"]
                                    }
                                }
                            },
                        ]

                    for chunk in self.lm_client.chat_completion_stream(messages=current_messages, model=model, temperature=temp, max_tokens=max_tok, tools=tools):
                        if self.stop_generation_flag:
                            break
                        if chunk["type"] == "reasoning":
                            reasoning_buffer += chunk["text"]
                            self.after(0, lambda t=chunk["text"]: self.center_panel.append_thinking(t))
                        elif chunk["type"] == "tool_calls":
                            for tc in chunk["tool_calls"]:
                                idx = tc.get("index", 0)
                                while len(tool_calls) <= idx:
                                    tool_calls.append({"id": None, "type": "function", "function": {"name": "", "arguments": ""}})
                                if tc.get("id"):
                                    tool_calls[idx]["id"] = tc["id"]
                                if tc.get("function", {}).get("name"):
                                    tool_calls[idx]["function"]["name"] += tc["function"]["name"]
                                if tc.get("function", {}).get("arguments"):
                                    tool_calls[idx]["function"]["arguments"] += tc["function"]["arguments"]
                        elif chunk["type"] == "content":
                            full_content += chunk["text"]
                            if use_temp:
                                self.after(0, lambda t=chunk["text"]: self.center_panel.append_temp_content(t))
                            else:
                                self.after(0, lambda t=chunk["text"]: self.center_panel.append_response(t))
                        elif chunk["type"] == "error":
                            error = chunk["message"]
                            break
                except Exception as e:
                    error = str(e)

                if error:
                    self._log_debug("MODEL_ERROR", error=error)
                    self.after(0, lambda: self.center_panel.display_message(f"\n[Ошибка: {error}]\n", "error"))
                    self.after(0, lambda: setattr(self, 'is_generating', False))
                    self.after(0, lambda: self.center_panel.set_input_state(tk.NORMAL))
                    return
                if self.stop_generation_flag:
                    self.after(0, lambda: self.center_panel.display_message("\n[Остановлено]\n", "system"))
                    self.after(0, lambda: setattr(self, 'is_generating', False))
                    self.after(0, lambda: self.center_panel.set_input_state(tk.NORMAL))
                    return

                # Обрабатываем вызовы, требующие ответа (roll_dice, send_object_info)
                handled_calls = []
                for tc in tool_calls:
                    name = tc["function"]["name"]
                    if name == "roll_dice":
                        try:
                            args = json.loads(tc["function"]["arguments"])
                            dice_type = args.get("dice_type", "d20")
                            if dice_type == "d20":
                                value = random.randint(1, 20)
                            elif dice_type == "d100":
                                value = random.randint(1, 100)
                            elif dice_type == "d6":
                                value = random.randint(1, 6)
                            else:
                                value = random.randint(1, 20)
                            tool_response = {
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": json.dumps({"dice_value": value})
                            }
                            current_messages.append(tool_response)
                            handled_calls.append(tc)
                            self._log_debug("ROLL_DICE", f"{dice_type} -> {value}")
                            self.after(0, lambda t=dice_type, v=value: self.center_panel.display_system_message(f"🎲 {t} → {v}\n"))
                        except Exception as e:
                            self._log_debug("ROLL_DICE_ERROR", str(e))
                            tool_response = {
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": json.dumps({"error": str(e)})
                            }
                            current_messages.append(tool_response)
                            handled_calls.append(tc)
                    elif name == "send_object_info":
                        try:
                            args = json.loads(tc["function"]["arguments"])
                            result = self._handle_send_object_info(args)
                            descriptions = result.get("descriptions", {})
                            desc_text = "\n".join([f"{oid}: {desc}" for oid, desc in descriptions.items()])
                            tool_response = {
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": json.dumps({"descriptions": descriptions})
                            }
                            current_messages.append(tool_response)
                            current_messages.append({
                                "role": "user",
                                "content": f"Вот описания запрошенных объектов:\n{desc_text}\n\nТеперь проанализируй их и, если нужно, вызови confirm_scene."
                            })
                            handled_calls.append(tc)
                            self._log_debug("send_object_info processed", str(args))
                        except Exception as e:
                            self._log_debug("send_object_info ERROR", str(e))
                            tool_response = {
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": json.dumps({"error": str(e)})
                            }
                            current_messages.append(tool_response)
                            handled_calls.append(tc)

                # Если были обработанные вызовы, продолжаем цикл
                if handled_calls:
                    has_assistant_msg = any(msg.get("role") == "assistant" and msg.get("tool_calls") for msg in current_messages)
                    if not has_assistant_msg:
                        assistant_msg = {"role": "assistant", "content": full_content or None, "tool_calls": tool_calls}
                        current_messages.append(assistant_msg)
                    self.after(0, lambda: _chat_loop(current_messages, depth+1))
                    return

                # Если есть другие tool_calls (report_*), не требующие ответа, передаём в callback
                if tool_calls and expect_tool_calls:
                    self.after(0, lambda: callback(tool_calls, full_content, extra))
                else:
                    self.after(0, lambda: callback([], full_content, extra))

            threading.Thread(target=stream_and_process, daemon=True).start()

        _chat_loop(messages.copy())

    # ---------- Общий метод отправки запроса к модели ----------
    def _build_context_messages(self, stage_name: str, main_prompt: str = "", extra_prompts: List[str] = None) -> List[Dict[str, str]]:
        messages = []

        # --- ВСТАВКА КРАТКОЙ ПАМЯТИ (если есть) ---
        if hasattr(self, 'memory_summary') and self.memory_summary:
            memory_text = f"Краткая история предыдущих событий (справочно, не заменяет инструкции ниже):\n{self.memory_summary}"
            messages.append({"role": "system", "content": memory_text})
            
        # 1. Сначала собираем все системные сообщения из конфигурации этапа
        config_messages = []
        config = self.stage_prompts_config.get(stage_name, [])
        for entry in config:
            if entry == stage_name:
                continue
            if entry.startswith("narrator:"):
                narr_id = entry[9:]
                narr = self.narrators.get(narr_id)
                if narr:
                    config_messages.append({"role": "system", "content": f"Ты — рассказчик. Твой стиль и манера повествования:\n{narr.description}"})
            elif entry.startswith("history"):
                # Историю пока пропускаем, добавим позже как user/assistant
                continue
            else:
                content = self.prompt_manager.get_prompt_content(entry)
                if content:
                    config_messages.append({"role": "system", "content": content})
        
        # 2. ВСТАВЛЯЕМ ПАМЯТЬ В САМОЕ НАЧАЛО (наименьший приоритет)
        if self.enable_memory_summary and self.memory_summaries:
            memory_text = (
                "Краткая история предыдущих событий (справочно, не заменяет инструкции ниже):\n"
                + "\n".join(f"- {s}" for s in self.memory_summaries)
            )
            messages.append({"role": "system", "content": memory_text})
        
        # 3. Добавляем остальные системные сообщения из конфигурации
        messages.extend(config_messages)
        
        # 4. Добавляем историю чата (user/assistant) если нужно
        for entry in config:
            if entry.startswith("history"):
                parts = entry.split(":", 1)
                limit = None
                if len(parts) > 1 and parts[1].isdigit():
                    limit = int(parts[1])
                history = [msg for msg in self.conversation_history if msg["role"] in ("user", "assistant")]
                if limit is not None and limit > 0:
                    history = history[-limit:]
                for msg in history:
                    messages.append({"role": msg["role"], "content": msg["content"]})
                break  # обрабатываем только один history элемент
        
        # 5. В КОНЦЕ — самый важный системный промт (инструкции этапа)
        if main_prompt:
            messages.append({"role": "system", "content": main_prompt})
        if extra_prompts:
            for p in extra_prompts:
                messages.append({"role": "system", "content": p})
        
        return messages
    
    def _generate_memory_summary(self, user_msg: str, assistant_msg: str):
        """Генерирует краткое резюме важных событий последнего обмена и сохраняет в memory_summaries."""
        if not self.enable_memory_summary:
            return
        if not user_msg or not assistant_msg:
            return

        # Загружаем промт из менеджера (пользователь может его редактировать)
        prompt_template = self.prompt_manager.get_prompt_content("memory_summary_generation")
        if not prompt_template:
            # fallback, если вдруг промт отсутствует
            prompt_template = (
                "Сообщение игрока: {user_message}\nОтвет рассказчика: {assistant_message}\n"
                "Резюме (одно предложение на русском):"
            )
        main_prompt = prompt_template.format(
            user_message=user_msg,
            assistant_message=assistant_msg
        )

        messages = [{"role": "user", "content": main_prompt}]
        model = self.primary_model if self.use_two_models else self.model_name
        temp = 0.3
        max_tok = 150

        try:
            full_response = ""
            for chunk in self.lm_client.chat_completion_stream(
                messages=messages,
                model=model,
                temperature=temp,
                max_tokens=max_tok,
                tools=[]
            ):
                if chunk["type"] == "content":
                    full_response += chunk["text"]
                elif chunk["type"] == "error":
                    self._log_debug("MEMORY_SUMMARY_ERROR", chunk["message"])
                    return

            summary = full_response.strip()
            if summary:
                self.memory_summaries.append(summary)
                if len(self.memory_summaries) > self.max_memory_summaries:
                    self.memory_summaries = self.memory_summaries[-self.max_memory_summaries:]
                self._save_current_session_safe()
                self.center_panel.display_system_message(f"🧠 Добавлено в память: {summary}\n")
                self._log_debug("MEMORY_SUMMARY_ADDED", f"Summary: {summary}\nFull list: {self.memory_summaries}")
        except Exception as e:
            self._log_debug("MEMORY_SUMMARY_EXCEPTION", str(e))

    # ---------- Старые обработчики инструментов (адаптированы для stage_data) ----------
    def _handle_send_object_info(self, arguments: dict) -> Dict[str, Any]:
        object_ids_raw = arguments.get("object_ids", [])
        if isinstance(object_ids_raw, str):
            try:
                object_ids = json.loads(object_ids_raw)
            except:
                object_ids = [object_ids_raw]
        else:
            object_ids = object_ids_raw
        allowed_ids = []
        for obj_id in object_ids:
            if obj_id.startswith('n') and obj_id in self.current_profile.enabled_narrators:
                allowed_ids.append(obj_id)
            elif obj_id.startswith('c') and obj_id in self.current_profile.enabled_characters:
                allowed_ids.append(obj_id)
            elif obj_id.startswith('l') and obj_id in self.current_profile.enabled_locations:
                allowed_ids.append(obj_id)
            elif obj_id.startswith('i') and obj_id in self.current_profile.enabled_items:
                allowed_ids.append(obj_id)
        descriptions = {}
        for obj_id in allowed_ids:
            obj = self._get_object_by_id(obj_id)
            if obj:
                desc = self.get_object_description_with_local(obj_id)
                if isinstance(obj, Character) and (obj.inventory or obj.equipped):
                    if obj.inventory:
                        inv_names = [self.items.get(iid, Item(name="?")).name for iid in obj.inventory]
                        desc += f"\nИнвентарь: {', '.join(inv_names)}"
                    if obj.equipped:
                        eq_names = [self.items.get(iid, Item(name="?")).name for iid in obj.equipped]
                        desc += f"\nЭкипировано: {', '.join(eq_names)}"
                descriptions[obj_id] = desc
                self.stage_data["descriptions"][obj_id] = desc
            else:
                descriptions[obj_id] = f"Объект {obj_id} не найден."
        return {"descriptions": descriptions}

    # ---------- Прочие методы (без изменений) ----------
    def _load_all_data(self):
        for narr in self.storage.load_all_objects("narrators"):
            self.narrators[narr.id] = narr
        for char in self.storage.load_all_objects("characters"):
            self.characters[char.id] = char
        for loc in self.storage.load_all_objects("locations"):
            self.locations[loc.id] = loc
        for item in self.storage.load_all_objects("items"):
            self.items[item.id] = item

    def _sync_profile_with_objects(self):
        self.current_profile.enabled_narrators = [nid for nid in self.current_profile.enabled_narrators if nid in self.narrators]
        self.current_profile.enabled_characters = [cid for cid in self.current_profile.enabled_characters if cid in self.characters]
        self.current_profile.enabled_locations = [lid for lid in self.current_profile.enabled_locations if lid in self.locations]
        self.current_profile.enabled_items = [iid for iid in self.current_profile.enabled_items if iid in self.items]

    def get_object_description_with_local(self, obj_id: str) -> str:
        obj = self._get_object_by_id(obj_id)
        if not obj:
            return f"Объект {obj_id} не найден."
        global_desc = obj.description if obj.description else "Нет глобального описания."
        local_desc = self.local_descriptions.get(obj_id, "")
        if local_desc:
            return f"Глобальное описание: {global_desc}\nЛокальное описание: {local_desc}"
        else:
            return f"Описание: {global_desc}"

    # ---------- CRUD обработчики (без изменений) ----------
    def _handle_update_narrator(self, data):
        obj_id = data.get("id")
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        if not name:
            messagebox.showwarning("Ошибка", "Название рассказчика не может быть пустым.")
            return
        if obj_id and obj_id in self.narrators:
            narr = self.narrators[obj_id]
            narr.name = name
            narr.description = description
            self.storage.save_object("narrators", narr)
            messagebox.showinfo("Обновлено", f"Рассказчик '{name}' обновлён.")
        else:
            narr = Narrator(name=name, description=description)
            self.storage.save_object("narrators", narr)
            self.narrators[narr.id] = narr
            messagebox.showinfo("Создано", f"Рассказчик '{name}' создан (ID: {narr.id}).")
        self._refresh_all_ui()
        self._save_current_session_safe()

    def _handle_delete_narrator(self, data):
        obj_id = data.get("id")
        if not obj_id or obj_id not in self.narrators:
            return
        narr = self.narrators[obj_id]
        if messagebox.askyesno("Удаление", f"Удалить рассказчика '{narr.name}'?"):
            self.storage.delete_object("narrators", obj_id)
            del self.narrators[obj_id]
            if obj_id in self.current_profile.enabled_narrators:
                self.current_profile.enabled_narrators.remove(obj_id)
            self._refresh_all_ui()
            self._save_current_session_safe()
            messagebox.showinfo("Удалено", f"Рассказчик '{narr.name}' удалён.")

    def _handle_create_character(self, data):
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        is_player = data.get("is_player", False)
        if not name:
            messagebox.showwarning("Ошибка", "Название персонажа не может быть пустым.")
            return
        char = Character(name=name, description=description, is_player=is_player)
        self.storage.save_object("characters", char)
        self.characters[char.id] = char
        self._refresh_all_ui()
        self._save_current_session_safe()
        messagebox.showinfo("Создано", f"Персонаж '{name}' создан (ID: {char.id}).")

    def _handle_update_character(self, data):
        obj_id = data.get("id")
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        is_player = data.get("is_player", False)
        if not obj_id or obj_id not in self.characters:
            return
        if not name:
            messagebox.showwarning("Ошибка", "Название персонажа не может быть пустым.")
            return
        char = self.characters[obj_id]
        char.name = name
        char.description = description
        char.is_player = is_player
        self.storage.save_object("characters", char)
        self._refresh_all_ui()
        self._save_current_session_safe()
        messagebox.showinfo("Обновлено", f"Персонаж '{name}' обновлён.")

    def _handle_delete_character(self, data):
        obj_id = data.get("id")
        if not obj_id or obj_id not in self.characters:
            return
        char = self.characters[obj_id]
        if messagebox.askyesno("Удаление", f"Удалить персонажа '{char.name}'?"):
            self.storage.delete_object("characters", obj_id)
            del self.characters[obj_id]
            if obj_id in self.current_profile.enabled_characters:
                self.current_profile.enabled_characters.remove(obj_id)
            self._refresh_all_ui()
            self._save_current_session_safe()
            messagebox.showinfo("Удалено", f"Персонаж '{char.name}' удалён.")

    def _handle_create_location(self, data):
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        if not name:
            messagebox.showwarning("Ошибка", "Название локации не может быть пустым.")
            return
        loc = Location(name=name, description=description)
        self.storage.save_object("locations", loc)
        self.locations[loc.id] = loc
        self._refresh_all_ui()
        self._save_current_session_safe()
        messagebox.showinfo("Создано", f"Локация '{name}' создана (ID: {loc.id}).")

    def _handle_update_location(self, data):
        obj_id = data.get("id")
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        if not obj_id or obj_id not in self.locations:
            return
        if not name:
            messagebox.showwarning("Ошибка", "Название локации не может быть пустым.")
            return
        loc = self.locations[obj_id]
        loc.name = name
        loc.description = description
        self.storage.save_object("locations", loc)
        self._refresh_all_ui()
        self._save_current_session_safe()
        messagebox.showinfo("Обновлено", f"Локация '{name}' обновлена.")

    def _handle_delete_location(self, data):
        obj_id = data.get("id")
        if not obj_id or obj_id not in self.locations:
            return
        loc = self.locations[obj_id]
        if messagebox.askyesno("Удаление", f"Удалить локацию '{loc.name}'?"):
            self.storage.delete_object("locations", obj_id)
            del self.locations[obj_id]
            if obj_id in self.current_profile.enabled_locations:
                self.current_profile.enabled_locations.remove(obj_id)
            self._refresh_all_ui()
            self._save_current_session_safe()
            messagebox.showinfo("Удалено", f"Локация '{loc.name}' удалена.")

    def _handle_create_item(self, data):
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        if not name:
            messagebox.showwarning("Ошибка", "Название предмета не может быть пустым.")
            return
        item = Item(name=name, description=description)
        self.storage.save_object("items", item)
        self.items[item.id] = item
        self._refresh_all_ui()
        self._save_current_session_safe()
        messagebox.showinfo("Создано", f"Предмет '{name}' создан (ID: {item.id}).")

    def _handle_update_item(self, data):
        obj_id = data.get("id")
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        if not obj_id or obj_id not in self.items:
            return
        if not name:
            messagebox.showwarning("Ошибка", "Название предмета не может быть пустым.")
            return
        item = self.items[obj_id]
        item.name = name
        item.description = description
        self.storage.save_object("items", item)
        self._refresh_all_ui()
        self._save_current_session_safe()
        messagebox.showinfo("Обновлено", f"Предмет '{name}' обновлён.")

    def _handle_delete_item(self, data):
        obj_id = data.get("id")
        if not obj_id or obj_id not in self.items:
            return
        item = self.items[obj_id]
        if messagebox.askyesno("Удаление", f"Удалить предмет '{item.name}'?"):
            self.storage.delete_object("items", obj_id)
            del self.items[obj_id]
            if obj_id in self.current_profile.enabled_items:
                self.current_profile.enabled_items.remove(obj_id)
            self._refresh_all_ui()
            self._save_current_session_safe()
            messagebox.showinfo("Удалено", f"Предмет '{item.name}' удалён.")

    def _handle_refresh_ui(self, data=None):
        self._refresh_all_ui()
        if self.center_panel:
            self.center_panel.update_translation_button_state()

    def _handle_update_settings(self, data):
        if not data:
            return
        self.settings.update(data)
        self.save_settings()
        self.max_history_messages = self.settings.get("max_history_messages", 10)
        self.use_two_models = self.settings.get("use_two_models", False)
        self.primary_model = self.settings.get("primary_model", "local-model")
        self.translator_model = self.settings.get("translator_model", "local-model")
        self.enable_assistant_translation = self.settings.get("enable_assistant_translation", False)
        self.model_name = self.settings.get("model_name", "local-model")
        self.primary_temperature = self.settings.get("primary_temperature", 0.7)
        self.primary_max_tokens = self.settings.get("primary_max_tokens", 4096)
        self.translator_temperature = self.settings.get("translator_temperature", 0.3)
        self.translator_max_tokens = self.settings.get("translator_max_tokens", 4096)
        self.lm_client.base_url = self.settings.get("api_url", "http://localhost:1234/v1")
        self.lm_client.set_default_params(
            max_tokens=self.settings.get("max_tokens", 4096),
            temperature=self.settings.get("temperature", 0.7)
        )
        if self.center_panel:
            self.center_panel.update_translation_button_state()
        self.enable_memory_summary = self.settings.get("enable_memory_summary", False)
        self.max_memory_summaries = self.settings.get("max_memory_summaries", 5)
        # Если максимальный размер изменился, обрезаем список
        if len(self.memory_summaries) > self.max_memory_summaries:
            self.memory_summaries = self.memory_summaries[-self.max_memory_summaries:]
            self._save_current_session_safe()
        self._log_debug("MEMORY_TRIMMED", f"New max size {self.max_memory_summaries}, summaries: {self.memory_summaries}")
        messagebox.showinfo("Настройки", "Настройки сохранены и применены.")

    def _handle_update_profile(self, data):
        if not data:
            return
        self.current_profile.enabled_narrators = data.get("enabled_narrators", self.current_profile.enabled_narrators)
        self.current_profile.enabled_characters = data.get("enabled_characters", self.current_profile.enabled_characters)
        self.current_profile.enabled_locations = data.get("enabled_locations", self.current_profile.enabled_locations)
        self.current_profile.enabled_items = data.get("enabled_items", self.current_profile.enabled_items)
        self._sync_profile_with_objects()
        self._save_current_session_safe()
        self._refresh_all_ui()
        # Очистить неактивных рассказчиков из конфигурации этапов
        self._cleanup_stage_prompts_narrators()

    def _handle_save_profile(self, data=None):
        name = self.current_profile.name
        if not name or name == "Default":
            new_name = simpledialog.askstring("Сохранить профиль", "Введите имя профиля:", initialvalue=name)
            if not new_name:
                return
            self.current_profile.name = new_name
        self.storage.save_profile(self.current_profile)
        messagebox.showinfo("Профиль", f"Профиль '{self.current_profile.name}' сохранён.")
        self._refresh_all_ui()

    def _handle_load_profile(self, data):
        name = data.get("name")
        if not name:
            return
        profile = self.storage.load_profile(name)
        if not profile:
            messagebox.showerror("Ошибка", f"Профиль '{name}' не найден.")
            return
        self.current_profile = profile
        self._sync_profile_with_objects()
        self._save_current_session_safe()
        self._refresh_all_ui()
        messagebox.showinfo("Профиль", f"Профиль '{name}' загружен.")

    def _handle_new_profile(self, data=None):
        name = simpledialog.askstring("Новый профиль", "Введите имя нового профиля:")
        if not name:
            return
        if self.storage.load_profile(name):
            messagebox.showerror("Ошибка", f"Профиль с именем '{name}' уже существует.")
            return
        new_profile = GameProfile(name=name)
        self.current_profile = new_profile
        self.storage.save_profile(new_profile)
        self._sync_profile_with_objects()
        self._save_current_session_safe()
        self._refresh_all_ui()
        messagebox.showinfo("Профиль", f"Новый профиль '{name}' создан.")

    def _handle_update_prompt(self, data):
        name = data.get("name")
        content = data.get("content", "")
        if not name:
            return
        self.prompt_manager.save_prompt(name, content)
        if self.right_panel:
            self.right_panel.notify_prompt_updated(name)
        messagebox.showinfo("Промт", f"Промт '{name}' сохранён.")

    def _handle_create_prompt(self, data):
        name = data.get("name")
        if not name:
            return
        if self.prompt_manager.create_prompt(name):
            if self.right_panel:
                self.right_panel.notify_prompt_created(name)
            messagebox.showinfo("Промт", f"Промт '{name}' создан.")
        else:
            messagebox.showerror("Ошибка", f"Промт с именем '{name}' уже существует.")

    def _handle_delete_prompt(self, data):
        name = data.get("name")
        if not name:
            return
        if name in self.prompt_manager.default_prompts:
            messagebox.showwarning("Удаление", "Нельзя удалить стандартный промт.")
            return
        if messagebox.askyesno("Удаление", f"Удалить промт '{name}'?"):
            self.prompt_manager.delete_prompt(name)
            if self.right_panel:
                self.right_panel.notify_prompt_deleted(name)
            messagebox.showinfo("Промт", f"Промт '{name}' удалён.")

    def _handle_set_local_description(self, data):
        obj_id = data.get("obj_id")
        description = data.get("description", "").strip()
        if not obj_id:
            return
        if description:
            self.local_descriptions[obj_id] = description
        else:
            self.local_descriptions.pop(obj_id, None)
        self._save_current_session_safe()
        if self.right_panel:
            self.right_panel.refresh()
        messagebox.showinfo("Локальное описание", f"Локальное описание для {obj_id} сохранено.")

    def _handle_clear_local_description(self, data):
        obj_id = data.get("obj_id")
        if not obj_id:
            return
        if obj_id in self.local_descriptions:
            del self.local_descriptions[obj_id]
            self._save_current_session_safe()
            if self.right_panel:
                self.right_panel.refresh()
            messagebox.showinfo("Локальное описание", f"Локальное описание для {obj_id} удалено.")

    def _refresh_all_ui(self):
        if self.right_panel:
            self.right_panel.refresh()
        if self.left_panel:
            self.left_panel.refresh_session_list()

    def _get_object_by_id(self, obj_id: str) -> Optional[BaseObject]:
        if obj_id.startswith('c'):
            return self.characters.get(obj_id)
        if obj_id.startswith('l'):
            return self.locations.get(obj_id)
        if obj_id.startswith('i'):
            return self.items.get(obj_id)
        if obj_id.startswith('n'):
            return self.narrators.get(obj_id)
        return None

    def _build_ui(self):
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True)
        self.left_panel = LeftPanel(main_pane, self)
        main_pane.add(self.left_panel, weight=1)
        self.center_panel = CenterPanel(main_pane, self)
        main_pane.add(self.center_panel, weight=4)
        self.right_panel = RightPanel(main_pane, self)
        main_pane.add(self.right_panel, weight=3)
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="Новая сессия", command=lambda: self.update("new_session"))
        file_menu.add_command(label="Сохранить сессию", command=lambda: self.update("save_current_session"))
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self._on_closing)
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Настройки", menu=settings_menu)
        settings_menu.add_command(label="Параметры API", command=self._open_settings_dialog)

    def _open_settings_dialog(self):
        dialog = SettingsDialog(self, self.settings)
        self.wait_window(dialog.top)
        if dialog.result:
            self.update("update_settings", dialog.result)

    # ---------- Перевод (оставлен без изменений) ----------
    def _translate_response_stream(self, original_content: str, response_start_index: str = None):
        system_prompt = self.prompt_manager.load_prompt("translator_system")
        user_prompt = f"Translate to Russian:\n\n{original_content}"
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        
        # Формируем читаемый текст промта перевода
        full_prompt_lines = []
        full_prompt_lines.append(f"=== ПЕРЕВОД (модель: {self.translator_model}) ===")
        full_prompt_lines.append(f"Температура: {self.translator_temperature}, Max tokens: {self.translator_max_tokens}\n")
        for msg in messages:
            role = msg["role"].upper()
            content = msg["content"]
            full_prompt_lines.append(f"{role}:\n{content}\n")
        full_prompt = "\n".join(full_prompt_lines)
        self.center_panel.log_system_prompt(full_prompt)
        self._log_debug("TRANSLATE_REQUEST", full_prompt)

        self.center_panel.log_system_prompt(f"=== ПРОМТ ПЕРЕВОДА ===\n{system_prompt}\n{user_prompt}")
        self.after(0, lambda: self.center_panel.display_system_message("🌐 Перевод ответа...\n"))
        if response_start_index is None:
            self.after(0, lambda: self.center_panel.start_translation_response())
            response_start_index = self.center_panel.get_current_response_start()
        self.after(0, lambda: self.center_panel.start_translation_stream(response_start_index))
        temp = self.settings.get("translator_temperature", 0.3)
        max_tok = self.settings.get("translator_max_tokens", 4096)
        model = self.settings.get("translator_model", "local-model")

        def translate_stream():
            full_translation = ""
            reasoning_buffer = ""
            try:
                for chunk in self.lm_client.chat_completion_stream(messages=messages, model=model, temperature=temp, max_tokens=max_tok, tools=[]):
                    if self.stop_generation_flag:
                        break
                    if chunk["type"] == "reasoning":
                        reasoning_buffer += chunk["text"]
                        self.after(0, lambda text=chunk["text"]: self.center_panel.append_thinking(text))
                    elif chunk["type"] == "content":
                        if reasoning_buffer:
                            reasoning_buffer = ""
                        full_translation += chunk["text"]
                        self.after(0, lambda text=chunk["text"]: self.center_panel.append_translation_stream(text))
                    elif chunk["type"] == "error":
                        self.after(0, lambda msg=chunk["message"]: self.center_panel.display_message(f"\n[Translation error: {msg}]\n", "error"))
                        return
                if full_translation:
                    self.after(0, lambda: self.center_panel.finalize_translation(full_translation, response_start_index))
                    self.after(0, lambda: self.conversation_history.append({"role": "assistant", "content": full_translation}))
                    self.after(0, lambda: self._save_current_session_safe())
                    self.after(0, lambda: setattr(self, 'last_translated_response', full_translation))
                    self.after(0, lambda: self.center_panel.update_translation_button_state())
                else:
                    self.after(0, lambda: self.center_panel.display_message("\n[Translation failed]\n", "error"))
            except Exception as e:
                self.after(0, lambda: self.center_panel.display_message(f"\n[Translation error: {e}]\n", "error"))
        threading.Thread(target=translate_stream, daemon=True).start()



    # ---------- Object CRUD handlers ----------
    def _handle_update_narrator(self, data):
        obj_id = data.get("id")
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        if not name:
            messagebox.showwarning("Ошибка", "Название рассказчика не может быть пустым.")
            return
        if obj_id and obj_id in self.narrators:
            narr = self.narrators[obj_id]
            narr.name = name
            narr.description = description
            self.storage.save_object("narrators", narr)
            messagebox.showinfo("Обновлено", f"Рассказчик '{name}' обновлён.")
        else:
            narr = Narrator(name=name, description=description)
            self.storage.save_object("narrators", narr)
            self.narrators[narr.id] = narr
            messagebox.showinfo("Создано", f"Рассказчик '{name}' создан (ID: {narr.id}).")
        self._refresh_all_ui()
        self._save_current_session_safe()

    def _handle_delete_narrator(self, data):
        obj_id = data.get("id")
        if not obj_id or obj_id not in self.narrators:
            return
        narr = self.narrators[obj_id]
        if messagebox.askyesno("Удаление", f"Удалить рассказчика '{narr.name}'?"):
            self.storage.delete_object("narrators", obj_id)
            del self.narrators[obj_id]
            if obj_id in self.current_profile.enabled_narrators:
                self.current_profile.enabled_narrators.remove(obj_id)
            self._refresh_all_ui()
            self._save_current_session_safe()
            # Очистить удалённого рассказчика из конфигурации этапов
            self._cleanup_stage_prompts_narrators()
            messagebox.showinfo("Удалено", f"Рассказчик '{narr.name}' удалён.")

    def _handle_create_character(self, data):
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        is_player = data.get("is_player", False)
        if not name:
            messagebox.showwarning("Ошибка", "Название персонажа не может быть пустым.")
            return
        char = Character(name=name, description=description, is_player=is_player)
        self.storage.save_object("characters", char)
        self.characters[char.id] = char
        self._refresh_all_ui()
        self._save_current_session_safe()
        messagebox.showinfo("Создано", f"Персонаж '{name}' создан (ID: {char.id}).")

    def _handle_update_character(self, data):
        obj_id = data.get("id")
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        is_player = data.get("is_player", False)
        if not obj_id or obj_id not in self.characters:
            return
        if not name:
            messagebox.showwarning("Ошибка", "Название персонажа не может быть пустым.")
            return
        char = self.characters[obj_id]
        char.name = name
        char.description = description
        char.is_player = is_player
        self.storage.save_object("characters", char)
        self._refresh_all_ui()
        self._save_current_session_safe()
        messagebox.showinfo("Обновлено", f"Персонаж '{name}' обновлён.")

    def _handle_delete_character(self, data):
        obj_id = data.get("id")
        if not obj_id or obj_id not in self.characters:
            return
        char = self.characters[obj_id]
        if messagebox.askyesno("Удаление", f"Удалить персонажа '{char.name}'?"):
            self.storage.delete_object("characters", obj_id)
            del self.characters[obj_id]
            if obj_id in self.current_profile.enabled_characters:
                self.current_profile.enabled_characters.remove(obj_id)
            self._refresh_all_ui()
            self._save_current_session_safe()
            messagebox.showinfo("Удалено", f"Персонаж '{char.name}' удалён.")

    def _handle_create_location(self, data):
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        if not name:
            messagebox.showwarning("Ошибка", "Название локации не может быть пустым.")
            return
        loc = Location(name=name, description=description)
        self.storage.save_object("locations", loc)
        self.locations[loc.id] = loc
        self._refresh_all_ui()
        self._save_current_session_safe()
        messagebox.showinfo("Создано", f"Локация '{name}' создана (ID: {loc.id}).")

    def _handle_update_location(self, data):
        obj_id = data.get("id")
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        if not obj_id or obj_id not in self.locations:
            return
        if not name:
            messagebox.showwarning("Ошибка", "Название локации не может быть пустым.")
            return
        loc = self.locations[obj_id]
        loc.name = name
        loc.description = description
        self.storage.save_object("locations", loc)
        self._refresh_all_ui()
        self._save_current_session_safe()
        messagebox.showinfo("Обновлено", f"Локация '{name}' обновлена.")

    def _handle_delete_location(self, data):
        obj_id = data.get("id")
        if not obj_id or obj_id not in self.locations:
            return
        loc = self.locations[obj_id]
        if messagebox.askyesno("Удаление", f"Удалить локацию '{loc.name}'?"):
            self.storage.delete_object("locations", obj_id)
            del self.locations[obj_id]
            if obj_id in self.current_profile.enabled_locations:
                self.current_profile.enabled_locations.remove(obj_id)
            self._refresh_all_ui()
            self._save_current_session_safe()
            messagebox.showinfo("Удалено", f"Локация '{loc.name}' удалена.")

    def _handle_create_item(self, data):
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        if not name:
            messagebox.showwarning("Ошибка", "Название предмета не может быть пустым.")
            return
        item = Item(name=name, description=description)
        self.storage.save_object("items", item)
        self.items[item.id] = item
        self._refresh_all_ui()
        self._save_current_session_safe()
        messagebox.showinfo("Создано", f"Предмет '{name}' создан (ID: {item.id}).")

    def _handle_update_item(self, data):
        obj_id = data.get("id")
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        if not obj_id or obj_id not in self.items:
            return
        if not name:
            messagebox.showwarning("Ошибка", "Название предмета не может быть пустым.")
            return
        item = self.items[obj_id]
        item.name = name
        item.description = description
        self.storage.save_object("items", item)
        self._refresh_all_ui()
        self._save_current_session_safe()
        messagebox.showinfo("Обновлено", f"Предмет '{name}' обновлён.")

    def _handle_delete_item(self, data):
        obj_id = data.get("id")
        if not obj_id or obj_id not in self.items:
            return
        item = self.items[obj_id]
        if messagebox.askyesno("Удаление", f"Удалить предмет '{item.name}'?"):
            self.storage.delete_object("items", obj_id)
            del self.items[obj_id]
            if obj_id in self.current_profile.enabled_items:
                self.current_profile.enabled_items.remove(obj_id)
            self._refresh_all_ui()
            self._save_current_session_safe()
            messagebox.showinfo("Удалено", f"Предмет '{item.name}' удалён.")

    def _handle_refresh_ui(self, data=None):
        self._refresh_all_ui()
        if self.center_panel:
            self.center_panel.update_translation_button_state()

    def _handle_update_settings(self, data):
        if not data:
            return
        self.settings.update(data)
        self.save_settings()
        self.max_history_messages = self.settings.get("max_history_messages", 10)
        self.use_two_models = self.settings.get("use_two_models", False)
        self.primary_model = self.settings.get("primary_model", "local-model")
        self.translator_model = self.settings.get("translator_model", "local-model")
        self.enable_assistant_translation = self.settings.get("enable_assistant_translation", False)
        self.model_name = self.settings.get("model_name", "local-model")
        self.primary_temperature = self.settings.get("primary_temperature", 0.7)
        self.primary_max_tokens = self.settings.get("primary_max_tokens", 4096)
        self.translator_temperature = self.settings.get("translator_temperature", 0.3)
        self.translator_max_tokens = self.settings.get("translator_max_tokens", 4096)
        self.lm_client.base_url = self.settings.get("api_url", "http://localhost:1234/v1")
        self.lm_client.set_default_params(
            max_tokens=self.settings.get("max_tokens", 4096),
            temperature=self.settings.get("temperature", 0.7)
        )
        if self.center_panel:
            self.center_panel.update_translation_button_state()
        messagebox.showinfo("Настройки", "Настройки сохранены и применены.")

    def _handle_update_profile(self, data):
        if not data:
            return
        self.current_profile.enabled_narrators = data.get("enabled_narrators", self.current_profile.enabled_narrators)
        self.current_profile.enabled_characters = data.get("enabled_characters", self.current_profile.enabled_characters)
        self.current_profile.enabled_locations = data.get("enabled_locations", self.current_profile.enabled_locations)
        self.current_profile.enabled_items = data.get("enabled_items", self.current_profile.enabled_items)
        self._sync_profile_with_objects()
        self._save_current_session_safe()
        self._refresh_all_ui()

    def _handle_save_profile(self, data=None):
        name = self.current_profile.name
        if not name or name == "Default":
            new_name = simpledialog.askstring("Сохранить профиль", "Введите имя профиля:", initialvalue=name)
            if not new_name:
                return
            self.current_profile.name = new_name
        self.storage.save_profile(self.current_profile)
        messagebox.showinfo("Профиль", f"Профиль '{self.current_profile.name}' сохранён.")
        self._refresh_all_ui()

    def _handle_load_profile(self, data):
        name = data.get("name")
        if not name:
            return
        profile = self.storage.load_profile(name)
        if not profile:
            messagebox.showerror("Ошибка", f"Профиль '{name}' не найден.")
            return
        self.current_profile = profile
        self._sync_profile_with_objects()
        self._save_current_session_safe()
        self._refresh_all_ui()
        self._cleanup_stage_prompts_narrators()   # добавить
        messagebox.showinfo("Профиль", f"Профиль '{name}' загружен.")

    def _handle_new_profile(self, data=None):
        name = simpledialog.askstring("Новый профиль", "Введите имя нового профиля:")
        if not name:
            return
        if self.storage.load_profile(name):
            messagebox.showerror("Ошибка", f"Профиль с именем '{name}' уже существует.")
            return
        new_profile = GameProfile(name=name)
        self.current_profile = new_profile
        self.storage.save_profile(new_profile)
        self._sync_profile_with_objects()
        self._save_current_session_safe()
        self._refresh_all_ui()
        self._cleanup_stage_prompts_narrators()   # добавить
        messagebox.showinfo("Профиль", f"Новый профиль '{name}' создан.")

    def _handle_update_prompt(self, data):
        name = data.get("name")
        content = data.get("content", "")
        if not name:
            return
        self.prompt_manager.save_prompt(name, content)
        if self.right_panel:
            self.right_panel.notify_prompt_updated(name)
        messagebox.showinfo("Промт", f"Промт '{name}' сохранён.")

    def _handle_create_prompt(self, data):
        name = data.get("name")
        if not name:
            return
        if self.prompt_manager.create_prompt(name):
            if self.right_panel:
                self.right_panel.notify_prompt_created(name)
            messagebox.showinfo("Промт", f"Промт '{name}' создан.")
        else:
            messagebox.showerror("Ошибка", f"Промт с именем '{name}' уже существует.")

    def _handle_delete_prompt(self, data):
        name = data.get("name")
        if not name:
            return
        if name in self.prompt_manager.default_prompts:
            messagebox.showwarning("Удаление", "Нельзя удалить стандартный промт.")
            return
        if messagebox.askyesno("Удаление", f"Удалить промт '{name}'?"):
            self.prompt_manager.delete_prompt(name)
            if self.right_panel:
                self.right_panel.notify_prompt_deleted(name)
            messagebox.showinfo("Промт", f"Промт '{name}' удалён.")

    def _handle_set_local_description(self, data):
        obj_id = data.get("obj_id")
        description = data.get("description", "").strip()
        if not obj_id:
            return
        if description:
            self.local_descriptions[obj_id] = description
        else:
            self.local_descriptions.pop(obj_id, None)
        self._save_current_session_safe()
        if self.right_panel:
            self.right_panel.refresh()
        messagebox.showinfo("Локальное описание", f"Локальное описание для {obj_id} сохранено.")

    def _handle_clear_local_description(self, data):
        obj_id = data.get("obj_id")
        if not obj_id:
            return
        if obj_id in self.local_descriptions:
            del self.local_descriptions[obj_id]
            self._save_current_session_safe()
            if self.right_panel:
                self.right_panel.refresh()
            messagebox.showinfo("Локальное описание", f"Локальное описание для {obj_id} удалено.")

    def _refresh_all_ui(self):
        if self.right_panel:
            self.right_panel.refresh()
        if self.left_panel:
            self.left_panel.refresh_session_list()

    def _get_object_by_id(self, obj_id: str) -> Optional[BaseObject]:
        if obj_id.startswith('c'):
            return self.characters.get(obj_id)
        if obj_id.startswith('l'):
            return self.locations.get(obj_id)
        if obj_id.startswith('i'):
            return self.items.get(obj_id)
        if obj_id.startswith('n'):
            return self.narrators.get(obj_id)
        return None

    def _build_ui(self):
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True)
        self.left_panel = LeftPanel(main_pane, self)
        main_pane.add(self.left_panel, weight=1)
        self.center_panel = CenterPanel(main_pane, self)
        main_pane.add(self.center_panel, weight=4)
        self.right_panel = RightPanel(main_pane, self)
        main_pane.add(self.right_panel, weight=3)
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="Новая сессия", command=lambda: self.update("new_session"))
        file_menu.add_command(label="Сохранить сессию", command=lambda: self.update("save_current_session"))
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self._on_closing)
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Настройки", menu=settings_menu)
        settings_menu.add_command(label="Параметры API", command=self._open_settings_dialog)

    def _open_settings_dialog(self):
        dialog = SettingsDialog(self, self.settings)
        self.wait_window(dialog.top)
        if dialog.result:
            self.update("update_settings", dialog.result)

# ---------- Left Panel ----------
class LeftPanel(ttk.Frame):
    def __init__(self, parent, app: MainApp):
        super().__init__(parent)
        self.app = app
        self._build_ui()

    def _build_ui(self):
        ttk.Label(self, text="Игровые сессии").pack(pady=5)
        list_frame = ttk.Frame(self)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self.listbox = tk.Listbox(list_frame, font=("Arial", 10))
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self.listbox.bind("<Button-3>", self._show_context_menu)
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Новая сессия", command=lambda: self.app.update("new_session")).pack(side=tk.LEFT, padx=5)
        self._context_menu = tk.Menu(self.listbox, tearoff=0)
        self._context_menu.add_command(label="Переименовать", command=self._rename_selected)
        self._context_menu.add_command(label="Удалить", command=self._delete_selected)

    def refresh_session_list(self):
        self.listbox.delete(0, tk.END)
        sessions = self.app.storage.list_sessions()
        self.session_ids = sessions
        for sid in sessions:
            name = self.get_session_name(sid)  # теперь безопасно
            if sid == self.app.current_session_id:
                name = f"▶ {name}"
            self.listbox.insert(tk.END, name)

    def get_session_name(self, session_id: str) -> str:
        data = self.app.storage.load_session(session_id)
        if data is None:
            return "⚠️ Повреждена"
        return data.get("name", "Без имени")

    def _on_select(self, event):
        if self.app.is_generating:
            messagebox.showwarning("Генерация", "Сначала остановите генерацию (кнопка Стоп).")
            return
        selection = self.listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx < len(self.session_ids):
            sid = self.session_ids[idx]
            if sid != self.app.current_session_id:
                self.app.update("load_session", {"session_id": sid})

    def _show_context_menu(self, event):
        idx = self.listbox.nearest(event.y)
        if idx == -1:
            return
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(idx)
        self.listbox.activate(idx)
        self._context_menu.post(event.x_root, event.y_root)

    def _rename_selected(self):
        selection = self.listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        sid = self.session_ids[idx]
        current_name = self.get_session_name(sid)
        new_name = simpledialog.askstring("Переименовать", "Новое название:", initialvalue=current_name)
        if new_name and new_name != current_name:
            self.app.update("rename_session", {"session_id": sid, "new_name": new_name})

    def _delete_selected(self):
        selection = self.listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        sid = self.session_ids[idx]
        self.app.update("delete_session", {"session_id": sid})

# ---------- Center Panel ----------
class CenterPanel(ttk.Frame):
    def __init__(self, parent, app: MainApp):
        super().__init__(parent)
        self.app = app
        self.thinking_visible = tk.BooleanVar(value=True)
        self.system_info_visible = tk.BooleanVar(value=False)
        self.last_full_prompt = ""
        self._sending = False
        self.stage_names = app.stage_names 
        self.prompts_by_stage = {}          
        self.current_selected_stage = None
        
        self._build_ui()
        self._configure_tags()
        self._configure_tags_for_info()

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=0, minsize=0)
        self.grid_rowconfigure(1, weight=0, minsize=0)
        self.grid_rowconfigure(2, weight=1, minsize=50)
        self.grid_rowconfigure(3, weight=0, minsize=80)
        self.grid_columnconfigure(0, weight=1)

        self.info_frame = ttk.LabelFrame(self, text="Информация о промте")
        self.info_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 0))
        info_header = ttk.Frame(self.info_frame)
        info_header.pack(fill=tk.X, padx=2, pady=2)
        self.stage_combo = ttk.Combobox(info_header, state="readonly", width=20)
        self.stage_combo.pack(side=tk.LEFT, padx=(10, 5))
        self.stage_combo.bind("<<ComboboxSelected>>", self._on_stage_select)
        self.toggle_info_btn = ttk.Button(info_header, text="Свернуть", command=self._toggle_system_info)
        self.toggle_info_btn.pack(side=tk.LEFT)
        self.open_window_btn = ttk.Button(info_header, text="Открыть в окне", command=self._open_prompt_window)
        self.open_window_btn.pack(side=tk.LEFT, padx=5)
        ttk.Label(info_header, text=" (полный текст отправленного промта)").pack(side=tk.LEFT)
        self.info_text = scrolledtext.ScrolledText(self.info_frame, wrap=tk.WORD, font=("Arial", 9), height=4, state=tk.DISABLED)
        self.info_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        add_context_menu(self.info_text)

        self.thinking_frame = ttk.LabelFrame(self, text="Thinking (рассуждения)")
        self.thinking_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=(5, 0))
        think_header = ttk.Frame(self.thinking_frame)
        think_header.pack(fill=tk.X, padx=2, pady=2)
        self.toggle_think_btn = ttk.Button(think_header, text="Свернуть", command=self._toggle_thinking)
        self.toggle_think_btn.pack(side=tk.LEFT)
        self.thinking_text = scrolledtext.ScrolledText(self.thinking_frame, wrap=tk.WORD, font=("Arial", 10), height=6, state=tk.DISABLED)
        self.thinking_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        add_context_menu(self.thinking_text)

        self.chat_frame = ttk.Frame(self)
        self.chat_frame.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        self.chat_frame.grid_rowconfigure(1, weight=1)
        self.chat_frame.grid_columnconfigure(0, weight=1)

        token_status_frame = ttk.Frame(self.chat_frame)
        token_status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        ttk.Label(token_status_frame, text="Токенов системного промта:").pack(side=tk.LEFT)
        self.token_count_var = tk.StringVar(value="0")
        token_label = ttk.Label(token_status_frame, textvariable=self.token_count_var, font=("Arial", 10, "bold"))
        token_label.pack(side=tk.LEFT, padx=(5,0))
        ttk.Label(token_status_frame, text=" | Полный контекст:").pack(side=tk.LEFT, padx=(10,0))
        self.total_token_var = tk.StringVar(value="0")
        total_token_label = ttk.Label(token_status_frame, textvariable=self.total_token_var, font=("Arial", 10, "bold"))
        total_token_label.pack(side=tk.LEFT, padx=(5,0))

        self.chat_display = scrolledtext.ScrolledText(self.chat_frame, wrap=tk.WORD, font=("Arial", 11), state=tk.DISABLED)
        self.chat_display.grid(row=1, column=0, sticky="nsew")
        add_context_menu(self.chat_display)

        self.input_container = ttk.Frame(self)
        self.input_container.grid(row=3, column=0, sticky="ew", padx=5, pady=5)
        self.input_text = tk.Text(self.input_container, height=3, font=("Arial", 11))
        self.input_text.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        add_context_menu(self.input_text)

        btn_frame_top = ttk.Frame(self.input_container)
        btn_frame_top.pack(fill=tk.X, pady=2)
        btn_frame_bottom = ttk.Frame(self.input_container)
        btn_frame_bottom.pack(fill=tk.X, pady=2)

        self.send_btn = ttk.Button(btn_frame_top, text="Отправить", command=self._send_message)
        self.send_btn.pack(side=tk.LEFT, padx=2)
        self.stop_btn = ttk.Button(btn_frame_top, text="Стоп", command=lambda: self.app.update("stop_generation"))
        self.stop_btn.pack(side=tk.LEFT, padx=2)
        self.start_btn = ttk.Button(btn_frame_top, text="Начать игру", command=lambda: self.app.update("start_game"))
        self.start_btn.pack(side=tk.LEFT, padx=2)
        self.clear_btn = ttk.Button(btn_frame_top, text="Очистить", command=lambda: self.app.update("clear_chat"))
        self.clear_btn.pack(side=tk.LEFT, padx=2)

        self.regenerate_btn = ttk.Button(btn_frame_bottom, text="Перегенерировать", command=self._regenerate_last)
        self.regenerate_btn.pack(side=tk.LEFT, padx=2)
        self.regenerate_translation_btn = ttk.Button(btn_frame_bottom, text="Перегенерировать перевод", command=self._regenerate_translation)
        self.regenerate_translation_btn.pack(side=tk.LEFT, padx=2)
        self.delete_last_btn = ttk.Button(btn_frame_bottom, text="Удалить последнее", command=self._delete_last_user_message)
        self.delete_last_btn.pack(side=tk.LEFT, padx=2)

        self.input_text.bind("<Control-Return>", lambda e: self._send_message())

        self.temp_response_start = None

    def update_token_count(self, token_str: str, total_str: str = None):
        self.token_count_var.set(token_str)
        if total_str is not None:
            self.total_token_var.set(total_str)

    def update_total_tokens(self, total_str: str):
        self.total_token_var.set(total_str)

    def _configure_tags(self):
        self.chat_display.tag_config("user", foreground="blue")
        self.chat_display.tag_config("assistant", foreground="green")
        self.chat_display.tag_config("system", foreground="gray", font=("Arial", 10, "italic"))
        self.chat_display.tag_config("error", foreground="red")
        self.thinking_text.tag_config("thinking", foreground="purple", font=("Arial", 10, "italic"))
        self.chat_display.tag_config("component_header", foreground="darkorange", font=("Arial", 10, "bold"))
        self.chat_display.tag_config("component_item", foreground="navy")
        self.chat_display.tag_config("translation", foreground="darkgreen", font=("Arial", 11, "italic"))
        self.chat_display.tag_config("temp", foreground="orange", font=("Arial", 10, "italic"))

    def _toggle_thinking(self):
        if self.thinking_visible.get():
            self.thinking_text.pack_forget()
            self.toggle_think_btn.config(text="Развернуть")
            self.thinking_visible.set(False)
            self.grid_rowconfigure(1, minsize=0, weight=0)
        else:
            self.thinking_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            self.toggle_think_btn.config(text="Свернуть")
            self.thinking_visible.set(True)
            self.grid_rowconfigure(1, minsize=100, weight=0)
        self.update_idletasks()

    def _toggle_system_info(self):
        if self.system_info_visible.get():
            self.info_text.pack_forget()
            self.toggle_info_btn.config(text="Развернуть")
            self.system_info_visible.set(False)
            self.grid_rowconfigure(0, minsize=0, weight=0)
        else:
            self.info_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            self.toggle_info_btn.config(text="Свернуть")
            self.system_info_visible.set(True)
            self.grid_rowconfigure(0, minsize=120, weight=0)
        self.update_idletasks()

    def _open_prompt_window(self):
        if not self.last_full_prompt:
            messagebox.showinfo("Нет данных", "Промт ещё не был отправлен.")
            return
        win = tk.Toplevel(self)
        win.title("Полный текст промта")
        win.geometry("800x600")
        text_area = scrolledtext.ScrolledText(win, wrap=tk.WORD, font=("Courier", 10))
        text_area.pack(fill=tk.BOTH, expand=True)
        text_area.insert(tk.END, self.last_full_prompt)
        text_area.config(state=tk.DISABLED)
        add_context_menu(text_area)

    def log_system_prompt(self, prompt: str, stage_name: str = None):
        """
        Отображает полный промт, отправленный модели, с цветовым выделением ролей.
        Если stage_name указан, промт сохраняется в словарь prompts_by_stage.
        """
        # Сохраняем промт по этапу
        if stage_name:
            self.prompts_by_stage[stage_name] = prompt
            # Обновляем список этапов в комбобоксе
            self._update_stage_combobox()
            # Если текущий выбранный этап совпадает с сохранённым, обновляем отображение
            if self.current_selected_stage == stage_name:
                self._display_prompt(prompt)
        else:
            # Если этап не указан (например, перевод), сохраняем как "other"
            self.prompts_by_stage["other"] = prompt
            if self.current_selected_stage == "other":
                self._display_prompt(prompt)

    def _update_stage_combobox(self):
        """Обновляет список этапов в комбобоксе на основе сохранённых промтов."""
        stages = list(self.prompts_by_stage.keys())
        if not stages:
            return
        # Добавляем "other", если его ещё нет
        if "other" not in stages and "other" in self.prompts_by_stage:
            stages.append("other")
        self.stage_combo['values'] = stages
        if self.current_selected_stage not in stages:
            self.current_selected_stage = stages[0] if stages else None
            if self.current_selected_stage:
                self.stage_combo.set(self.current_selected_stage)
                self._display_prompt(self.prompts_by_stage[self.current_selected_stage])

    def _display_prompt(self, prompt: str):
        """Отображает промт в info_text с форматированием."""
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        
        lines = prompt.split('\n')
        for line in lines:
            if line.startswith("==="):
                self.info_text.insert(tk.END, line + "\n", "header")
            elif line.startswith("[") and "]" in line and ":" in line:
                role_part = line.split("]", 1)[1].strip().split(":", 1)[0].lower()
                if role_part == "system":
                    tag = "system_role"
                elif role_part == "user":
                    tag = "user_role"
                elif role_part == "assistant":
                    tag = "assistant_role"
                else:
                    tag = "default"
                self.info_text.insert(tk.END, line + "\n", tag)
            else:
                self.info_text.insert(tk.END, line + "\n", "content")
        self.info_text.config(state=tk.DISABLED)
        self.last_full_prompt = prompt
        self.info_text.see("1.0")

    def _on_stage_select(self, event=None):
        """Обработчик выбора этапа из комбобокса."""
        selected = self.stage_combo.get()
        if selected and selected in self.prompts_by_stage:
            self.current_selected_stage = selected
            self._display_prompt(self.prompts_by_stage[selected])
                                 
    def _configure_tags_for_info(self):
        """Добавить теги для панели информации (вызывается при инициализации)"""
        self.info_text.tag_config("header", foreground="darkblue", font=("Arial", 10, "bold"))
        self.info_text.tag_config("system_role", foreground="green", font=("Arial", 9, "bold"))
        self.info_text.tag_config("user_role", foreground="blue", font=("Arial", 9, "bold"))
        self.info_text.tag_config("assistant_role", foreground="purple", font=("Arial", 9, "bold"))
        self.info_text.tag_config("content", foreground="black", font=("Arial", 9))

    def display_components(self, components: List[Dict]):
        self.display_message("\n📦 **Состав отправленного промта:**\n", "system")
        for comp in components:
            comp_type = comp.get("type", "")
            name = comp.get("name", "")
            items = comp.get("items", [])
            header = f"  • {comp_type}"
            if name:
                header += f" — {name}"
            self.display_message(header + "\n", "component_header")
            for item in items:
                self.display_message(f"      - {item}\n", "component_item")
        self.display_message("\n", "system")

    def set_input_state(self, state):
        self.input_text.config(state=state)
        if state == tk.NORMAL:
            self.send_btn.config(state=tk.NORMAL)
            self.regenerate_btn.config(state=tk.NORMAL)
            self.delete_last_btn.config(state=tk.NORMAL)
            self._sending = False
        else:
            self.send_btn.config(state=tk.DISABLED)
            self.regenerate_btn.config(state=tk.DISABLED)
            self.delete_last_btn.config(state=tk.DISABLED)

    def start_new_response(self, clear_thinking=True):
        if clear_thinking:
            self.thinking_text.config(state=tk.NORMAL)
            self.thinking_text.delete(1.0, tk.END)
            self.thinking_text.config(state=tk.DISABLED)
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, "Ассистент: ", "assistant")
        self.current_response_start = self.chat_display.index(tk.INSERT)
        self.chat_display.config(state=tk.DISABLED)

    def get_current_response_start(self):
        return getattr(self, 'current_response_start', None)

    def start_translation_response(self):
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, "Ассистент (перевод): ", "assistant")
        self.current_response_start = self.chat_display.index(tk.INSERT)
        self.chat_display.config(state=tk.DISABLED)

    def start_translation_stream(self, response_start):
        self.translation_start_pos = response_start
        self.chat_display.config(state=tk.NORMAL)
        end_pos = self.chat_display.index(tk.END)
        self.chat_display.delete(response_start, end_pos)
        self.chat_display.insert(tk.END, "Ассистент (перевод): ", "assistant")
        self.current_translation_start = self.chat_display.index(tk.INSERT)
        self.chat_display.config(state=tk.DISABLED)

    def append_translation_stream(self, text: str):
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, text, "translation")
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)
        self.update_idletasks()

    def finalize_translation(self, full_translation: str, response_start):
        self.chat_display.config(state=tk.NORMAL)
        if hasattr(self, 'current_translation_start'):
            self.chat_display.delete(self.current_translation_start, tk.END)
            self.chat_display.insert(self.current_translation_start, full_translation, "translation")
        self.chat_display.insert(tk.END, "\n\n")
        self.chat_display.config(state=tk.DISABLED)
        self.update_idletasks()

    def append_thinking(self, text: str):
        self.thinking_text.config(state=tk.NORMAL)
        self.thinking_text.insert(tk.END, text, "thinking")
        self.thinking_text.see(tk.END)
        self.thinking_text.config(state=tk.DISABLED)
        self.update_idletasks()

    def append_response(self, text: str):
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, text)
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)
        self.update_idletasks()

    def remove_last_response(self):
        if hasattr(self, 'current_response_start') and self.current_response_start:
            self.chat_display.config(state=tk.NORMAL)
            end_pos = self.chat_display.index(tk.END)
            self.chat_display.delete(self.current_response_start, end_pos)
            self.chat_display.config(state=tk.DISABLED)

    def finalize_response(self, translation_pending=False):
        if not translation_pending:
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.insert(tk.END, "\n\n")
            self.chat_display.see(tk.END)
            self.chat_display.config(state=tk.DISABLED)
            self.update_idletasks()

    def display_message(self, text: str, tag=None):
        self.chat_display.config(state=tk.NORMAL)
        if tag:
            self.chat_display.insert(tk.END, text, tag)
        else:
            self.chat_display.insert(tk.END, text)
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)
        self.update_idletasks()

    def display_system_message(self, text: str):
        self.display_message(text, "system")

    def clear_chat(self):
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.delete(1.0, tk.END)
        self.chat_display.config(state=tk.DISABLED)
        self.thinking_text.config(state=tk.NORMAL)
        self.thinking_text.delete(1.0, tk.END)
        self.thinking_text.config(state=tk.DISABLED)
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        self.info_text.config(state=tk.DISABLED)
        self.last_full_prompt = ""
        self.prompts_by_stage.clear()
        self.current_selected_stage = None
        self._update_stage_combobox()
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        self.info_text.config(state=tk.DISABLED)
        self.last_full_prompt = ""

    def update_translation_button_state(self):
        if self.app.enable_assistant_translation and self.app.use_two_models and self.app.last_original_response is not None:
            self.regenerate_translation_btn.config(state=tk.NORMAL)
        else:
            self.regenerate_translation_btn.config(state=tk.DISABLED)

    def start_temp_response(self):
        """Начинает временный вывод (стрим) — запоминает позицию до вставки префикса"""
        self.chat_display.config(state=tk.NORMAL)
        # Запоминаем позицию ДО вставки префикса
        self.temp_start_index = self.chat_display.index(tk.INSERT)
        self.chat_display.insert(tk.END, "⚙️ Генерация (временный вывод): ", "temp")
        # Позиция после префикса (для добавления контента)
        self.temp_response_start = self.chat_display.index(tk.INSERT)
        self.chat_display.config(state=tk.DISABLED)
        self.update_idletasks()

    def append_temp_content(self, text: str):
        if self.temp_response_start:
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.insert(tk.END, text, "temp")
            self.chat_display.see(tk.END)
            self.chat_display.config(state=tk.DISABLED)
            self.update_idletasks()

    def clear_temp_response(self):
        """Удаляет весь временный блок (включая префикс)"""
        if hasattr(self, 'temp_start_index') and self.temp_start_index:
            self.chat_display.config(state=tk.NORMAL)
            end_pos = self.chat_display.index(tk.END)
            self.chat_display.delete(self.temp_start_index, end_pos)
            self.chat_display.config(state=tk.DISABLED)
            self.temp_start_index = None
            self.temp_response_start = None
            self.update_idletasks()

    def _send_message(self):
        if self.app.is_generating:
            messagebox.showwarning("Генерация", "Подождите завершения генерации или нажмите 'Стоп'.")
            return
        if self._sending:
            return
        message = self.input_text.get("1.0", tk.END).strip()
        if message:
            self._sending = True
            self.input_text.delete("1.0", tk.END)
            self.display_message(f"Вы: {message}\n", "user")
            self.send_btn.config(state=tk.DISABLED)
            self.app.update("send_message", {"message": message})

    def _regenerate_last(self):
        if self.app.is_generating:
            messagebox.showwarning("Генерация", "Подождите завершения генерации или нажмите 'Стоп'.")
            return
        if not self.app.last_user_message:
            messagebox.showinfo("Перегенерация", "Нет последнего сообщения пользователя.")
            return
        self.app.update("regenerate_last_response")

    def _regenerate_translation(self):
        if self.app.is_generating:
            messagebox.showwarning("Генерация", "Подождите завершения генерации или нажмите 'Стоп'.")
            return
        self.app.update("regenerate_translation")

    def _delete_last_user_message(self):
        if self.app.is_generating:
            messagebox.showwarning("Генерация", "Сначала остановите генерацию (кнопка Стоп).")
            return
        self.app.update("delete_last_user_message")

# ---------- Right Panel and Tabs ----------
class RightPanel(ttk.Frame):
    def __init__(self, parent, app: MainApp):
        super().__init__(parent)
        self.app = app
        self.tab_frames = {}
        self.current_tab = None
        self._build_ui()
        self._create_tabs()
        self.show_tab("profile")
    def _build_ui(self):
        self.button_container = ttk.Frame(self)
        self.button_container.pack(fill=tk.X, padx=5, pady=5)
        row1 = ttk.Frame(self.button_container)
        row1.pack(fill=tk.X, pady=2)
        row2 = ttk.Frame(self.button_container)
        row2.pack(fill=tk.X, pady=2)
        row3 = ttk.Frame(self.button_container)
        row3.pack(fill=tk.X, pady=2)
        buttons = [("profile", "Профиль", row1), ("narrators", "Рассказчики", row1), ("characters", "Персонажи", row1), 
            ("locations", "Локации", row2), ("items", "Предметы", row2), ("prompts", "Системные промты", row2), 
            ("translator_prompts", "Промты перевода", row3), ("stage_prompts", "Этапы", row3)]
        self.tab_buttons = {}
        for tab_name, text, parent_row in buttons:
            btn = ttk.Button(parent_row, text=text, command=lambda n=tab_name: self.show_tab(n))
            btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
            self.tab_buttons[tab_name] = btn
        self.content_frame = ttk.Frame(self)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    def _create_tabs(self):
        self.tab_frames["profile"] = ProfileTab(self.content_frame, self.app)
        self.tab_frames["narrators"] = BaseEditorTab(self.content_frame, self.app, "narrators", Narrator, "Рассказчики")
        self.tab_frames["characters"] = BaseEditorTab(self.content_frame, self.app, "characters", Character, "Персонажи")
        self.tab_frames["locations"] = BaseEditorTab(self.content_frame, self.app, "locations", Location, "Локации")
        self.tab_frames["items"] = BaseEditorTab(self.content_frame, self.app, "items", Item, "Предметы")
        self.tab_frames["prompts"] = SystemPromptsTab(self.content_frame, self.app)
        self.tab_frames["translator_prompts"] = TranslatorPromptsTab(self.content_frame, self.app)
        self.tab_frames["stage_prompts"] = StagePromptsTab(self.content_frame, self.app)
    def show_tab(self, tab_name: str):
        if self.current_tab == tab_name:
            return
        if self.current_tab and self.current_tab in self.tab_frames:
            self.tab_frames[self.current_tab].pack_forget()
        if tab_name in self.tab_frames:
            self.tab_frames[tab_name].pack(fill=tk.BOTH, expand=True)
            self.current_tab = tab_name
            for name, btn in self.tab_buttons.items():
                if name == tab_name:
                    btn.config(state="disabled")
                else:
                    btn.config(state="normal")
            self.tab_frames[tab_name].refresh()
    def refresh(self):
        for frame in self.tab_frames.values():
            if hasattr(frame, "refresh"):
                frame.refresh()
    def notify_object_created(self, obj_type: str, obj_id: str):
        frame = self.tab_frames.get(obj_type)
        if frame and hasattr(frame, "add_object"):
            frame.add_object(obj_id)
    def notify_object_updated(self, obj_type: str, obj_id: str):
        frame = self.tab_frames.get(obj_type)
        if frame and hasattr(frame, "update_object"):
            frame.update_object(obj_id)
    def notify_object_deleted(self, obj_type: str, obj_id: str):
        frame = self.tab_frames.get(obj_type)
        if frame and hasattr(frame, "remove_object"):
            frame.remove_object(obj_id)
    def notify_prompt_created(self, name: str):
        frame1 = self.tab_frames.get("prompts")
        if frame1 and hasattr(frame1, "add_prompt"):
            frame1.add_prompt(name)
        frame2 = self.tab_frames.get("translator_prompts")
        if frame2 and hasattr(frame2, "add_prompt"):
            frame2.add_prompt(name)
    def notify_prompt_updated(self, name: str):
        frame1 = self.tab_frames.get("prompts")
        if frame1 and hasattr(frame1, "update_prompt"):
            frame1.update_prompt(name)
        frame2 = self.tab_frames.get("translator_prompts")
        if frame2 and hasattr(frame2, "update_prompt"):
            frame2.update_prompt(name)
    def notify_prompt_deleted(self, name: str):
        frame1 = self.tab_frames.get("prompts")
        if frame1 and hasattr(frame1, "remove_prompt"):
            frame1.remove_prompt(name)
        frame2 = self.tab_frames.get("translator_prompts")
        if frame2 and hasattr(frame2, "remove_prompt"):
            frame2.remove_prompt(name)

class ProfileTab(ttk.Frame):
    def __init__(self, parent, app: MainApp):
        super().__init__(parent)
        self.app = app
        self._build_ui()
        self.refresh()
    def _build_ui(self):
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        row0 = ttk.Frame(top_frame)
        row0.pack(fill=tk.X, pady=2)
        ttk.Label(row0, text="Профиль:").pack(side=tk.LEFT)
        self.profile_name_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(row0, textvariable=self.profile_name_var, width=20)
        self.profile_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        row1 = ttk.Frame(top_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Button(row1, text="Загрузить", command=self._load_profile).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text="Сохранить", command=self._save_profile).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text="Новый", command=self._new_profile).pack(side=tk.LEFT, padx=2)
        canvas_container = ttk.Frame(self)
        canvas_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.canvas = tk.Canvas(canvas_container, borderwidth=0)
        scrollbar = ttk.Scrollbar(canvas_container, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw", tags=("window",))
        def _on_canvas_configure(event):
            self.canvas.itemconfig(self.canvas_window, width=event.width)
        self.canvas.bind("<Configure>", _on_canvas_configure)
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.canvas.bind("<MouseWheel>", _on_mousewheel)
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill=tk.X, padx=5, pady=5)
        self.apply_btn = ttk.Button(bottom_frame, text="Применить", command=self._apply_changes)
        self.apply_btn.pack(pady=5)
        self.narrator_vars = {}
        self.char_vars = {}
        self.loc_vars = {}
        self.item_vars = {}
    def refresh(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        profile = self.app.current_profile
        profiles = self.app.storage.list_profiles()
        self.profile_combo['values'] = profiles
        self.profile_name_var.set(profile.name)
        if self.app.narrators:
            ttk.Label(self.scrollable_frame, text="Рассказчики", font=('Arial', 10, 'bold')).pack(anchor='w', pady=(5,0))
            self.narrator_vars.clear()
            for nid, narr in self.app.narrators.items():
                var = tk.BooleanVar(value=(nid in profile.enabled_narrators))
                self.narrator_vars[nid] = var
                cb = ttk.Checkbutton(self.scrollable_frame, text=narr.name, variable=var, command=self._on_checkbox_change)
                cb.pack(anchor='w', padx=20)
        if self.app.characters:
            ttk.Label(self.scrollable_frame, text="Персонажи", font=('Arial', 10, 'bold')).pack(anchor='w', pady=(10,0))
            self.char_vars.clear()
            for cid, char in self.app.characters.items():
                var = tk.BooleanVar(value=(cid in profile.enabled_characters))
                self.char_vars[cid] = var
                cb = ttk.Checkbutton(self.scrollable_frame, text=f"{char.name} {'(ИГРОК)' if char.is_player else ''}", variable=var, command=self._on_checkbox_change)
                cb.pack(anchor='w', padx=20)
        if self.app.locations:
            ttk.Label(self.scrollable_frame, text="Локации", font=('Arial', 10, 'bold')).pack(anchor='w', pady=(10,0))
            self.loc_vars.clear()
            for lid, loc in self.app.locations.items():
                var = tk.BooleanVar(value=(lid in profile.enabled_locations))
                self.loc_vars[lid] = var
                cb = ttk.Checkbutton(self.scrollable_frame, text=loc.name, variable=var, command=self._on_checkbox_change)
                cb.pack(anchor='w', padx=20)
        if self.app.items:
            ttk.Label(self.scrollable_frame, text="Предметы", font=('Arial', 10, 'bold')).pack(anchor='w', pady=(10,0))
            self.item_vars.clear()
            for iid, item in self.app.items.items():
                var = tk.BooleanVar(value=(iid in profile.enabled_items))
                self.item_vars[iid] = var
                cb = ttk.Checkbutton(self.scrollable_frame, text=item.name, variable=var, command=self._on_checkbox_change)
                cb.pack(anchor='w', padx=20)
        self.scrollable_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    def _on_checkbox_change(self):
        pass
    def _apply_changes(self):
        profile = self.app.current_profile
        profile.enabled_narrators = [nid for nid, var in self.narrator_vars.items() if var.get()]
        profile.enabled_characters = [cid for cid, var in self.char_vars.items() if var.get()]
        profile.enabled_locations = [lid for lid, var in self.loc_vars.items() if var.get()]
        profile.enabled_items = [iid for iid, var in self.item_vars.items() if var.get()]
        self.app.update("update_profile", {"enabled_narrators": profile.enabled_narrators, "enabled_characters": profile.enabled_characters, "enabled_locations": profile.enabled_locations, "enabled_items": profile.enabled_items})
        messagebox.showinfo("Профиль", "Настройки применены.")
    def _load_profile(self):
        name = self.profile_name_var.get()
        if name:
            self.app.update("load_profile", {"name": name})
    def _save_profile(self):
        self.app.update("save_profile")
    def _new_profile(self):
        self.app.update("new_profile")

class SystemPromptsTab(ttk.Frame):
    def __init__(self, parent, app: MainApp):
        super().__init__(parent)
        self.app = app
        self.current_prompt_name = None
        self._build_ui()
        self.refresh()
    def _build_ui(self):
        top_frame = ttk.LabelFrame(self, text="Список системных промтов")
        top_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.listbox = tk.Listbox(top_frame, height=8)
        scrollbar = ttk.Scrollbar(top_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        btn_frame = ttk.Frame(top_frame)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Создать", command=self._create_new).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить", command=self._delete_selected).pack(side=tk.LEFT, padx=5)
        editor_frame = ttk.LabelFrame(self, text="Редактор промта")
        editor_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.name_label = ttk.Label(editor_frame, text="Название:")
        self.name_label.pack(anchor='w', padx=5, pady=2)
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(editor_frame, textvariable=self.name_var, state='readonly')
        self.name_entry.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(editor_frame, text="Содержимое:").pack(anchor='w', padx=5, pady=2)
        self.text_editor = scrolledtext.ScrolledText(editor_frame, wrap=tk.WORD, height=12)
        self.text_editor.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        add_context_menu(self.text_editor)
        btn_frame2 = ttk.Frame(editor_frame)
        btn_frame2.pack(fill=tk.X, pady=5)
        self.save_btn = ttk.Button(btn_frame2, text="Сохранить", command=self._save_current)
        self.save_btn.pack(side=tk.RIGHT, padx=5)
        self.save_btn.config(state=tk.DISABLED)
    def refresh(self):
        self.listbox.delete(0, tk.END)
        prompts = self.app.prompt_manager.list_prompts()
        for name in sorted(prompts):
            if not name.startswith("translator_"):
                self.listbox.insert(tk.END, name)
        self._clear_editor()
    def add_prompt(self, name: str):
        if name.startswith("translator_"):
            return
        self.refresh()
        for i in range(self.listbox.size()):
            if self.listbox.get(i) == name:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(i)
                self.listbox.see(i)
                self._on_select(None)
                break
    def update_prompt(self, name: str):
        if name.startswith("translator_"):
            return
        if self.current_prompt_name == name:
            content = self.app.prompt_manager.get_prompt_content(name)
            self.text_editor.delete(1.0, tk.END)
            self.text_editor.insert(1.0, content)
    def remove_prompt(self, name: str):
        if name.startswith("translator_"):
            return
        self.refresh()
        if self.current_prompt_name == name:
            self._clear_editor()
    def _on_select(self, event):
        selection = self.listbox.curselection()
        if not selection:
            return
        name = self.listbox.get(selection[0])
        self.current_prompt_name = name
        content = self.app.prompt_manager.get_prompt_content(name)
        self.name_var.set(name)
        self.text_editor.delete(1.0, tk.END)
        self.text_editor.insert(1.0, content)
        self.save_btn.config(state=tk.NORMAL)
    def _save_current(self):
        if not self.current_prompt_name:
            return
        new_content = self.text_editor.get(1.0, tk.END).strip()
        self.app.update("update_prompt", {"name": self.current_prompt_name, "content": new_content})
        messagebox.showinfo("Сохранено", f"Промт '{self.current_prompt_name}' сохранён.")
    def _clear_editor(self):
        self.current_prompt_name = None
        self.name_var.set("")
        self.text_editor.delete(1.0, tk.END)
        self.save_btn.config(state=tk.DISABLED)
    def _create_new(self):
        name = simpledialog.askstring("Новый промт", "Введите имя нового промта (без префикса 'translator_'):")
        if name:
            if name.startswith("translator_"):
                messagebox.showwarning("Недопустимое имя", "Имя не должно начинаться с 'translator_'.")
                return
            self.app.update("create_prompt", {"name": name})
    def _delete_selected(self):
        if not self.current_prompt_name:
            return
        if self.current_prompt_name in self.app.prompt_manager.default_prompts and not self.current_prompt_name.startswith("translator_"):
            messagebox.showwarning("Удаление", "Нельзя удалить стандартный промт.")
            return
        self.app.update("delete_prompt", {"name": self.current_prompt_name})

class TranslatorPromptsTab(ttk.Frame):
    def __init__(self, parent, app: MainApp):
        super().__init__(parent)
        self.app = app
        self.current_prompt_name = None
        self._build_ui()
        self.refresh()
    def _build_ui(self):
        top_frame = ttk.LabelFrame(self, text="Список промтов переводчика")
        top_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.listbox = tk.Listbox(top_frame, height=8)
        scrollbar = ttk.Scrollbar(top_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        btn_frame = ttk.Frame(top_frame)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Создать", command=self._create_new).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить", command=self._delete_selected).pack(side=tk.LEFT, padx=5)
        editor_frame = ttk.LabelFrame(self, text="Редактор промта переводчика")
        editor_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.name_label = ttk.Label(editor_frame, text="Название:")
        self.name_label.pack(anchor='w', padx=5, pady=2)
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(editor_frame, textvariable=self.name_var, state='readonly')
        self.name_entry.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(editor_frame, text="Содержимое:").pack(anchor='w', padx=5, pady=2)
        self.text_editor = scrolledtext.ScrolledText(editor_frame, wrap=tk.WORD, height=12)
        self.text_editor.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        add_context_menu(self.text_editor)
        btn_frame2 = ttk.Frame(editor_frame)
        btn_frame2.pack(fill=tk.X, pady=5)
        self.save_btn = ttk.Button(btn_frame2, text="Сохранить", command=self._save_current)
        self.save_btn.pack(side=tk.RIGHT, padx=5)
        self.save_btn.config(state=tk.DISABLED)
    def refresh(self):
        self.listbox.delete(0, tk.END)
        prompts = self.app.prompt_manager.list_prompts()
        for name in sorted(prompts):
            if name.startswith("translator_"):
                display_name = name[len("translator_"):] if name != "translator_system" else name
                self.listbox.insert(tk.END, display_name)
        self._clear_editor()
    def add_prompt(self, name: str):
        if not name.startswith("translator_"):
            return
        self.refresh()
        display_name = name[len("translator_"):] if name != "translator_system" else name
        for i in range(self.listbox.size()):
            if self.listbox.get(i) == display_name:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(i)
                self.listbox.see(i)
                self._on_select(None)
                break
    def update_prompt(self, name: str):
        if not name.startswith("translator_"):
            return
        if self.current_prompt_name == name:
            content = self.app.prompt_manager.get_prompt_content(name)
            self.text_editor.delete(1.0, tk.END)
            self.text_editor.insert(1.0, content)
    def remove_prompt(self, name: str):
        if not name.startswith("translator_"):
            return
        self.refresh()
        if self.current_prompt_name == name:
            self._clear_editor()
    def _on_select(self, event):
        selection = self.listbox.curselection()
        if not selection:
            return
        display_name = self.listbox.get(selection[0])
        if display_name == "translator_system":
            full_name = "translator_system"
        else:
            full_name = f"translator_{display_name}"
        self.current_prompt_name = full_name
        content = self.app.prompt_manager.get_prompt_content(full_name)
        self.name_var.set(display_name)
        self.text_editor.delete(1.0, tk.END)
        self.text_editor.insert(1.0, content)
        self.save_btn.config(state=tk.NORMAL)
    def _save_current(self):
        if not self.current_prompt_name:
            return
        new_content = self.text_editor.get(1.0, tk.END).strip()
        self.app.update("update_prompt", {"name": self.current_prompt_name, "content": new_content})
        messagebox.showinfo("Сохранено", f"Промт переводчика '{self.current_prompt_name}' сохранён.")
    def _clear_editor(self):
        self.current_prompt_name = None
        self.name_var.set("")
        self.text_editor.delete(1.0, tk.END)
        self.save_btn.config(state=tk.DISABLED)
    def _create_new(self):
        name = simpledialog.askstring("Новый промт переводчика", "Введите имя нового промта (без префикса 'translator_'):")
        if name:
            if name.startswith("translator_"):
                messagebox.showwarning("Недопустимое имя", "Имя не должно начинаться с 'translator_'.")
                return
            full_name = f"translator_{name}"
            self.app.update("create_prompt", {"name": full_name})
    def _delete_selected(self):
        if not self.current_prompt_name:
            return
        if self.current_prompt_name == "translator_system":
            messagebox.showwarning("Удаление", "Нельзя удалить стандартный промт переводчика.")
            return
        self.app.update("delete_prompt", {"name": self.current_prompt_name})

class BaseEditorTab(ttk.Frame):
    def __init__(self, parent, app: MainApp, obj_type: str, obj_class, title: str):
        super().__init__(parent)
        self.app = app
        self.obj_type = obj_type
        self.obj_class = obj_class
        self.title = title
        self.current_obj_id = None
        self.editing_mode = tk.StringVar(value="global")
        self.player_var = tk.BooleanVar(value=False)
        self._build_ui()
        self.refresh()
    def _build_ui(self):
        list_frame = ttk.LabelFrame(self, text=f"Список {self.title}")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 0))
        list_container = ttk.Frame(list_frame)
        list_container.pack(fill=tk.BOTH, expand=True)
        self.listbox = tk.Listbox(list_container, height=8)
        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(btn_frame, text="Создать", command=self._create_new).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить", command=self._delete_selected).pack(side=tk.LEFT, padx=5)
        mode_frame = ttk.LabelFrame(self, text="Режим редактирования")
        mode_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Radiobutton(mode_frame, text="Global", variable=self.editing_mode, value="global", command=self._on_mode_change).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(mode_frame, text="Session", variable=self.editing_mode, value="local", command=self._on_mode_change).pack(side=tk.LEFT, padx=5)
        self.reset_local_btn = ttk.Button(mode_frame, text="Сбросить локальное", command=self._reset_local, state=tk.DISABLED)
        self.reset_local_btn.pack(side=tk.RIGHT, padx=5)
        if self.obj_type == "characters":
            player_frame = ttk.Frame(self)
            player_frame.pack(fill=tk.X, padx=5, pady=5)
            self.player_check = ttk.Checkbutton(player_frame, text="Это персонаж игрока (ГГ)", variable=self.player_var, command=self._on_player_flag_change)
            self.player_check.pack(side=tk.LEFT)
        editor_frame = ttk.LabelFrame(self, text="Редактор")
        editor_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Label(editor_frame, text="Название:").pack(anchor='w', padx=5, pady=2)
        self.name_entry = ttk.Entry(editor_frame, width=30)
        self.name_entry.pack(fill=tk.X, padx=5, pady=2)
        add_context_menu(self.name_entry)
        ttk.Label(editor_frame, text="Описание:").pack(anchor='w', padx=5, pady=2)
        self.desc_text = scrolledtext.ScrolledText(editor_frame, height=10, wrap=tk.WORD)
        self.desc_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        add_context_menu(self.desc_text)
        save_btn = ttk.Button(editor_frame, text="Сохранить", command=self._save_current)
        save_btn.pack(pady=5)
    def _get_objects_dict(self):
        if self.obj_type == "narrators":
            return self.app.narrators
        elif self.obj_type == "characters":
            return self.app.characters
        elif self.obj_type == "locations":
            return self.app.locations
        elif self.obj_type == "items":
            return self.app.items
        return {}
    def _extract_num(self, obj_id: str) -> int:
        match = re.search(r'\d+$', obj_id)
        return int(match.group()) if match else 0
    def _populate_list(self):
        self.listbox.delete(0, tk.END)
        objects_dict = self._get_objects_dict()
        sorted_ids = sorted(objects_dict.keys(), key=self._extract_num)
        for obj_id in sorted_ids:
            obj = objects_dict[obj_id]
            text = f"{obj.name} (id:{obj.id})"
            if self.obj_type == "characters" and obj.is_player:
                text += " [ИГРОК]"
            self.listbox.insert(tk.END, text)
    def refresh(self):
        current_selection = self.current_obj_id
        self._populate_list()
        if current_selection and current_selection in self._get_objects_dict():
            self._select_object_by_id(current_selection)
        else:
            self._clear_form()
    def add_object(self, obj_id: str):
        self.refresh()
        self._select_object_by_id(obj_id)
    def update_object(self, obj_id: str):
        if self.current_obj_id == obj_id:
            self._load_current_description()
        self.refresh()
    def remove_object(self, obj_id: str):
        if self.current_obj_id == obj_id:
            self._clear_form()
        self.refresh()
    def _on_mode_change(self):
        if self.current_obj_id:
            self._load_current_description()
            local_exists = self.current_obj_id in self.app.local_descriptions
            self.reset_local_btn.config(state=tk.NORMAL if local_exists else tk.DISABLED)
    def _load_current_description(self):
        if not self.current_obj_id:
            return
        obj = self._get_objects_dict().get(self.current_obj_id)
        if not obj:
            return
        self.name_entry.delete(0, tk.END)
        self.name_entry.insert(0, obj.name)
        self.desc_text.delete(1.0, tk.END)
        if self.editing_mode.get() == "global":
            self.desc_text.insert(1.0, obj.description)
            if self.obj_type == "characters":
                self.player_var.set(obj.is_player)
                self.player_check.config(state=tk.NORMAL)
        else:
            local_desc = self.app.local_descriptions.get(self.current_obj_id, "")
            self.desc_text.insert(1.0, local_desc)
            if self.obj_type == "characters":
                self.player_var.set(obj.is_player)
                self.player_check.config(state=tk.DISABLED)
    def _clear_form(self):
        self.current_obj_id = None
        self.name_entry.delete(0, tk.END)
        self.desc_text.delete(1.0, tk.END)
        if self.obj_type == "characters":
            self.player_var.set(False)
            self.player_check.config(state=tk.NORMAL)
        self.reset_local_btn.config(state=tk.DISABLED)
    def _create_new(self):
        default_name = "Новый объект"
        default_desc = ""
        data = {"name": default_name, "description": default_desc}
        if self.obj_type == "characters":
            data["is_player"] = False
        if self.obj_type == "narrators":
            self.app.update("update_narrator", data)
        elif self.obj_type == "characters":
            self.app.update("create_character", data)
        elif self.obj_type == "locations":
            self.app.update("create_location", data)
        elif self.obj_type == "items":
            self.app.update("create_item", data)
    def _delete_selected(self):
        if not self.current_obj_id:
            return
        obj = self._get_objects_dict().get(self.current_obj_id)
        if not obj:
            return
        if messagebox.askyesno("Удаление", f"Удалить '{obj.name}'?"):
            if self.obj_type == "narrators":
                self.app.update("delete_narrator", {"id": self.current_obj_id})
            elif self.obj_type == "characters":
                self.app.update("delete_character", {"id": self.current_obj_id})
            elif self.obj_type == "locations":
                self.app.update("delete_location", {"id": self.current_obj_id})
            elif self.obj_type == "items":
                self.app.update("delete_item", {"id": self.current_obj_id})
    def _save_current(self):
        name = self.name_entry.get().strip()
        desc = self.desc_text.get(1.0, tk.END).strip()
        if not name:
            messagebox.showwarning("Ошибка", "Введите название")
            return
        if self.editing_mode.get() == "global":
            if not self.current_obj_id:
                data = {"name": name, "description": desc}
                if self.obj_type == "characters":
                    data["is_player"] = self.player_var.get()
                if self.obj_type == "narrators":
                    self.app.update("update_narrator", data)
                elif self.obj_type == "characters":
                    self.app.update("create_character", data)
                elif self.obj_type == "locations":
                    self.app.update("create_location", data)
                elif self.obj_type == "items":
                    self.app.update("create_item", data)
            else:
                data = {"id": self.current_obj_id, "name": name, "description": desc}
                if self.obj_type == "characters":
                    data["is_player"] = self.player_var.get()
                if self.obj_type == "narrators":
                    self.app.update("update_narrator", data)
                elif self.obj_type == "characters":
                    self.app.update("update_character", data)
                elif self.obj_type == "locations":
                    self.app.update("update_location", data)
                elif self.obj_type == "items":
                    self.app.update("update_item", data)
        else:
            if self.current_obj_id:
                self.app.update("set_local_description", {"obj_id": self.current_obj_id, "description": desc})
                self.reset_local_btn.config(state=tk.NORMAL if desc.strip() else tk.DISABLED)
    def _reset_local(self):
        if self.current_obj_id and self.current_obj_id in self.app.local_descriptions:
            if messagebox.askyesno("Сброс", "Удалить локальное описание?"):
                self.app.update("clear_local_description", {"obj_id": self.current_obj_id})
                if self.editing_mode.get() == "local":
                    self.desc_text.delete(1.0, tk.END)
                    self.reset_local_btn.config(state=tk.DISABLED)
    def _on_select(self, event):
        selection = self.listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        objects_dict = self._get_objects_dict()
        sorted_ids = sorted(objects_dict.keys(), key=self._extract_num)
        if idx < len(sorted_ids):
            obj_id = sorted_ids[idx]
            self.current_obj_id = obj_id
            self._load_current_description()
            local_exists = obj_id in self.app.local_descriptions
            self.reset_local_btn.config(state=tk.NORMAL if local_exists else tk.DISABLED)
    def _select_object_by_id(self, obj_id: str):
        objects_dict = self._get_objects_dict()
        if obj_id not in objects_dict:
            return
        self.current_obj_id = obj_id
        self._load_current_description()
        local_exists = obj_id in self.app.local_descriptions
        self.reset_local_btn.config(state=tk.NORMAL if local_exists else tk.DISABLED)
        sorted_ids = sorted(objects_dict.keys(), key=self._extract_num)
        try:
            pos = sorted_ids.index(obj_id)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(pos)
            self.listbox.see(pos)
        except ValueError:
            pass
    def _on_player_flag_change(self):
        if self.editing_mode.get() == "global" and self.current_obj_id:
            obj = self._get_objects_dict().get(self.current_obj_id)
            if obj and obj.is_player != self.player_var.get():
                data = {"id": self.current_obj_id, "name": obj.name, "description": obj.description, "is_player": self.player_var.get()}
                self.app.update("update_character", data)

class SettingsDialog:
    def __init__(self, parent, current_settings):
        self.top = tk.Toplevel(parent)
        self.top.title("Настройки")
        self.top.geometry("550x700")
        self.top.transient(parent)
        self.top.grab_set()
        self.result = None
        self.parent = parent
        main_frame = ttk.Frame(self.top, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main_frame, text="API URL:").grid(row=0, column=0, sticky="w", pady=5)
        self.api_url = ttk.Entry(main_frame, width=50)
        self.api_url.insert(0, current_settings.get("api_url", "http://localhost:1234/v1"))
        self.api_url.grid(row=0, column=1, sticky="ew", pady=5)
        add_context_menu(self.api_url)
        self.use_two_models_var = tk.BooleanVar(value=current_settings.get("use_two_models", False))
        ttk.Checkbutton(main_frame, text="Использовать две модели", variable=self.use_two_models_var, command=self._toggle_two_models).grid(row=1, column=0, columnspan=2, sticky="w", pady=5)
        self.single_frame = ttk.LabelFrame(main_frame, text="Одиночный режим")
        self.single_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=5)
        ttk.Label(self.single_frame, text="Модель:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.model_name_combo = ttk.Combobox(self.single_frame, width=40)
        self.model_name_combo.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        self.model_name_combo.set(current_settings.get("model_name", "local-model"))
        ttk.Label(self.single_frame, text="Температура:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.single_temp = ttk.Spinbox(self.single_frame, from_=0.0, to=2.0, increment=0.1, width=10)
        self.single_temp.delete(0, tk.END)
        self.single_temp.insert(0, str(current_settings.get("temperature", 0.7)))
        self.single_temp.grid(row=1, column=1, sticky="w", padx=5, pady=2)
        ttk.Label(self.single_frame, text="Max tokens:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.single_max_tokens = ttk.Spinbox(self.single_frame, from_=0, to=200000, width=10)
        self.single_max_tokens.delete(0, tk.END)
        self.single_max_tokens.insert(0, str(current_settings.get("max_tokens", 4096)))
        self.single_max_tokens.grid(row=2, column=1, sticky="w", padx=5, pady=2)
        self.single_frame.columnconfigure(1, weight=1)
        self.dual_frame = ttk.LabelFrame(main_frame, text="Двухмодельный режим")
        self.dual_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=5)
        ttk.Label(self.dual_frame, text="Основная модель:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.primary_model_combo = ttk.Combobox(self.dual_frame, width=40)
        self.primary_model_combo.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        self.primary_model_combo.set(current_settings.get("primary_model", "local-model"))
        ttk.Label(self.dual_frame, text="Температура (осн.):").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.primary_temp = ttk.Spinbox(self.dual_frame, from_=0.0, to=2.0, increment=0.1, width=10)
        self.primary_temp.delete(0, tk.END)
        self.primary_temp.insert(0, str(current_settings.get("primary_temperature", 0.7)))
        self.primary_temp.grid(row=1, column=1, sticky="w", padx=5, pady=2)
        ttk.Label(self.dual_frame, text="Max tokens (осн.):").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.primary_max_tokens = ttk.Spinbox(self.dual_frame, from_=0, to=200000, width=10)
        self.primary_max_tokens.delete(0, tk.END)
        self.primary_max_tokens.insert(0, str(current_settings.get("primary_max_tokens", 4096)))
        self.primary_max_tokens.grid(row=2, column=1, sticky="w", padx=5, pady=2)
        ttk.Label(self.dual_frame, text="Модель-переводчик:").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        self.translator_model_combo = ttk.Combobox(self.dual_frame, width=40)
        self.translator_model_combo.grid(row=3, column=1, sticky="ew", padx=5, pady=2)
        self.translator_model_combo.set(current_settings.get("translator_model", "local-model"))
        ttk.Label(self.dual_frame, text="Температура (пер.):").grid(row=4, column=0, sticky="w", padx=5, pady=2)
        self.translator_temp = ttk.Spinbox(self.dual_frame, from_=0.0, to=2.0, increment=0.1, width=10)
        self.translator_temp.delete(0, tk.END)
        self.translator_temp.insert(0, str(current_settings.get("translator_temperature", 0.3)))
        self.translator_temp.grid(row=4, column=1, sticky="w", padx=5, pady=2)
        ttk.Label(self.dual_frame, text="Max tokens (пер.):").grid(row=5, column=0, sticky="w", padx=5, pady=2)
        self.translator_max_tokens = ttk.Spinbox(self.dual_frame, from_=0, to=200000, width=10)
        self.translator_max_tokens.delete(0, tk.END)
        self.translator_max_tokens.insert(0, str(current_settings.get("translator_max_tokens", 4096)))
        self.translator_max_tokens.grid(row=5, column=1, sticky="w", padx=5, pady=2)
        self.dual_frame.columnconfigure(1, weight=1)
        refresh_btn = ttk.Button(main_frame, text="Обновить список моделей", command=self._refresh_models_list)
        refresh_btn.grid(row=3, column=0, columnspan=2, pady=5)
        self.enable_assistant_translation_var = tk.BooleanVar(value=current_settings.get("enable_assistant_translation", False))
        self.translation_cb = ttk.Checkbutton(main_frame, text="Переводить ответы ассистента", variable=self.enable_assistant_translation_var)
        self.translation_cb.grid(row=4, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Label(main_frame, text="Max History Messages:").grid(row=5, column=0, sticky="w", pady=5)
        self.max_history = ttk.Spinbox(main_frame, from_=0, to=50, width=10)
        # Память (summary)
        self.enable_memory_var = tk.BooleanVar(value=current_settings.get("enable_memory_summary", False))
        ttk.Checkbutton(main_frame, text="Включить краткую память (summary)", variable=self.enable_memory_var).grid(row=9, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Label(main_frame, text="Максимум резюме в памяти:").grid(row=10, column=0, sticky="w", pady=5)
        self.max_memory_summaries = ttk.Spinbox(main_frame, from_=1, to=20, width=10)
        self.max_memory_summaries.delete(0, tk.END)
        self.max_memory_summaries.insert(0, str(current_settings.get("max_memory_summaries", 5)))
        self.max_memory_summaries.grid(row=10, column=1, sticky="w", pady=5)

        self.max_history.delete(0, tk.END)
        self.max_history.insert(0, str(current_settings.get("max_history_messages", 10)))
        self.max_history.grid(row=5, column=1, sticky="w", pady=5)

        
        ttk.Label(main_frame, text="Количество d20:").grid(row=6, column=0, sticky="w", pady=5)
        self.d20_count = ttk.Spinbox(main_frame, from_=0, to=100, width=10)
        self.d20_count.delete(0, tk.END)
        self.d20_count.insert(0, str(current_settings.get("dice_d20_count", 10)))
        self.d20_count.grid(row=6, column=1, sticky="w", pady=5)
        ttk.Label(main_frame, text="Количество d100:").grid(row=7, column=0, sticky="w", pady=5)
        self.d100_count = ttk.Spinbox(main_frame, from_=0, to=50, width=10)
        self.d100_count.delete(0, tk.END)
        self.d100_count.insert(0, str(current_settings.get("dice_d100_count", 10)))
        self.d100_count.grid(row=7, column=1, sticky="w", pady=5)
        ttk.Label(main_frame, text="Количество d6:").grid(row=8, column=0, sticky="w", pady=5)
        self.d6_count = ttk.Spinbox(main_frame, from_=0, to=200, width=10)
        self.d6_count.delete(0, tk.END)
        self.d6_count.insert(0, str(current_settings.get("dice_d6_count", 100)))
        self.d6_count.grid(row=8, column=1, sticky="w", pady=5)
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=11, column=0, columnspan=2, pady=20)
        ttk.Button(btn_frame, text="Сохранить", command=self._save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.top.destroy).pack(side=tk.LEFT, padx=5)
        main_frame.columnconfigure(1, weight=1)
        self._refresh_models_list()
        self._toggle_two_models()
    def _refresh_models_list(self):
        api_url = self.api_url.get().strip()
        base_url = api_url.rstrip('/')
        if base_url.endswith('/v1'):
            base_url = base_url[:-3]
        models = ["local-model"]
        try:
            url = f"{base_url}/v1/models"
            response = requests.get(url, timeout=5)
            if response.status_code != 200:
                url = f"{base_url}/models"
                response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if "data" in data:
                    for item in data["data"]:
                        if "id" in item:
                            models.append(item["id"])
                elif "models" in data:
                    for item in data["models"]:
                        if "id" in item:
                            models.append(item["id"])
                        elif "key" in item:
                            models.append(item["key"])
                seen = set()
                unique = []
                for m in models:
                    if m not in seen:
                        seen.add(m)
                        unique.append(m)
                models = unique
            else:
                messagebox.showwarning("Предупреждение", f"Не удалось получить список моделей (HTTP {response.status_code})")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при запросе к LM Studio:\n{e}")
        self.model_name_combo['values'] = models
        self.primary_model_combo['values'] = models
        self.translator_model_combo['values'] = models
        if self.model_name_combo.get() not in models:
            self.model_name_combo.set(models[0] if models else "local-model")
        if self.primary_model_combo.get() not in models:
            self.primary_model_combo.set(models[0] if models else "local-model")
        if self.translator_model_combo.get() not in models:
            self.translator_model_combo.set(models[0] if models else "local-model")
        model_count = len(models) - 1
        messagebox.showinfo("Список моделей", f"Найдено {model_count} загруженных моделей.\n\n" + "\n".join(models))
    def _toggle_two_models(self):
        if self.use_two_models_var.get():
            self.dual_frame.grid()
            self.single_frame.grid_remove()
            self.translation_cb.grid()
        else:
            self.single_frame.grid()
            self.dual_frame.grid_remove()
            self.translation_cb.grid_remove()
    def _save(self):
        use_two = self.use_two_models_var.get()
        self.result = {
            "api_url": self.api_url.get().strip(),
            "model_name": self.model_name_combo.get(),
            "max_history_messages": int(self.max_history.get()),
            "dice_d20_count": int(self.d20_count.get()),
            "dice_d100_count": int(self.d100_count.get()),
            "dice_d6_count": int(self.d6_count.get()),
            "use_two_models": use_two,
            "primary_model": self.primary_model_combo.get(),
            "translator_model": self.translator_model_combo.get(),
            "enable_assistant_translation": self.enable_assistant_translation_var.get(),
            "primary_temperature": float(self.primary_temp.get()),
            "primary_max_tokens": int(self.primary_max_tokens.get()),
            "translator_temperature": float(self.translator_temp.get()),
            "translator_max_tokens": int(self.translator_max_tokens.get()),
            "temperature": float(self.single_temp.get()),
            "max_tokens": int(self.single_max_tokens.get()),
            "enable_memory_summary": self.enable_memory_var.get(),
            "max_memory_summaries": int(self.max_memory_summaries.get()),
        }
        self.top.destroy()

# ==================== ИСПРАВЛЕННЫЙ КЛАСС StagePromptsTab ====================
class StagePromptsTab(ttk.Frame):
    """
    Вкладка настройки порядка системных сообщений для каждого этапа генерации.
    
    Порядок имеет значение: сообщения добавляются в том порядке, в котором они
    перечислены в списке. Модель читает их последовательно, и последние сообщения
    (внизу списка) оказывают наибольшее влияние, так как они «свежее» в памяти.
    Поэтому самые важные системные инструкции рекомендуется размещать в конце.
    """
    def __init__(self, parent, app: MainApp):
        super().__init__(parent)
        self.app = app
        self.stages = [
            "stage1_request_descriptions",
            "stage1_truth_check",    
            "stage1_player_action",
            "stage1_random_event",
            "stage1_turn_order",
            "stage2_npc_action",
            "stage3_final",
            "stage4_summary"
        ]
        self.current_stage = None
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # Используем grid для всей вкладки
        self.grid_rowconfigure(1, weight=1)   # строка с этапами/промтами растягивается
        self.grid_columnconfigure(0, weight=1)

        # ========== РЯД 1: Пояснение ==========
        info_frame = ttk.LabelFrame(self, text="Важно: порядок системных сообщений")
        info_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        info_text = (
            "Сообщения передаются модели в том порядке, в котором они перечислены (сверху вниз).\n"
            "Модель лучше запоминает последние сообщения, поэтому самые важные инструкции\n"
            "рекомендуется размещать в КОНЦЕ списка (нижняя часть).\n"
            "Используйте кнопки «Вверх» / «Вниз» для изменения приоритета."
        )
        ttk.Label(info_frame, text=info_text, wraplength=700, justify=tk.LEFT).pack(padx=5, pady=5)

        # ========== РЯД 2: Две колонки (Этапы и Системные промты) ==========
        main_row = ttk.Frame(self)
        main_row.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        main_row.grid_columnconfigure(0, weight=1)
        main_row.grid_columnconfigure(1, weight=3)

        # Левая колонка: список этапов
        left_frame = ttk.LabelFrame(main_row, text="Этапы")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        left_frame.grid_rowconfigure(0, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        self.stage_listbox = tk.Listbox(left_frame, height=12, font=("Arial", 10))
        for stage in self.stages:
            self.stage_listbox.insert(tk.END, stage)
        self.stage_listbox.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        stage_scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.stage_listbox.yview)
        stage_scrollbar.grid(row=0, column=1, sticky="ns", pady=5)
        self.stage_listbox.configure(yscrollcommand=stage_scrollbar.set)
        self.stage_listbox.bind("<<ListboxSelect>>", self._on_stage_select)

        # Правая колонка: список промтов для выбранного этапа
        right_frame = ttk.LabelFrame(main_row, text="Системные промты для выбранного этапа (порядок важен)")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        list_container = ttk.Frame(right_frame)
        list_container.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        list_container.grid_rowconfigure(0, weight=1)
        list_container.grid_columnconfigure(0, weight=1)

        self.prompts_listbox = tk.Listbox(list_container, height=10, font=("Arial", 10))
        self.prompts_listbox.grid(row=0, column=0, sticky="nsew")
        prompts_scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.prompts_listbox.yview)
        prompts_scrollbar.grid(row=0, column=1, sticky="ns")
        self.prompts_listbox.configure(yscrollcommand=prompts_scrollbar.set)

        # ========== РЯД 3: Кнопки (4 ряда по 2 кнопки) ==========
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        # Ряд 1
        ttk.Button(btn_frame, text="➕ Добавить системный промт", command=self._add_prompt).grid(row=0, column=0, padx=3, pady=2, sticky="ew")
        ttk.Button(btn_frame, text="📚 Добавить рассказчиков", command=self._add_narrators).grid(row=0, column=1, padx=3, pady=2, sticky="ew")

        # Ряд 2
        ttk.Button(btn_frame, text="❌ Удалить выбранный", command=self._remove_prompt).grid(row=1, column=0, padx=3, pady=2, sticky="ew")
        ttk.Button(btn_frame, text="🗑️ Удалить всех рассказчиков", command=self._remove_all_narrators).grid(row=1, column=1, padx=3, pady=2, sticky="ew")

        # Ряд 3
        ttk.Button(btn_frame, text="⬆️ Вверх", command=lambda: self._move_prompt(-1)).grid(row=2, column=0, padx=3, pady=2, sticky="ew")
        ttk.Button(btn_frame, text="⬇️ Вниз", command=lambda: self._move_prompt(1)).grid(row=2, column=1, padx=3, pady=2, sticky="ew")

        # Ряд 4
        ttk.Button(btn_frame, text="📜 Добавить историю чата", command=self._add_history).grid(row=3, column=0, padx=3, pady=2, sticky="ew")
        ttk.Button(btn_frame, text="💾 Сохранить", command=self._save_config).grid(row=3, column=1, padx=3, pady=2, sticky="ew")

    def _on_stage_select(self, event):
        selection = self.stage_listbox.curselection()
        if not selection:
            return
        self.current_stage = self.stages[selection[0]]
        self._refresh_prompts_list()

    def _refresh_prompts_list(self):
        self.prompts_listbox.delete(0, tk.END)
        if not self.current_stage:
            return
        prompts = self.app.stage_prompts_config.get(self.current_stage, [])
        for entry in prompts:
            if entry.startswith("narrator:"):
                narr_id = entry[9:]
                narr = self.app.narrators.get(narr_id)
                display = f"📖 {narr.name if narr else narr_id}"
            elif entry.startswith("history"):
                parts = entry.split(":", 1)
                if len(parts) > 1 and parts[1].isdigit():
                    count = parts[1]
                    display = f"📜 История ({count} сообщ.)"
                else:
                    display = "📜 История (все сообщения)"
            else:
                display = f"💬 {entry}"
            self.prompts_listbox.insert(tk.END, display)

    def _add_prompt(self):
        all_prompts = self.app.prompt_manager.list_prompts()
        all_prompts = [p for p in all_prompts if not p.startswith("translator_")]
        if not all_prompts:
            messagebox.showinfo("Нет промтов", "Сначала создайте хотя бы один системный промт во вкладке 'Системные промты'.")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Выберите системный промт")
        dialog.geometry("400x300")
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text="Доступные промты:").pack(pady=5)
        listbox = tk.Listbox(dialog, height=15)
        listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        for p in all_prompts:
            listbox.insert(tk.END, p)

        def on_select():
            sel = listbox.curselection()
            if sel:
                selected = listbox.get(sel[0])
                current = self.app.stage_prompts_config.get(self.current_stage, [])
                if selected not in current:
                    current.append(selected)
                    self.app.stage_prompts_config[self.current_stage] = current
                    self._refresh_prompts_list()
                    self.app.save_stage_prompts_config()
                dialog.destroy()

        ttk.Button(dialog, text="Выбрать", command=on_select).pack(pady=5)
        ttk.Button(dialog, text="Отмена", command=dialog.destroy).pack(pady=2)
        listbox.bind("<Double-Button-1>", lambda e: on_select())

    def _add_narrators(self):
        enabled_narrators = self.app.current_profile.enabled_narrators
        if not enabled_narrators:
            messagebox.showinfo("Нет рассказчиков", "В текущем профиле не выбран ни один рассказчик. Сначала добавьте рассказчиков в профиль.")
            return

        current = self.app.stage_prompts_config.get(self.current_stage, [])
        sel = self.prompts_listbox.curselection()
        insert_idx = sel[0] if sel else len(current)

        new_entries = [f"narrator:{nid}" for nid in enabled_narrators if nid in self.app.narrators]
        if not new_entries:
            messagebox.showinfo("Нет рассказчиков", "Выбранные рассказчики не найдены в базе.")
            return

        for i, entry in enumerate(new_entries):
            current.insert(insert_idx + i, entry)

        self.app.stage_prompts_config[self.current_stage] = current
        self._refresh_prompts_list()
        if new_entries:
            self.prompts_listbox.selection_set(insert_idx)
            self.prompts_listbox.see(insert_idx)
        self.app.save_stage_prompts_config()
        messagebox.showinfo("Рассказчики добавлены", f"Добавлено {len(new_entries)} рассказчиков.")

    def _remove_all_narrators(self):
        if not self.current_stage:
            return
        current = self.app.stage_prompts_config.get(self.current_stage, [])
        new_list = [entry for entry in current if not entry.startswith("narrator:")]
        if len(new_list) == len(current):
            messagebox.showinfo("Нет рассказчиков", "В текущем этапе нет рассказчиков.")
            return
        self.app.stage_prompts_config[self.current_stage] = new_list
        self._refresh_prompts_list()
        self.app.save_stage_prompts_config()
        messagebox.showinfo("Удаление", "Все рассказчики удалены из текущего этапа.")

    def _remove_prompt(self):
        selection = self.prompts_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        current = self.app.stage_prompts_config.get(self.current_stage, [])
        if idx < len(current):
            del current[idx]
            self.app.stage_prompts_config[self.current_stage] = current
            self._refresh_prompts_list()
            self.app.save_stage_prompts_config()

    def _move_prompt(self, delta):
        selection = self.prompts_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        current = self.app.stage_prompts_config.get(self.current_stage, [])
        new_idx = idx + delta
        if 0 <= new_idx < len(current):
            item = current.pop(idx)
            current.insert(new_idx, item)
            self.app.stage_prompts_config[self.current_stage] = current
            self._refresh_prompts_list()
            self.prompts_listbox.selection_set(new_idx)
            self.app.save_stage_prompts_config()

    def _save_config(self):
        self.app.save_stage_prompts_config()
        messagebox.showinfo("Сохранено", "Конфигурация этапов сохранена.")

    def refresh(self):
        self._refresh_prompts_list()

    def _add_history(self):
        max_history = self.app.settings.get("max_history_messages", 10)
        current = self.app.stage_prompts_config.get(self.current_stage, [])
        sel = self.prompts_listbox.curselection()
        idx = sel[0] if sel else len(current)
        if max_history == 0:
            entry = "history"
        else:
            entry = f"history:{max_history}"
        current.insert(idx, entry)
        self.app.stage_prompts_config[self.current_stage] = current
        self._refresh_prompts_list()
        if sel:
            self.prompts_listbox.selection_set(idx)
        self.app.save_stage_prompts_config()

    def cleanup_inactive_narrators(self):
        """
        Удаляет из всех этапов записи рассказчиков, которые:
        - отсутствуют в self.app.narrators (удалены из базы)
        - или не включены в текущем профиле (self.app.current_profile.enabled_narrators)
        """
        if not hasattr(self.app, 'stage_prompts_config'):
            return
        active_narrator_ids = set(self.app.current_profile.enabled_narrators) & set(self.app.narrators.keys())
        changed = False
        for stage in self.stages:
            config = self.app.stage_prompts_config.get(stage, [])
            new_config = []
            for entry in config:
                if entry.startswith("narrator:"):
                    narr_id = entry[9:]
                    if narr_id in active_narrator_ids:
                        new_config.append(entry)
                    else:
                        changed = True
                else:
                    new_config.append(entry)
            if new_config != config:
                self.app.stage_prompts_config[stage] = new_config
        if changed:
            self.app.save_stage_prompts_config()
            if self.current_stage:
                self._refresh_prompts_list()

if __name__ == "__main__":
    app = MainApp()
    app.mainloop()