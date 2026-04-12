# Project_Py3_RPG_AI_main_Tools_version_V0.5.1.py
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
import sys
from models import BaseObject, Narrator, Character, Location, Item, GameProfile
from ui_utils import add_context_menu
from center_panel import CenterPanel
from left_panel import LeftPanel
from right_panel import RightPanel
from ui_tabs import ProfileTab, BaseEditorTab, SystemPromptsTab, TranslatorPromptsTab, StagePromptsTab

# Импортируем новый класс StageProcessor
from stage_processor import StageProcessor

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
            with open(temp_filename, "w", encoding="utf-8") as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            os.replace(temp_filename, filename)
        except Exception:
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

# ---------- Prompt Manager (с автосозданием недостающих промтов) ----------
class PromptManager:
    REQUIRED_PROMPTS = [
        "stage1_request_descriptions",
        "stage1_validate_scene",
        "stage1_truth_check",
        "stage1_player_action",
        "stage1_random_event",
        "stage1_validate_random_event",
        "stage1_turn_order",
        "stage2_npc_action",
        "stage3_final",
        "stage4_summary",
        "dice_rules",
        "stage1_random_event_continue",
        "translator_system",
        "compress_description"
    ]

    def __init__(self, prompts_dir: str = "System_Prompts"):
        self.prompts_dir = prompts_dir
        self._ensure_dir()
        self._create_default_prompts()
        self._check_required_prompts()

    def _ensure_dir(self):
        os.makedirs(self.prompts_dir, exist_ok=True)

    def _create_default_prompts(self):
        defaults = {
            "compress_description": """Ты — помощник, который сжимает описания игровых объектов (персонажей, локаций, предметов) до краткого, но информативного вида. Сохрани ключевые черты, внешность, характер, важные детали. Ответ должен быть на русском, не более {max_length} символов.

Исходное описание:
{description}"""
        }
        for name in self.REQUIRED_PROMPTS:
            filepath = os.path.join(self.prompts_dir, f"{name}.json")
            if not os.path.exists(filepath):
                content = defaults.get(name, "")
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump({"name": name, "content": content}, f, ensure_ascii=False, indent=2)

    def _check_required_prompts(self):
        missing = []
        for name in self.REQUIRED_PROMPTS:
            filepath = os.path.join(self.prompts_dir, f"{name}.json")
            if not os.path.exists(filepath):
                missing.append(name)
        if missing:
            messagebox.showerror(
                "Ошибка инициализации",
                f"Отсутствуют обязательные файлы промтов в папке '{self.prompts_dir}':\n\n" +
                "\n".join(missing) +
                "\n\nПрограмма будет закрыта."
            )
            sys.exit(1)

    def load_prompt(self, name: str) -> str:
        filepath = os.path.join(self.prompts_dir, f"{name}.json")
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Промт '{name}' не найден в папке '{self.prompts_dir}'")
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("content", "")

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

# ---------- LM Studio Client (без изменений) ----------
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
                                "location_id": {"type": "string", "description": "ID локации (может быть null, если не определена)"},
                                "character_ids": {"type": "array", "items": {"type": "string"}, "description": "Массив ID персонажей, которые действительно присутствуют в сцене"},
                                "item_ids": {"type": "array", "items": {"type": "string"}, "description": "Массив ID предметов, присутствующих в сцене"}
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
                                "object_ids": {"type": "array", "items": {"type": "string"}, "description": "Массив ID объектов (например, ['c1', 'c2', 'l1'])"}
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
                                "dice_type": {"type": "string", "enum": ["d20", "d100", "d6"], "description": "Тип кубика"}
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
                                "dice_type": {"type": "string", "enum": ["d20", "d100", "d6"], "description": "Тип кубика для броска"},
                                "chance": {"type": "integer", "description": "Шанс события в процентах (0-100)."}
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
                {
                    "type": "function",
                    "function": {
                        "name": "report_validation_result",
                        "description": "Сообщает результат проверки сцены.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "valid": {"type": "boolean"},
                                "feedback": {"type": "string", "description": "Причина отказа, если valid=false"}
                            },
                            "required": ["valid"]
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
            response = requests.post(url, json=payload, stream=True, timeout=None)
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

    # Синхронный вызов для сжатия описаний (без стриминга, без tools)
    def chat_completion_sync(self, messages: List[Dict], model: str, temperature: float = 0.3, max_tokens: int = 500, timeout: int = 10) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }
        try:
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[Ошибка сжатия: {e}]"

# ---------- Main Application (рефакторинг: добавлены методы для сжатия описаний, show_thinking, max_history) ----------
class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RPG AI Assistant")
        self.geometry("1200x700")
        self.minsize(900, 600)
        self.stage_names = [
            "stage1_request_descriptions",
            "stage1_validate_scene",
            "stage1_truth_check",
            "stage1_player_action",
            "stage1_random_event",
            "stage1_validate_random_event",
            "stage1_turn_order",
            "stage2_npc_action",
            "stage3_final",
            "stage4_summary"
        ]
        self.memory_summary = ""
        self.settings_file = "settings.json"
        self.settings = self.load_settings()
        self.storage = StorageManager()
        self.prompt_manager = PromptManager(prompts_dir="System_Prompts")

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
        self.memory_summaries: List[str] = []

        self.lm_client = LMStudioClient(base_url=self.settings.get("api_url", "http://localhost:1234/v1"))

        self.is_generating = False
        self.stop_generation_flag = False

        self.current_dice_sequences = ([], [], [])
        self.dice_indices = [0, 0, 0]

        # Состояние поэтапной генерации – вынесено в StageProcessor
        self.stage_processor = StageProcessor(self)

        self.use_two_models = self.settings.get("use_two_models", False)
        self.primary_model = self.settings.get("primary_model", "local-model")
        self.translator_model = self.settings.get("translator_model", "local-model")
        self.enable_assistant_translation = self.settings.get("enable_assistant_translation", False)
        self.model_name = self.settings.get("model_name", "local-model")
        self.primary_temperature = self.settings.get("primary_temperature", 0.7)
        self.primary_max_tokens = self.settings.get("primary_max_tokens", 4096)
        self.translator_temperature = self.settings.get("translator_temperature", 0.3)
        self.translator_max_tokens = self.settings.get("translator_max_tokens", 4096)

        # Настройки сжатия описаний
        self.compress_descriptions = self.settings.get("compress_descriptions", False)
        self.max_compressed_desc_length = self.settings.get("max_compressed_desc_length", 500)

        # Настройка показа reasoning
        self.show_thinking = self.settings.get("show_thinking", True)

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
            "update_narrator": lambda data: self._handle_update_object("narrators", data),
            "create_narrator": lambda data: self._handle_create_object("narrators", data),
            "delete_narrator": lambda data: self._handle_delete_object("narrators", data.get("id")),
            "create_character": lambda data: self._handle_create_object("characters", data),
            "update_character": lambda data: self._handle_update_object("characters", data),
            "delete_character": lambda data: self._handle_delete_object("characters", data.get("id")),
            "create_location": lambda data: self._handle_create_object("locations", data),
            "update_location": lambda data: self._handle_update_object("locations", data),
            "delete_location": lambda data: self._handle_delete_object("locations", data.get("id")),
            "create_item": lambda data: self._handle_create_object("items", data),
            "update_item": lambda data: self._handle_update_object("items", data),
            "delete_item": lambda data: self._handle_delete_object("items", data.get("id")),
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
            # Обработчики для стадий – перенаправляем в stage_processor
            "stage1_request_descriptions": lambda data: self.stage_processor._stage1_request_descriptions(data.get("retry_count", 0) if data else 0),
            "stage1_player_action": lambda data: self.stage_processor._stage1_player_action(data.get("retry_count", 0) if data else 0),
            "stage1_random_event": lambda data: self.stage_processor._stage1_random_event(data.get("retry_count", 0) if data else 0),
            "stage1_turn_order": lambda data: self.stage_processor._stage1_turn_order(data.get("retry_count", 0) if data else 0),
            "stage2_process_npc": lambda data: self.stage_processor._stage2_process_npc(data.get("retry_count", 0) if data else 0),
            "stage3_final": lambda data: self.stage_processor._stage3_final(data.get("retry_count", 0) if data else 0),
            "stage4_summary": lambda data: self.stage_processor._stage4_summary(data.get("retry_count", 0) if data else 0),
            "stage1_truth_check": lambda data: self.stage_processor._stage1_truth_check(data.get("retry_count", 0) if data else 0),
            "stage1_validate_scene": lambda data: self.stage_processor._stage1_validate_scene(data.get("retry_count", 0) if data else 0),
            "stage1_validate_random_event": lambda data: self.stage_processor._stage1_validate_random_event(data.get("retry_count", 0) if data else 0),
        }

        self._build_ui()
        self._load_all_data()
        self._load_last_session()
        self.update_idletasks()
        self.after(100, self._refresh_all_ui)
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ---------- Методы, оставшиеся без изменений (или слегка адаптированные) ----------
    def _handle_update_object(self, obj_type: str, data: dict):
        obj_id = data.get("id")
        name = data.get("name", "").strip()
        desc = data.get("description", "").strip()
        if not name:
            messagebox.showwarning("Ошибка", "Название не может быть пустым.")
            return
        objects_dict = getattr(self, obj_type, None)
        if objects_dict is None:
            messagebox.showerror("Ошибка", f"Неизвестный тип объектов: {obj_type}")
            return
        cls_map = {
            "narrators": Narrator,
            "characters": Character,
            "locations": Location,
            "items": Item
        }
        cls = cls_map.get(obj_type)
        if cls is None:
            messagebox.showerror("Ошибка", f"Неизвестный класс для {obj_type}")
            return
        if obj_id and obj_id in objects_dict:
            obj = objects_dict[obj_id]
            obj.name = name
            obj.description = desc
            if obj_type == "characters" and "is_player" in data:
                obj.is_player = data["is_player"]
            self.storage.save_object(obj_type, obj)
            action = "обновлён"
        else:
            kwargs = {"name": name, "description": desc}
            if obj_type == "characters":
                kwargs["is_player"] = data.get("is_player", False)
            obj = cls(**kwargs)
            self.storage.save_object(obj_type, obj)
            objects_dict[obj.id] = obj
            action = "создан"
        self._refresh_all_ui()
        self._save_current_session_safe()
        messagebox.showinfo("Успех", f"{cls.__name__} '{name}' {action} (ID: {obj.id}).")

    def _cleanup_old_logs(self):
        if not os.path.exists(self.logs_dir):
            return
        files = []
        for f in os.listdir(self.logs_dir):
            if f.startswith("debug_") and f.endswith(".txt"):
                full = os.path.join(self.logs_dir, f)
                files.append((full, os.path.getmtime(full)))
        files.sort(key=lambda x: x[1])
        if len(files) > self.max_log_files:
            to_delete = files[:len(files) - self.max_log_files]
            for full_path, _ in to_delete:
                try:
                    os.remove(full_path)
                except Exception:
                    pass

    def _cleanup_stage_prompts_narrators(self):
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
            "stage_prompts_config": {},
            "enable_memory_summary": True,
            "max_memory_summaries": 5,
            "compress_descriptions": False,
            "max_compressed_desc_length": 500
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
                "memory_summaries": self.memory_summaries
            }
        else:
            session_data["profile"] = self.current_profile.to_dict()
            session_data["history"] = self.conversation_history
            session_data["local_descriptions"] = self.local_descriptions
            session_data["memory_summaries"] = self.memory_summaries
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
                continue
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
        self._sync_last_user_message()
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
            self._sync_last_user_message()
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

    def _handle_regenerate_last_response(self, data=None):
        if self.is_generating:
            messagebox.showwarning("Генерация", "Модель уже генерирует ответ.")
            return
        if not self.last_user_message:
            messagebox.showinfo("Перегенерация", "Нет последнего сообщения пользователя.")
            return
        if self.conversation_history and self.conversation_history[-1]["role"] == "assistant":
            self.conversation_history.pop()
            self._save_current_session_safe()
        self.center_panel.clear_chat()
        for msg in self.conversation_history:
            role = "Вы" if msg["role"] == "user" else "Ассистент"
            tag = "user" if msg["role"] == "user" else "assistant"
            self.center_panel.display_message(f"{role}: {msg['content']}\n\n", tag)
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

    def _start_generation(self, user_message: str):
        if self.is_generating:
            messagebox.showwarning("Генерация", "Модель уже генерирует ответ.")
            return
        self.is_generating = True
        self.stop_generation_flag = False
        self.center_panel.set_input_state(tk.DISABLED)
        self.center_panel.start_new_response(clear_thinking=True)
        self.stage_processor.start_generation(user_message)

    # --------------------------------------------------------------------------
    # Общий метод отправки запроса к модели (используется StageProcessor)
    # --------------------------------------------------------------------------
    def _send_model_request(self, messages: List[Dict], callback, extra=None, expect_tool_calls=True,
                            stage_name: str = None, use_temp: bool = False, tools_override=None):
        if self.use_two_models:
            model = self.primary_model
            temp = self.primary_temperature
            max_tok = self.primary_max_tokens
        else:
            model = self.model_name
            temp = self.settings.get("temperature", 0.7)
            max_tok = self.settings.get("max_tokens", 4096)

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
                    if tools_override is not None:
                        tools = tools_override
                    else:
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
                            {
                                "type": "function",
                                "function": {
                                    "name": "report_validation_result",
                                    "description": "Сообщает результат проверки сцены.",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {
                                            "valid": {"type": "boolean"},
                                            "feedback": {"type": "string", "description": "Причина отказа, если valid=false"}
                                        },
                                        "required": ["valid"]
                                    }
                                }
                            }
                        ]

                    for chunk in self.lm_client.chat_completion_stream(messages=current_messages, model=model, temperature=temp, max_tokens=max_tok, tools=tools):
                        if self.stop_generation_flag:
                            break
                        if chunk["type"] == "reasoning":
                            reasoning_buffer += chunk["text"]
                            if self.show_thinking:
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

                if handled_calls:
                    has_assistant_msg = any(msg.get("role") == "assistant" and msg.get("tool_calls") for msg in current_messages)
                    if not has_assistant_msg:
                        assistant_msg = {"role": "assistant", "content": full_content or None, "tool_calls": tool_calls}
                        current_messages.append(assistant_msg)
                    self.after(0, lambda: _chat_loop(current_messages, depth+1))
                    return

                if tool_calls and expect_tool_calls:
                    self.after(0, lambda: callback(tool_calls, full_content, extra))
                else:
                    self.after(0, lambda: callback([], full_content, extra))

            threading.Thread(target=stream_and_process, daemon=True).start()

        _chat_loop(messages.copy())

    # ---------- Метод построения контекста (исправлен: max_history_messages) ----------
    def _build_context_messages(self, stage_name: str, main_prompt: str = "", extra_prompts: List[str] = None) -> List[Dict[str, str]]:
        messages = []

        # Краткая память (если включена) – добавляется всегда, это не история диалога
        if self.enable_memory_summary and self.memory_summaries:
            memory_text = (
                "Краткая история предыдущих событий (справочно, не заменяет инструкции ниже):\n"
                + "\n".join(f"- {s}" for s in self.memory_summaries)
            )
            messages.append({"role": "system", "content": memory_text})

        config = self.stage_prompts_config.get(stage_name, [])
        history_limit = None   # None = использовать глобальную настройку

        for entry in config:
            if entry.startswith("history:"):
                # Формат: history:5 или history:0
                parts = entry.split(":", 1)
                if len(parts) > 1 and parts[1].isdigit():
                    history_limit = int(parts[1])
                else:
                    history_limit = 0   # 0 = не добавлять
            elif entry.startswith("narrator:"):
                narr_id = entry[9:]
                narr = self.narrators.get(narr_id)
                if narr:
                    messages.append({"role": "system", "content": f"Ты — рассказчик. Твой стиль и манера повествования:\n{narr.description}"})
            else:
                content = self.prompt_manager.get_prompt_content(entry)
                if content:
                    messages.append({"role": "system", "content": content})

        # Определяем, сколько сообщений истории добавить
        if history_limit is None:
            # Нет явной директивы в конфиге – используем глобальную настройку
            history_limit = self.max_history_messages if self.max_history_messages > 0 else 0
        if history_limit > 0:
            history = [msg for msg in self.conversation_history if msg["role"] in ("user", "assistant")]
            history = history[-history_limit:]   # берём последние N сообщений
            for msg in history:
                messages.append({"role": msg["role"], "content": msg["content"]})

        if main_prompt:
            messages.append({"role": "system", "content": main_prompt})
        if extra_prompts:
            for p in extra_prompts:
                messages.append({"role": "system", "content": p})

        return messages
    
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
                # Получаем описание для модели (с возможным сжатием)
                desc = self.get_description_for_model(obj_id)
                if isinstance(obj, Character) and (obj.inventory or obj.equipped):
                    if obj.inventory:
                        inv_names = [self.items.get(iid, Item(name="?")).name for iid in obj.inventory]
                        desc += f"\nИнвентарь: {', '.join(inv_names)}"
                    if obj.equipped:
                        eq_names = [self.items.get(iid, Item(name="?")).name for iid in obj.equipped]
                        desc += f"\nЭкипировано: {', '.join(eq_names)}"
                descriptions[obj_id] = desc
            else:
                descriptions[obj_id] = f"Объект {obj_id} не найден."
        return {"descriptions": descriptions}

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
        """Возвращает описание для отображения в UI (без сжатия)."""
        obj = self._get_object_by_id(obj_id)
        if not obj:
            return f"Объект {obj_id} не найден."
        global_desc = obj.description if obj.description else "Нет глобального описания."
        local_desc = self.local_descriptions.get(obj_id, "")
        if local_desc:
            return f"Глобальное описание: {global_desc}\nЛокальное описание: {local_desc}"
        else:
            return f"Описание: {global_desc}"

    def get_description_for_model(self, obj_id: str) -> str:
        """Возвращает описание для передачи модели. Если включено сжатие, сжимает."""
        full_desc = self.get_object_description_with_local(obj_id)
        if not self.compress_descriptions:
            return full_desc
        # Сжимаем описание с помощью LLM
        return self._compress_description(full_desc)

    def _compress_description(self, description: str) -> str:
        """Сжимает описание с помощью промта compress_description."""
        if not description or len(description) <= self.max_compressed_desc_length:
            return description
        prompt_template = self.prompt_manager.get_prompt_content("compress_description")
        user_prompt = prompt_template.format(
            max_length=self.max_compressed_desc_length,
            description=description
        )
        messages = [{"role": "user", "content": user_prompt}]
        # Используем ту же модель, что и для основных запросов (можно отдельную)
        if self.use_two_models:
            model = self.primary_model
            temp = self.primary_temperature
        else:
            model = self.model_name
            temp = self.settings.get("temperature", 0.7)
        # Синхронный вызов
        compressed = self.lm_client.chat_completion_sync(
            messages=messages,
            model=model,
            temperature=temp,
            max_tokens=self.max_compressed_desc_length + 50,
            timeout=10
        )
        # Если сжатие не удалось или вернуло ошибку, возвращаем оригинал (обрезанный)
        if compressed.startswith("[Ошибка сжатия:"):
            self._log_debug("COMPRESS_ERROR", compressed)
            # Обрезаем до лимита
            if len(description) > self.max_compressed_desc_length:
                return description[:self.max_compressed_desc_length] + "..."
            return description
        # Убираем лишние пробелы и переносы
        compressed = compressed.strip()
        if len(compressed) > self.max_compressed_desc_length + 20:
            compressed = compressed[:self.max_compressed_desc_length] + "..."
        return compressed

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

    def _handle_create_object(self, obj_type: str, data: dict):
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        if not name:
            messagebox.showwarning("Ошибка", "Название не может быть пустым.")
            return
        cls_map = {
            "narrators": Narrator,
            "characters": Character,
            "locations": Location,
            "items": Item
        }
        cls = cls_map.get(obj_type)
        if not cls:
            return
        kwargs = {"name": name, "description": description}
        if obj_type == "characters":
            kwargs["is_player"] = data.get("is_player", False)
        obj = cls(**kwargs)
        self.storage.save_object(obj_type, obj)
        objects_dict = getattr(self, obj_type)
        objects_dict[obj.id] = obj
        self._refresh_all_ui()
        self._save_current_session_safe()
        messagebox.showinfo("Создано", f"{cls.__name__} '{name}' создан (ID: {obj.id}).")

    def _handle_delete_object(self, obj_type: str, obj_id: str):
        if not obj_id:
            return
        objects_dict = getattr(self, obj_type)
        obj = objects_dict.get(obj_id)
        if not obj:
            return
        if not messagebox.askyesno("Удаление", f"Удалить {obj_type[:-1]} '{obj.name}'?"):
            return
        self.storage.delete_object(obj_type, obj_id)
        del objects_dict[obj_id]
        profile_attr = f"enabled_{obj_type}"
        enabled_list = getattr(self.current_profile, profile_attr, [])
        if obj_id in enabled_list:
            enabled_list.remove(obj_id)
        self._refresh_all_ui()
        self._save_current_session_safe()
        if obj_type == "narrators":
            self._cleanup_stage_prompts_narrators()
        messagebox.showinfo("Удалено", f"{obj_type[:-1].capitalize()} '{obj.name}' удалён.")

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
        if len(self.memory_summaries) > self.max_memory_summaries:
            self.memory_summaries = self.memory_summaries[-self.max_memory_summaries:]
            self._save_current_session_safe()
        self._log_debug("MEMORY_TRIMMED", f"New max size {self.max_memory_summaries}, summaries: {self.memory_summaries}")

        # Обновляем настройки сжатия
        self.compress_descriptions = self.settings.get("compress_descriptions", False)
        self.max_compressed_desc_length = self.settings.get("max_compressed_desc_length", 500)

        # Настройка показа reasoning
        self.show_thinking = self.settings.get("show_thinking", True)

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
        self._cleanup_stage_prompts_narrators()
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
        self._cleanup_stage_prompts_narrators()
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
        if name in self.prompt_manager.REQUIRED_PROMPTS:
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

    # ---------- Перевод ----------
    def _translate_response_stream(self, original_content: str, response_start_index: str = None):
        system_prompt = self.prompt_manager.load_prompt("translator_system")
        user_prompt = f"Translate to Russian:\n\n{original_content}"
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
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
                        if self.show_thinking:
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

# ---------- SettingsDialog (добавлены настройки сжатия и show_thinking) ----------
class SettingsDialog:
    def __init__(self, parent, current_settings):
        self.top = tk.Toplevel(parent)
        self.top.title("Настройки")
        self.top.geometry("550x800")
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
        self.enable_memory_var = tk.BooleanVar(value=current_settings.get("enable_memory_summary", False))
        ttk.Checkbutton(main_frame, text="Включить краткую память (summary)", variable=self.enable_memory_var).grid(row=9, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Label(main_frame, text="Максимум резюме в памяти:").grid(row=10, column=0, sticky="w", pady=5)
        self.max_memory_summaries = ttk.Spinbox(main_frame, from_=1, to=20, width=10)
        self.max_memory_summaries.delete(0, tk.END)
        self.max_memory_summaries.insert(0, str(current_settings.get("max_memory_summaries", 5)))
        self.max_memory_summaries.grid(row=10, column=1, sticky="w", pady=5)

        # Настройки сжатия описаний
        self.compress_descriptions_var = tk.BooleanVar(value=current_settings.get("compress_descriptions", False))
        ttk.Checkbutton(main_frame, text="Сжимать описания объектов перед передачей модели", variable=self.compress_descriptions_var).grid(row=11, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Label(main_frame, text="Макс. длина сжатого описания (символов):").grid(row=12, column=0, sticky="w", pady=5)
        self.max_compressed_desc_length = ttk.Spinbox(main_frame, from_=100, to=2000, increment=50, width=10)
        self.max_compressed_desc_length.delete(0, tk.END)
        self.max_compressed_desc_length.insert(0, str(current_settings.get("max_compressed_desc_length", 500)))
        self.max_compressed_desc_length.grid(row=12, column=1, sticky="w", pady=5)

        # Настройка показа reasoning
        self.show_thinking_var = tk.BooleanVar(value=current_settings.get("show_thinking", True))
        ttk.Checkbutton(main_frame, text="Показывать мыслительный процесс (reasoning)", variable=self.show_thinking_var).grid(row=13, column=0, columnspan=2, sticky="w", pady=5)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=14, column=0, columnspan=2, pady=20)
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
            "compress_descriptions": self.compress_descriptions_var.get(),
            "max_compressed_desc_length": int(self.max_compressed_desc_length.get()),
            "show_thinking": self.show_thinking_var.get(),
        }
        self.top.destroy()

if __name__ == "__main__":
    app = MainApp()
    app.mainloop()
    