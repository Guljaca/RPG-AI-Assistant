# stage_processor.py
import json
import random
import re
from typing import Dict, List, Optional, Any, Tuple

from models import Character
import time


class UniversalParser:
    """
    Извлекает вызовы функций из текстового ответа модели.
    Поддерживает:
      - function_name([...])
      - function_name(value, value)
      - function_name(param=value)
      - {"name": "fn", "arguments": {...}}
    """

    FUNC_CALL_PATTERN = re.compile(
        r'(?P<func>\w+)\s*\(\s*(?P<args>[^)]*?)\s*\)',
        re.DOTALL | re.IGNORECASE
    )
    JSON_PATTERN = re.compile(r'\{[^{}]*\}')

    @classmethod
    def parse(cls, text: str) -> List[Tuple[str, Any]]:
        if not text:
            return []
        results = []
        for match in cls.FUNC_CALL_PATTERN.finditer(text):
            func_name = match.group('func').strip()
            args_str = match.group('args').strip()
            args = cls._parse_arguments(args_str)
            if args is not None:
                results.append((func_name, args))
        if not results:
            for json_match in cls.JSON_PATTERN.finditer(text):
                try:
                    obj = json.loads(json_match.group())
                    if 'name' in obj and 'arguments' in obj:
                        results.append((obj['name'], obj['arguments']))
                except:
                    continue
        return results

    @classmethod
    def _parse_arguments(cls, args_str: str) -> Optional[Any]:
        args_str = args_str.strip()
        if not args_str:
            return None
        if args_str.startswith('{') and args_str.endswith('}'):
            try:
                return json.loads(args_str)
            except:
                pass
        if args_str.startswith('[') and args_str.endswith(']'):
            try:
                inner = args_str[1:-1].strip()
                if not inner:
                    return []
                items = []
                for item in cls._split_args_preserve_brackets(inner, sep=','):
                    item = item.strip()
                    if item.startswith("'") and item.endswith("'"):
                        items.append(item[1:-1])
                    elif item.startswith('"') and item.endswith('"'):
                        items.append(item[1:-1])
                    elif item.isdigit():
                        items.append(int(item))
                    elif item in ('true', 'True'):
                        items.append(True)
                    elif item in ('false', 'False'):
                        items.append(False)
                    else:
                        items.append(item)
                return items
            except:
                pass
        parts = cls._split_args_preserve_brackets(args_str, sep=',')
        if len(parts) > 1 and not any('=' in p for p in parts):
            result = []
            for p in parts:
                p = p.strip()
                if p.startswith("'") and p.endswith("'"):
                    result.append(p[1:-1])
                elif p.startswith('"') and p.endswith('"'):
                    result.append(p[1:-1])
                elif p.isdigit():
                    result.append(int(p))
                elif p in ('true', 'True'):
                    result.append(True)
                elif p in ('false', 'False'):
                    result.append(False)
                else:
                    result.append(p)
            return result
        result = {}
        for part in parts:
            if '=' not in part:
                continue
            key, value_str = part.split('=', 1)
            key = key.strip()
            value_str = value_str.strip()
            if value_str.startswith("'") and value_str.endswith("'"):
                value = value_str[1:-1]
            elif value_str.startswith('"') and value_str.endswith('"'):
                value = value_str[1:-1]
            elif value_str.isdigit():
                value = int(value_str)
            elif value_str in ('true', 'True'):
                value = True
            elif value_str in ('false', 'False'):
                value = False
            elif value_str.startswith('[') and value_str.endswith(']'):
                inner = value_str[1:-1].strip()
                if inner:
                    value = [cls._parse_single_value(x.strip()) for x in cls._split_args_preserve_brackets(inner, sep=',')]
                else:
                    value = []
            else:
                value = value_str
            result[key] = value
        return result if result else None

    @staticmethod
    def _split_args_preserve_brackets(text: str, sep=',') -> List[str]:
        parts = []
        current = []
        bracket_level = 0
        in_quote = False
        quote_char = None
        for ch in text:
            if ch in ('"', "'") and not in_quote:
                in_quote = True
                quote_char = ch
            elif ch == quote_char and in_quote:
                in_quote = False
                quote_char = None
            elif not in_quote and ch in '([{':
                bracket_level += 1
            elif not in_quote and ch in ')]}':
                bracket_level -= 1
            if not in_quote and bracket_level == 0 and ch == sep:
                parts.append(''.join(current).strip())
                current = []
            else:
                current.append(ch)
        if current:
            parts.append(''.join(current).strip())
        return parts

    @staticmethod
    def _parse_single_value(s: str) -> Any:
        s = s.strip()
        if s.startswith("'") and s.endswith("'"):
            return s[1:-1]
        if s.startswith('"') and s.endswith('"'):
            return s[1:-1]
        if s.isdigit():
            return int(s)
        if s in ('true', 'True'):
            return True
        if s in ('false', 'False'):
            return False
        return s


class StageProcessor:
    """
    Управляет поэтапной генерацией ответа ассистента.
    Все броски генерируются внутри и берутся из очередей.
    Модель НЕ вызывает roll_dice, только получает готовые числа.
    Все вызовы функций извлекаются из текста через UniversalParser.
    """
    # Все возможные стадии (для синхронизации с настройками)
    ALL_STAGES = [
        "stage1_request_descriptions",
        "stage1_create_scene",
        "stage1_truth_check",
        "stage1_player_action",
        "stage1_random_event_determine",
        "stage1_random_event_request_objects",
        "stage1_random_event_details",
        "stage2_npc_action",
        "stage3_final",
        "stage11_validation",
        "stage4_summary",
        "stage10_associative_memory"
    ]

    def __init__(self, main_app):
        self.main_app = main_app
        self.generation_start_time = None
        self.stage = None
        self.last_changed_objects = []
        self.stage_data = {
            "user_message": "",
            "original_user_message": "",
            "descriptions": {},
            "scene_location_id": None,
            "scene_character_ids": [],
            "scene_item_ids": [],
            "scene_summary": "",
            "player_action_dice": None,
            "player_action_desc": "",
            "event_occurrence_dice": None,
            "event_quality_dice": None,
            "event_occurred": False,
            "event_desc": "",
            "event_additional_ids": [],
            "npc_actions": {},
            "current_npc_index": 0,
            "final_response": "",
            "truth_violation": "",
            "scene_generation_retries": 0,
            "random_event_retries": 0,
            "npc_retry_count": 0
        }
        self.stage_retries = {}
        self.dice_queue_d20 = []
        self.dice_queue_d100 = []
        self._refill_dice_queues()

    def _refill_dice_queues(self):
        self.dice_queue_d20 = [random.randint(1, 20) for _ in range(5)]
        self.dice_queue_d100 = [random.randint(1, 100) for _ in range(5)]

    def _pop_dice(self, dice_type: str) -> int:
        if dice_type == 'd20':
            if not self.dice_queue_d20:
                self.dice_queue_d20 = [random.randint(1, 20) for _ in range(5)]
            return self.dice_queue_d20.pop(0)
        elif dice_type == 'd100':
            if not self.dice_queue_d100:
                self.dice_queue_d100 = [random.randint(1, 100) for _ in range(5)]
            return self.dice_queue_d100.pop(0)
        else:
            return random.randint(1, 20)

    def start_generation(self, user_message: str):
        self.generation_start_time = time.time()
        self._refill_dice_queues()
        self.stage_data.update({
            "user_message": user_message,
            "original_user_message": user_message,
            "descriptions": {},
            "scene_location_id": None,
            "scene_character_ids": [],
            "scene_item_ids": [],
            "scene_summary": "",
            "player_action_dice": None,
            "player_action_desc": "",
            "event_occurrence_dice": None,
            "event_quality_dice": None,
            "event_occurred": False,
            "event_desc": "",
            "event_additional_ids": [],
            "npc_actions": {},
            "current_npc_index": 0,
            "final_response": "",
            "truth_violation": "",
            "scene_generation_retries": 0,
            "random_event_retries": 0,
            "npc_retry_count": 0
        })
        self._stage1_request_descriptions()

    # --------------------------------------------------------------------------
    # Вспомогательные методы
    # --------------------------------------------------------------------------
    def _log_debug(self, step: str, content: str = "", error: str = None):
        if self.main_app.current_debug_log_path:
            self.main_app._log_debug(step, content, error)
        if content and len(content) < 500:
            self._display_system(f"[DEBUG] {step}: {content}")
        elif content:
            self._display_system(f"[DEBUG] {step}: {content[:200]}... (обрезано)")

    def _log_full_response(self, stage: str, content: str):
        self._log_debug(f"FULL_RESPONSE_{stage}", f"Content:\n{content}")
        self._display_thinking(f"📨 Ответ модели ({stage}):\n{content[:500]}{'...' if len(content)>500 else ''}")

    def _display_thinking(self, msg: str):
        if hasattr(self.main_app, 'thinking_panel') and self.main_app.thinking_panel:
            self.main_app.thinking_panel.append_text(msg + "\n")
        else:
            self._display_system(f"[THINK] {msg}")

    def _get_object_by_id(self, obj_id: str):
        return self.main_app._get_object_by_id(obj_id)

    def _get_object_description_with_local(self, obj_id: str) -> str:
        return self.main_app.get_description_for_model(obj_id)

    def _send_request(self, messages, callback, extra=None, stage_name: str = None, use_temp: bool = False, show_in_thinking: bool = False):
        self.main_app._send_model_request(
            messages, callback, extra, stage_name, use_temp, show_in_thinking
        )

    def _display_system(self, msg: str):
        self.main_app.center_panel.display_message(msg, "system")

    def _display_error(self, msg: str):
        self.main_app.center_panel.display_message(msg, "error")

    def _display_message(self, msg: str, tag: str = "system"):
        self.main_app.center_panel.display_message(msg, tag)

    def _finish_generation(self):
        total_time = 0
        if self.generation_start_time is not None:
            total_time = time.time() - self.generation_start_time
            self._log_debug("GENERATION_COMPLETED", f"Total time: {total_time:.2f} sec")
            self.generation_start_time = None
        else:
            self._log_debug("GENERATION_COMPLETED")
        
        final_response = self.stage_data.get("final_response", "")
        if final_response:
            # Просто выводим текст, tkinter сам обработает \n как перенос строки
            self.main_app.center_panel.display_message(f"\n{final_response}\n\n", "assistant")
            self.main_app.conversation_history.append({"role": "assistant", "content": final_response})
            self.main_app._finalize_generation_memory_turn()
            self._save_current_session()
        
        if total_time:
            self._display_system(f"✅ Генерация завершена за {total_time:.2f} секунд.\n")
        
        self.main_app.is_generating = False
        self.main_app.center_panel.set_input_state("normal")
        self.main_app.center_panel.update_translation_button_state()
        self.main_app.current_debug_log_path = None
        self.main_app.display_generation_memory_summary()

    def _save_current_session(self):
        self.main_app._save_current_session_safe()

    def _try_parse_tool_calls_from_text(self, content: str, expected_func_names: List[str] = None) -> List[Dict]:
        parsed = UniversalParser.parse(content)
        tool_calls = []
        for func_name, args in parsed:
            if expected_func_names and func_name not in expected_func_names:
                continue
            tool_calls.append({
                "id": f"parsed_{func_name}_{random.randint(1000,9999)}",
                "type": "function",
                "function": {
                    "name": func_name,
                    "arguments": json.dumps(args, ensure_ascii=False)
                }
            })
        return tool_calls

    def _is_model_rejection(self, text: str) -> bool:
        if not text:
            return False
        rejection_phrases = [
            "не подходит", "не могу подтвердить", "не соответствует", "не вижу смысла",
            "отклоняю", "не удалось определить", "не вижу", "не подходящая сцена",
            "не могу согласиться", "не подтверждаю", "не вижу объектов", "не подходит для сцены"
        ]
        return any(phrase in text.lower() for phrase in rejection_phrases)

    def _get_retry_limit(self, stage_name: str) -> int:
        return self.main_app.stage_retry_limits.get(stage_name, 2)

    # --------------------------------------------------------------------------
    # Синхронное получение описаний объектов
    # --------------------------------------------------------------------------
    def _fetch_descriptions_sync(self, obj_ids: List[str]):
        for obj_id in obj_ids:
            self._display_system(f"📦 Получение описания для {obj_id}...\n")
            try:
                desc = self._get_object_description_with_local(obj_id)
                self.stage_data["descriptions"][obj_id] = desc
                self._display_system(f"✅ Описание {obj_id} получено.\n")
            except Exception as e:
                self._display_error(f"❌ Ошибка получения описания {obj_id}: {e}\n")
                self.stage_data["descriptions"][obj_id] = f"Ошибка: {e}"
        self._display_system("✅ Все описания объектов получены.\n")

    # --------------------------------------------------------------------------
    # СТАДИЯ 1.1: запрос описаний объектов (кандидатов)
    # --------------------------------------------------------------------------
    def _stage1_request_descriptions(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage1_request_descriptions", True):
            self._log_debug("STAGE1_SKIPPED", "Stage1 disabled")
            self._stage1_create_scene()
            return

        self._log_debug(f"=== STAGE1.1: request_descriptions (attempt {retry_count+1}) ===")
        self._display_system(f"🔍 Этап 1.1/10: Определение необходимых объектов (попытка {retry_count+1})...\n")

        if retry_count > 0:
            self.stage_data["descriptions"] = {}

        objects_text = []
        for lid in self.main_app.current_profile.enabled_locations:
            loc = self.main_app.locations.get(lid)
            if loc:
                assoc = self.main_app.get_associative_memory_for_object(lid)
                assoc_str = f" ({assoc})" if assoc else ""
                objects_text.append(f"Локация: {lid} - {loc.name}{assoc_str}")
        for cid in self.main_app.current_profile.enabled_characters:
            char = self.main_app.characters.get(cid)
            if char:
                assoc = self.main_app.get_associative_memory_for_object(cid)
                assoc_str = f" ({assoc})" if assoc else ""
                player_tag = ' (ИГРОК)' if char.is_player else ''
                objects_text.append(f"Персонаж: {cid} - {char.name}{player_tag}{assoc_str}")
        for iid in self.main_app.current_profile.enabled_items:
            item = self.main_app.items.get(iid)
            if item:
                assoc = self.main_app.get_associative_memory_for_object(iid)
                assoc_str = f" ({assoc})" if assoc else ""
                objects_text.append(f"Предмет: {iid} - {item.name}{assoc_str}")
        available = "\n".join(objects_text) if objects_text else "Нет доступных объектов."

        # Получаем лимиты из настроек
        max_locs = self.main_app.max_locations_per_scene
        max_chars = self.main_app.max_characters_per_scene
        max_items = self.main_app.max_items_per_scene

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_request_descriptions")
        if not prompt_template:
            raise RuntimeError("Промт 'stage1_request_descriptions' не загружен. Проверьте файлы промтов.")
        main_prompt = prompt_template.format(
            user_message=self.stage_data["user_message"],
            available_objects=available,
            max_locations=max_locs,
            max_characters=max_chars,
            max_items=max_items
        )
        main_prompt += "\n\n⚠️ Ты должен ответить ТОЛЬКО вызовом send_object_info с массивом ID объектов. Пример: send_object_info(['l1','c2','c3']). Никакого другого текста."

        messages = [
            {"role": "user", "content": f"Сообщение игрока: {self.stage_data['user_message']}"},
            {"role": "system", "content": main_prompt}
        ]

        self._send_request(
            messages,
            lambda content, extra: self._after_stage1_request_descriptions(content, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_request_descriptions",
            show_in_thinking=True
        )

    def _after_stage1_request_descriptions(self, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_full_response("stage1_request_descriptions", content)

        tool_calls = self._try_parse_tool_calls_from_text(content, expected_func_names=["send_object_info"])
        if len(tool_calls) > 1:
            self._log_debug("WARNING", f"Найдено несколько вызовов send_object_info ({len(tool_calls)}), беру последний")
        send_call = tool_calls[-1] if tool_calls else None

        if send_call:
            try:
                args = json.loads(send_call["function"]["arguments"])
                object_ids = None
                if isinstance(args, list):
                    object_ids = args
                elif "object_ids" in args:
                    object_ids = args["object_ids"]
                elif "ids" in args:
                    object_ids = args["ids"]
                elif len(args) == 1 and isinstance(list(args.values())[0], list):
                    object_ids = list(args.values())[0]

                if object_ids is not None and isinstance(object_ids, list) and object_ids:
                    self._display_system(f"📦 Запрошены объекты: {object_ids}\n")
                    self._fetch_descriptions_sync(object_ids)
                    self._stage1_create_scene()
                    return
                else:
                    self._display_error("⚠️ send_object_info вызван без корректного списка object_ids.\n")
            except Exception as e:
                self._log_debug("ERROR", f"send_object_info parse error: {e}")

        limit = self._get_retry_limit("stage1_request_descriptions")
        if retry_count < limit:
            self._display_error(f"⚠️ Модель не вызвала send_object_info. Повтор ({retry_count+1}/{limit})...\n")
            self._stage1_request_descriptions(retry_count+1)
        else:
            self._display_system("⚠️ Модель не запросила объекты. Создаём сцену по умолчанию.\n")
            self._create_default_scene()

    def _create_default_scene(self):
        location_id = None
        if self.main_app.current_profile.enabled_locations:
            location_id = self.main_app.current_profile.enabled_locations[0]
        character_ids = [cid for cid in self.main_app.current_profile.enabled_characters
                        if not self.main_app.characters.get(cid, Character(is_player=False)).is_player]
        item_ids = self.main_app.current_profile.enabled_items[:3]

        self.stage_data["scene_location_id"] = location_id
        self.stage_data["scene_character_ids"] = character_ids
        self.stage_data["scene_item_ids"] = item_ids

        all_ids = []
        if location_id:
            all_ids.append(location_id)
        all_ids.extend(character_ids)
        all_ids.extend(item_ids)

        scene_parts = []
        if location_id:
            loc = self.main_app.locations.get(location_id)
            loc_name = loc.name if loc else location_id
            scene_parts.append(f"Локация: {loc_name} (ID: {location_id})")
        if character_ids:
            char_names = []
            for cid in character_ids:
                char = self.main_app.characters.get(cid)
                char_names.append(f"{char.name} (ID: {cid})" if char else cid)
            scene_parts.append(f"Персонажи: {', '.join(char_names)}")
        if item_ids:
            item_names = []
            for iid in item_ids:
                item = self.main_app.items.get(iid)
                item_names.append(f"{item.name} (ID: {iid})" if item else iid)
            scene_parts.append(f"Предметы: {', '.join(item_names)}")
        summary = "\n".join(scene_parts)
        self.stage_data["scene_summary"] = summary
        self._display_system(f"🔄 Сцена создана автоматически:\n{summary}\n")
        if all_ids:
            self._fetch_descriptions_sync(all_ids)
        self._stage1_truth_check()

    # --------------------------------------------------------------------------
    # СТАДИЯ 1.2: создание сцены на основе полученных описаний
    # --------------------------------------------------------------------------
    def _stage1_create_scene(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage1_create_scene", True):
            self._log_debug("STAGE1_CREATE_SCENE_SKIPPED", "Stage1_create_scene disabled")
            self._stage1_truth_check()
            return

        self._log_debug(f"=== STAGE1.2: create_scene (attempt {retry_count+1}) ===")
        self._display_system(f"🎬 Этап 1.2/10: Создание сцены (попытка {retry_count+1})...\n")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_create_scene")
        if not prompt_template:
            raise RuntimeError("Промт 'stage1_create_scene' не загружен. Проверьте файлы промтов.")
        main_prompt = prompt_template.format(
            user_message=self.stage_data["user_message"],
            descriptions=descriptions_text
        )
        main_prompt += "\n\n⚠️ Ты должен ответить ТОЛЬКО вызовом confirm_scene с одним аргументом-списком: confirm_scene([location_id, character_ids, item_ids]). Пример: confirm_scene(['l1', ['c2','c3'], []]). Никакого другого текста."

        messages = [
            {"role": "user", "content": f"Сообщение игрока: {self.stage_data['user_message']}"},
            {"role": "system", "content": main_prompt}
        ]

        self._send_request(
            messages,
            lambda content, extra: self._after_stage1_create_scene(content, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_create_scene",
            show_in_thinking=True
        )

    def _after_stage1_create_scene(self, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_full_response("stage1_create_scene", content)

        tool_calls = self._try_parse_tool_calls_from_text(content, expected_func_names=["confirm_scene"])
        if len(tool_calls) > 1:
            self._log_debug("WARNING", f"Найдено несколько вызовов confirm_scene ({len(tool_calls)}), беру последний")
        confirm_call = tool_calls[-1] if tool_calls else None

        if confirm_call:
            try:
                args = json.loads(confirm_call["function"]["arguments"])
                location_id = None
                character_ids = []
                item_ids = []

                if isinstance(args, list) and len(args) == 1 and isinstance(args[0], list) and len(args[0]) >= 3:
                    inner = args[0]
                    location_id = inner[0] if isinstance(inner[0], str) else None
                    character_ids = inner[1] if isinstance(inner[1], list) else []
                    item_ids = inner[2] if isinstance(inner[2], list) else []
                elif isinstance(args, list) and len(args) >= 3:
                    location_id = args[0] if isinstance(args[0], str) else None
                    character_ids = args[1] if isinstance(args[1], list) else []
                    item_ids = args[2] if isinstance(args[2], list) else []
                elif isinstance(args, dict):
                    location_id = args.get("location_id")
                    character_ids = args.get("character_ids", [])
                    item_ids = args.get("item_ids", [])
                else:
                    raise ValueError("Unknown args format")

                user_msg_lower = self.stage_data.get("user_message", "").lower()
                for oid, desc in self.stage_data["descriptions"].items():
                    obj = self.main_app._get_object_by_id(oid)
                    if obj and hasattr(obj, 'name') and not getattr(obj, 'is_player', False):
                        name_lower = obj.name.lower()
                        if name_lower.split()[0] in user_msg_lower or user_msg_lower.startswith(name_lower.split()[0]):
                            if oid not in character_ids:
                                character_ids.append(oid)

                self.stage_data["scene_location_id"] = location_id
                self.stage_data["scene_character_ids"] = character_ids
                self.stage_data["scene_item_ids"] = item_ids

                scene_parts = []
                if self.stage_data["scene_location_id"]:
                    loc = self.main_app.locations.get(self.stage_data["scene_location_id"])
                    loc_name = loc.name if loc else self.stage_data["scene_location_id"]
                    scene_parts.append(f"Локация: {loc_name} (ID: {self.stage_data['scene_location_id']})")
                if self.stage_data["scene_character_ids"]:
                    char_names = []
                    for cid in self.stage_data["scene_character_ids"]:
                        char = self.main_app.characters.get(cid)
                        char_names.append(f"{char.name} (ID: {cid})" if char else cid)
                    scene_parts.append(f"Персонажи: {', '.join(char_names)}")
                if self.stage_data["scene_item_ids"]:
                    item_names = []
                    for iid in self.stage_data["scene_item_ids"]:
                        item = self.main_app.items.get(iid)
                        item_names.append(f"{item.name} (ID: {iid})" if item else iid)
                    scene_parts.append(f"Предметы: {', '.join(item_names)}")
                summary = "\n".join(scene_parts)
                self.stage_data["scene_summary"] = summary
                self._display_system(f"✅ Сцена создана:\n{summary}\n")
                self._stage1_truth_check()
                return
            except Exception as e:
                self._log_debug("ERROR", f"confirm_scene parse error: {e}")

        limit = self._get_retry_limit("stage1_create_scene")
        if retry_count < limit:
            self._display_error(f"⚠️ Модель не вызвала confirm_scene. Повтор ({retry_count+1}/{limit})...\n")
            self._stage1_create_scene(retry_count+1)
        else:
            self._display_system("⚠️ Не удалось получить confirm_scene. Создаём сцену по умолчанию.\n")
            self._create_default_scene()

    # --------------------------------------------------------------------------
    # СТАДИЯ 2: проверка правдивости
    # --------------------------------------------------------------------------
    def _stage1_truth_check(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage1_truth_check", True):
            self._log_debug("STAGE2_SKIPPED", "Stage2 (truth_check) disabled")
            self._stage1_player_action()
            return

        self._log_debug(f"=== STAGE2: truth_check (attempt {retry_count+1}) ===")
        self._display_system(f"🔍 Этап 2/10: Проверка правдивости (попытка {retry_count+1})...\n")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_truth_check")
        if not prompt_template:
            raise RuntimeError("Промт 'stage1_truth_check' не загружен.")
        main_prompt = prompt_template.format(
            user_message=self.stage_data["user_message"],
            descriptions=descriptions_text
        )
        main_prompt += "\n\n⚠️ ТОЛЬКО вызов report_truth_check с одним аргументом-списком: report_truth_check([violation, edited_message]). Пример: report_truth_check(['', ''])"

        messages = [
            {"role": "user", "content": f"Проверь сообщение: {self.stage_data['user_message']}"},
            {"role": "system", "content": main_prompt}
        ]

        self._send_request(
            messages,
            lambda content, extra: self._after_stage1_truth_check(content, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_truth_check",
            show_in_thinking=True
        )

    def _after_stage1_truth_check(self, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_full_response("stage1_truth_check", content)

        tool_calls = self._try_parse_tool_calls_from_text(content, ["report_truth_check"])
        if len(tool_calls) > 1:
            self._log_debug("WARNING", f"Найдено несколько вызовов report_truth_check ({len(tool_calls)}), беру последний")
        report_call = tool_calls[-1] if tool_calls else None

        if not report_call:
            limit = self._get_retry_limit("stage1_truth_check")
            if retry_count < limit:
                self._display_error(f"⚠️ Модель не вызвала report_truth_check. Повтор ({retry_count+1}/{limit})...\n")
                self._stage1_truth_check(retry_count+1)
                return
            else:
                self._display_system("⚠️ Пропускаем проверку правдивости.\n")
                self.stage_data["truth_violation"] = ""
                self._stage1_player_action()
                return

        try:
            args = json.loads(report_call["function"]["arguments"])
            violation = ""
            edited = ""

            if isinstance(args, list) and len(args) == 1 and isinstance(args[0], list) and len(args[0]) >= 2:
                violation = args[0][0] if isinstance(args[0][0], str) else str(args[0][0])
                edited = args[0][1] if isinstance(args[0][1], str) else str(args[0][1])
            elif isinstance(args, list) and len(args) >= 2:
                violation = args[0] if isinstance(args[0], str) else str(args[0])
                edited = args[1] if isinstance(args[1], str) else str(args[1])
            elif isinstance(args, dict):
                violation = args.get("violation", "")
                edited = args.get("edited_message", "")

            self.stage_data["truth_violation"] = violation
            if edited:
                self.stage_data["user_message"] = edited
                self._display_system(f"✏️ Сообщение изменено: {edited}\n")
            else:
                self._display_system("✅ Нарушений не найдено.\n")

            self._stage1_player_action()

        except Exception as e:
            self._log_debug("ERROR", f"truth_check parse error: {e}")
            limit = self._get_retry_limit("stage1_truth_check")
            if retry_count < limit:
                self._stage1_truth_check(retry_count+1)
            else:
                self.stage_data["truth_violation"] = ""
                self._stage1_player_action()

    # --------------------------------------------------------------------------
    # СТАДИЯ 3: действие игрока
    # --------------------------------------------------------------------------
    def _stage1_player_action(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage1_player_action", True):
            self._stage1_random_event_determine()
            return

        self._log_debug(f"=== STAGE3: player_action (attempt {retry_count+1}) ===")
        self._display_system(f"🎲 Этап 3/10: Действие игрока (попытка {retry_count+1})...\n")

        # Сохраняем бросок при первой попытке
        if retry_count == 0:
            dice_value = self._pop_dice('d20')
            self.stage_data["player_action_dice"] = dice_value
        else:
            dice_value = self.stage_data.get("player_action_dice")
            if dice_value is None:
                dice_value = self._pop_dice('d20')
                self.stage_data["player_action_dice"] = dice_value

        self._display_system(f"🎲 Бросок d20: {dice_value}\n")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        dice_rules = self.main_app.prompt_manager.get_prompt_content("dice_rules")
        violation_text = self.stage_data.get("truth_violation", "")
        violation_section = f"\nНарушение: {violation_text}\n" if violation_text else ""

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_player_action")
        if not prompt_template:
            raise RuntimeError("Промт 'stage1_player_action' не загружен.")
        main_prompt = prompt_template.format(
            user_message=self.stage_data["user_message"],
            descriptions=descriptions_text,
            dice_rules=dice_rules,
            truth_violation=violation_section,
            dice_value=dice_value
        )
        main_prompt += f"\n\n⚠️ Вызови act с одним аргументом-списком: act([{dice_value}, 'твоё описание'])."

        messages = [
            {"role": "user", "content": f"Игрок: {self.stage_data['user_message']}"},
            {"role": "system", "content": main_prompt}
        ]

        self._send_request(
            messages,
            lambda content, extra: self._after_stage1_player_action(content, extra),
            extra={"retry_count": retry_count, "expected_dice": dice_value},
            stage_name="stage1_player_action",
            show_in_thinking=True
        )

    def _after_stage1_player_action(self, content, extra):
        retry_count = extra.get("retry_count", 0)
        expected_dice = extra.get("expected_dice")
        
        # Исправляем частую ошибку: act([10, '...']] → act([10, '...'])
        import re
        content = re.sub(r'\]\s*\]$', ']', content.strip())
        content = re.sub(r'\]\]', ']', content)
        self._log_full_response("stage1_player_action", content)

        tool_calls = self._try_parse_tool_calls_from_text(content, expected_func_names=["act"])
        if not tool_calls:
            limit = self._get_retry_limit("stage1_player_action")
            if retry_count < limit:
                self._display_error(f"⚠️ Модель не вызвала act. Повтор ({retry_count+1}/{limit})...\n")
                self._stage1_player_action(retry_count+1)
                return
            else:
                self.stage_data["player_action_desc"] = content.strip()[:500] if content else "Действие выполнено."
                self._display_system(f"⚠️ Использую текст как описание: {self.stage_data['player_action_desc'][:100]}...\n")
                self._stage1_random_event_determine()
                return

        if len(tool_calls) > 1:
            self._log_debug("WARNING", f"Найдено несколько вызовов act ({len(tool_calls)}), беру последний")
        act_call = tool_calls[-1]
        try:
            args = json.loads(act_call["function"]["arguments"])
            description = ""

            if isinstance(args, list) and len(args) == 1 and isinstance(args[0], list) and len(args[0]) >= 2:
                description = args[0][1] if isinstance(args[0][1], str) else str(args[0][1])
            elif isinstance(args, list) and len(args) >= 2:
                description = args[1] if isinstance(args[1], str) else str(args[1])
            elif isinstance(args, dict):
                description = args.get("description", "")
            else:
                description = str(args)

            self.stage_data["player_action_desc"] = description or "Действие выполнено."
            self._display_system(f"✍️ Результат: {description[:100]}...\n")
            self._stage1_random_event_determine()
        except Exception as e:
            self._log_debug("ERROR", f"act parsing error: {e}")
            limit = self._get_retry_limit("stage1_player_action")
            if retry_count < limit:
                self._stage1_player_action(retry_count+1)
            else:
                self.stage_data["player_action_desc"] = "Действие выполнено."
                self._stage1_random_event_determine()

    # --------------------------------------------------------------------------
    # СТАДИЯ 4: определение случайного события (произошло ли)
    # --------------------------------------------------------------------------
    def _stage1_random_event_determine(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage1_random_event_determine", True):
            self._log_debug("STAGE4_SKIPPED", "Stage4 (random_event_determine) disabled")
            self._stage2_npc_action()
            return

        self._log_debug(f"=== STAGE4: random_event (determine) (attempt {retry_count+1}) ===")
        self._display_system(f"🎲 Этап 4/10: Определение случайного события (попытка {retry_count+1})...\n")

        dice_value = self._pop_dice('d100')
        self.stage_data["event_occurrence_dice"] = dice_value
        self._display_system(f"🎲 Бросок d100: {dice_value}\n")

        event_chance = getattr(self.main_app, 'random_event_chance', 30)

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        player_action = self.stage_data["player_action_desc"]

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_random_event")
        if not prompt_template:
            raise RuntimeError("Промт 'stage1_random_event' не загружен.")
        main_prompt = prompt_template.format(
            descriptions=descriptions_text,
            player_action=player_action,
            dice_value=dice_value,
            event_chance=event_chance
        )
        main_prompt += "\n\n⚠️ Вызови report_random_event с одним аргументом-списком: report_random_event([dice_value, 'yes' или 'no', ''])."

        messages = [
            {"role": "user", "content": f"Действие игрока: {player_action}"},
            {"role": "system", "content": main_prompt}
        ]

        self._send_request(
            messages,
            lambda content, extra: self._after_stage1_random_event_determine(content, extra),
            extra={"retry_count": retry_count, "dice_value": dice_value, "event_chance": event_chance},
            stage_name="stage1_random_event_determine",
            show_in_thinking=True
        )

    def _after_stage1_random_event_determine(self, content, extra):
        retry_count = extra.get("retry_count", 0)
        expected_dice = extra.get("dice_value")
        self._log_full_response("stage1_random_event_determine", content)

        tool_calls = self._try_parse_tool_calls_from_text(content, ["report_random_event"])
        if not tool_calls:
            limit = self._get_retry_limit("stage1_random_event_determine")
            if retry_count < limit:
                self._display_error(f"⚠️ Модель не вызвала report_random_event. Повтор ({retry_count+1}/{limit})...\n")
                self._stage1_random_event_determine(retry_count+1)
                return
            else:
                self._display_system("⚠️ Модель не определила событие. Считаем, что событие не произошло.\n")
                self.stage_data["event_occurred"] = False
                self._stage2_npc_action()
                return

        if len(tool_calls) > 1:
            self._log_debug("WARNING", f"Найдено несколько вызовов report_random_event ({len(tool_calls)}), беру последний")
        try:
            args = json.loads(tool_calls[-1]["function"]["arguments"])
            event_occurred = False

            if isinstance(args, list) and len(args) == 1 and isinstance(args[0], list) and len(args[0]) >= 2:
                occurred_str = str(args[0][1]).lower()
                event_occurred = occurred_str in ('yes', 'true', '1')
            elif isinstance(args, list) and len(args) >= 2:
                occurred_str = str(args[1]).lower()
                event_occurred = occurred_str in ('yes', 'true', '1')
            elif isinstance(args, dict):
                occurred_val = args.get("event_occurred")
                if isinstance(occurred_val, str):
                    event_occurred = occurred_val.lower() in ('yes', 'true', '1')
                else:
                    event_occurred = bool(occurred_val)

            self.stage_data["event_occurred"] = event_occurred
            self._display_system(f"✨ Событие: {'произошло' if event_occurred else 'НЕ произошло'} (d100={expected_dice})\n")

            if event_occurred:
                self._stage1_random_event_request_objects()
            else:
                self._stage2_npc_action()
        except Exception as e:
            self._log_debug("ERROR", f"report_random_event parse error: {e}")
            limit = self._get_retry_limit("stage1_random_event_determine")
            if retry_count < limit:
                self._stage1_random_event_determine(retry_count + 1)
            else:
                self.stage_data["event_occurred"] = False
                self._stage2_npc_action()

    # --------------------------------------------------------------------------
    # СТАДИЯ 5.1: запрос недостающих объектов для случайного события
    # --------------------------------------------------------------------------
    def _stage1_random_event_request_objects(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage1_random_event_request_objects", True):
            self._log_debug("STAGE5.1_SKIPPED", "Stage5.1 (request_objects) disabled")
            self._stage1_random_event_details()
            return

        self._log_debug(f"=== STAGE5.1: request objects for event (attempt {retry_count+1}) ===")
        self._display_system(f"📦 Этап 5.1/10: Запрос объектов для события (попытка {retry_count+1})...\n")

        objects_text = []
        for lid in self.main_app.current_profile.enabled_locations:
            loc = self.main_app.locations.get(lid)
            if loc:
                assoc = self.main_app.get_associative_memory_for_object(lid)
                assoc_str = f" ({assoc})" if assoc else ""
                objects_text.append(f"Локация: {lid} - {loc.name}{assoc_str}")
        for cid in self.main_app.current_profile.enabled_characters:
            char = self.main_app.characters.get(cid)
            if char:
                assoc = self.main_app.get_associative_memory_for_object(cid)
                assoc_str = f" ({assoc})" if assoc else ""
                player_tag = ' (ИГРОК)' if char.is_player else ''
                objects_text.append(f"Персонаж: {cid} - {char.name}{player_tag}{assoc_str}")
        for iid in self.main_app.current_profile.enabled_items:
            item = self.main_app.items.get(iid)
            if item:
                assoc = self.main_app.get_associative_memory_for_object(iid)
                assoc_str = f" ({assoc})" if assoc else ""
                objects_text.append(f"Предмет: {iid} - {item.name}{assoc_str}")
        available = "\n".join(objects_text) if objects_text else "Нет доступных объектов."

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        player_action = self.stage_data["player_action_desc"]
        event_dice = self.stage_data["event_occurrence_dice"]

        max_locs = self.main_app.max_locations_per_scene
        max_chars = self.main_app.max_characters_per_scene
        max_items = self.main_app.max_items_per_scene

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_random_event_request_objects")
        if not prompt_template:
            raise RuntimeError("Промт 'stage1_random_event_request_objects' не загружен.")
        main_prompt = prompt_template.format(
            event_dice=event_dice,
            descriptions=descriptions_text,
            player_action=player_action,
            available_objects=available,
            max_locations=max_locs,
            max_characters=max_chars,
            max_items=max_items
        )
        main_prompt += "\n\n⚠️ Если не хватает объектов, вызови send_object_info с массивом ID. Если хватает, ответь 'OK'."

        messages = [
            {"role": "user", "content": "Определи, нужны ли дополнительные объекты для описания события."},
            {"role": "system", "content": main_prompt}
        ]

        self._send_request(
            messages,
            lambda content, extra: self._after_stage1_random_event_request_objects(content, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_random_event_request_objects",
            show_in_thinking=True
        )

    def _after_stage1_random_event_request_objects(self, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_full_response("stage1_random_event_request_objects", content)

        tool_calls = self._try_parse_tool_calls_from_text(content, expected_func_names=["send_object_info"])
        if len(tool_calls) > 1:
            self._log_debug("WARNING", f"Найдено несколько вызовов send_object_info ({len(tool_calls)}), беру последний")
        send_call = tool_calls[-1] if tool_calls else None

        if send_call:
            try:
                args = json.loads(send_call["function"]["arguments"])
                object_ids = None
                if isinstance(args, list):
                    object_ids = args
                elif "object_ids" in args:
                    object_ids = args["object_ids"]
                elif "ids" in args:
                    object_ids = args["ids"]
                elif len(args) == 1 and isinstance(list(args.values())[0], list):
                    object_ids = list(args.values())[0]

                if object_ids is not None and isinstance(object_ids, list) and object_ids:
                    self._display_system(f"📦 Запрошены дополнительные объекты для события: {object_ids}\n")
                    self.stage_data["event_additional_ids"] = object_ids
                    self._fetch_descriptions_sync(object_ids)
                    self._stage1_random_event_details()
                    return
                else:
                    self._display_error("⚠️ send_object_info вызван без корректного списка object_ids.\n")
            except Exception as e:
                self._log_debug("ERROR", f"send_object_info parse error: {e}")

        self._display_system("✅ Дополнительные объекты не требуются.\n")
        self._stage1_random_event_details()

    # --------------------------------------------------------------------------
    # СТАДИЯ 5.2: описание случайного события (с броском качества d20)
    # --------------------------------------------------------------------------
    def _stage1_random_event_details(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage1_random_event_details", True):
            self._log_debug("STAGE5.2_SKIPPED", "Stage5.2 (event_details) disabled")
            self._stage2_npc_action()
            return

        self._log_debug(f"=== STAGE5.2: event details (attempt {retry_count+1}) ===")
        self._display_system(f"✨ Этап 5.2/10: Описание события (попытка {retry_count+1})...\n")

        if retry_count == 0:
            quality_dice = self._pop_dice('d20')
            self.stage_data["event_quality_dice"] = quality_dice
        else:
            quality_dice = self.stage_data.get("event_quality_dice", self._pop_dice('d20'))
        self._display_system(f"🎲 Качество события d20: {quality_dice}\n")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_random_event_continue")
        if not prompt_template:
            raise RuntimeError("Промт 'stage1_random_event_continue' не загружен.")
        main_prompt = prompt_template.format(
            descriptions=descriptions_text,
            player_action=self.stage_data["player_action_desc"],
            dice_value=quality_dice
        )
        main_prompt += "\n\n⚠️ Вызови report_random_event с одним аргументом-списком: report_random_event([dice_value, 'yes', 'твоё описание'])"

        messages = [
            {"role": "user", "content": "Опиши событие."},
            {"role": "system", "content": main_prompt}
        ]

        self._send_request(
            messages,
            lambda content, extra: self._after_stage1_random_event_details(content, extra),
            extra={"retry_count": retry_count, "dice_value": quality_dice},
            stage_name="stage1_random_event_details",
            show_in_thinking=True
        )

    def _after_stage1_random_event_details(self, content, extra):
        retry_count = extra.get("retry_count", 0)
        expected_dice = extra.get("dice_value")
        self._log_full_response("stage1_random_event_details", content)

        tool_calls = self._try_parse_tool_calls_from_text(content, ["report_random_event"])
        if len(tool_calls) > 1:
            self._log_debug("WARNING", f"Найдено несколько вызовов report_random_event ({len(tool_calls)}), беру последний")
        report_call = tool_calls[-1] if tool_calls else None

        if report_call:
            try:
                args = json.loads(report_call["function"]["arguments"])
                description = ""
                if isinstance(args, list) and len(args) == 1 and isinstance(args[0], list) and len(args[0]) >= 3:
                    description = args[0][2] if isinstance(args[0][2], str) else str(args[0][2])
                elif isinstance(args, list) and len(args) >= 3:
                    description = args[2] if isinstance(args[2], str) else str(args[2])
                elif isinstance(args, dict):
                    description = args.get("description", "")
                self.stage_data["event_desc"] = description
                self._display_system(f"✨ Событие: {description[:100]}...\n")
                self._stage2_npc_action()
                return
            except Exception as e:
                self._log_debug("ERROR", f"event parse error: {e}")

        if content and len(content.strip()) > 5:
            self.stage_data["event_desc"] = content.strip()[:300]
            self._display_system(f"⚠️ Событие (из текста без вызова): {self.stage_data['event_desc'][:100]}...\n")
            self._stage2_npc_action()
            return

        limit = self._get_retry_limit("stage1_random_event_details")
        if retry_count < limit:
            self._display_error(f"⚠️ Модель не описала событие. Повтор ({retry_count+1}/{limit})...\n")
            self._stage1_random_event_details(retry_count+1)
        else:
            self.stage_data["event_desc"] = "Произошло что-то неожиданное."
            self._display_system("⚠️ Событие сгенерировано автоматически.\n")
            self._stage2_npc_action()

    # --------------------------------------------------------------------------
    # СТАДИЯ 6: обработка NPC (действия)
    # --------------------------------------------------------------------------
    def _stage2_npc_action(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage2_npc_action", True):
            self._log_debug("STAGE6_SKIPPED", "Stage6 (NPC) disabled")
            self._stage3_final()
            return

        # Защита от бесконечной рекурсии
        if retry_count > 50:
            self._display_error("❌ Критическая ошибка: слишком много попыток обработки NPC. Принудительный выход.\n")
            self._stage3_final()
            return

        self._log_debug(f"=== STAGE6: NPCs (attempt {retry_count+1}) ===")
        self._display_system(f"🎭 Этап 6/10: Обработка NPC (попытка {retry_count+1})...\n")

        # Получаем список NPC (исключая игрока)
        all_chars = self.stage_data.get("scene_character_ids", [])
        npc_ids = []
        for cid in all_chars:
            char = self.main_app.characters.get(cid)
            if char and not char.is_player:
                npc_ids.append(cid)

        # Если NPC нет — сразу переходим к финальному этапу
        if not npc_ids:
            self._display_system("Нет NPC.\n")
            self._stage3_final()
            return

        # Инициализация данных, если первый вызов
        if not self.stage_data.get("npc_actions"):
            self.stage_data["npc_actions"] = {}
            self.stage_data["current_npc_index"] = 0

        # Проверка, что все NPC обработаны
        if self.stage_data["current_npc_index"] >= len(npc_ids):
            self._display_system("✅ Все NPC обработаны.\n")
            self._stage3_final()
            return

        npc_id = npc_ids[self.stage_data["current_npc_index"]]
        npc = self.main_app.characters.get(npc_id)
        if not npc:
            self._display_error(f"⚠️ NPC с ID {npc_id} не найден, пропускаем.\n")
            self.stage_data["current_npc_index"] += 1
            self._stage2_npc_action(0)
            return

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        player_action = self.stage_data["player_action_desc"]
        event_desc = self.stage_data["event_desc"] if self.stage_data["event_occurred"] else "Нет события"

        previous = []
        for cid, act in self.stage_data["npc_actions"].items():
            ch = self.main_app.characters.get(cid)
            if ch:
                previous.append(f"{ch.name}: {act}")
        previous_text = "\n".join(previous) if previous else "Нет"

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage2_npc_action")
        if not prompt_template:
            raise RuntimeError("Промт 'stage2_npc_action' не загружен.")
        main_prompt = prompt_template.format(
            npc_name=npc.name,
            npc_id=npc_id,
            descriptions=descriptions_text,
            player_action=player_action,
            event_description=event_desc,
            previous_actions=previous_text
        )
        main_prompt += "\n\n⚠️ Формат: Думает: ... Планирует: ..."
        messages = [{"role": "user", "content": main_prompt}]

        self._send_request(
            messages,
            lambda content, extra: self._after_stage2_npc_action(content, extra),
            extra={"npc_id": npc_id, "npc_name": npc.name, "retry_count": retry_count},
            stage_name="stage2_npc_action",
            show_in_thinking=True
        )

    def _after_stage2_npc_action(self, content, extra):
        npc_id = extra["npc_id"]
        npc_name = extra.get("npc_name", "NPC")
        retry_count = extra.get("retry_count", 0)
        self._log_full_response(f"stage2_npc_action_{npc_id}", content)

        intent = None
        if content:
            lines = content.strip().split('\n')
            thoughts = ""
            planned = ""
            for line in lines:
                lower = line.lower()
                if "думает" in lower:
                    thoughts = line.split(':', 1)[-1].strip() if ':' in line else line
                elif "планирует" in lower:
                    planned = line.split(':', 1)[-1].strip() if ':' in line else line
            if thoughts or planned:
                intent = f"{thoughts} {planned}".strip()
            else:
                intent = content[:200].strip()

        if not intent:
            limit = self._get_retry_limit("stage2_npc_action")
            if retry_count < limit:
                self._display_error(f"⚠️ Повтор для {npc_name}...\n")
                self._stage2_npc_action(retry_count + 1)
                return
            else:
                intent = f"{npc_name} наблюдает."

        self.stage_data["npc_actions"][npc_id] = intent
        self._display_system(f"✍️ {npc_name}: {intent[:100]}\n")
        # Переходим к следующему NPC, сбрасывая счётчик повторений
        self.stage_data["current_npc_index"] += 1
        self._stage2_npc_action(0)

    # --------------------------------------------------------------------------
    # СТАДИЯ 7: финальный рассказ
    # --------------------------------------------------------------------------
    def _stage3_final(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage3_final", True):
            self._log_debug("STAGE7_SKIPPED", "Stage7 (final) disabled")
            self._stage11_validation()
            return

        self._log_debug(f"=== STAGE7: final (attempt {retry_count+1}) ===")
        self._display_system(f"📖 Этап 7/10: Генерация финального ответа (попытка {retry_count+1})...\n")

        location_id = self.stage_data.get("scene_location_id")
        location_desc = self.stage_data["descriptions"].get(location_id, "Локация") if location_id else "Неизвестно"

        npc_actions_text = ""
        for cid in self.stage_data.get("scene_character_ids", []):
            char = self.main_app.characters.get(cid)
            if char and not char.is_player and cid in self.stage_data["npc_actions"]:
                npc_actions_text += f"{char.name}: {self.stage_data['npc_actions'][cid]}\n"

        player_outcome = self.stage_data["player_action_desc"]
        event_desc = self.stage_data["event_desc"] if self.stage_data["event_occurred"] else ""

        dice_rules = self.main_app.prompt_manager.get_prompt_content("dice_rules")

        npc_dice_results = []
        for cid in self.stage_data.get("scene_character_ids", []):
            char = self.main_app.characters.get(cid)
            if char and not char.is_player:
                val = self._pop_dice('d20')
                result = {1:"крит.провал",2:"провал",3:"провал",4:"провал"}.get(val, "успех" if 5<=val<=15 else "большой успех" if val<=19 else "крит.успех")
                npc_dice_results.append(f"{char.name}: d20={val} → {result}")
        dice_summary = "\n".join(npc_dice_results) if npc_dice_results else "Нет NPC"

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage3_final")
        if not prompt_template:
            raise RuntimeError("Промт 'stage3_final' не загружен.")
        prompt = prompt_template.format(
            location_desc=location_desc,
            player_action_outcome=player_outcome,
            event_description=event_desc,
            npcs_actions=npc_actions_text,
            dice_results=dice_summary,
            dice_rules=dice_rules
        )

        # ДОБАВЛЕНИЕ: если нет активных NPC и не произошло события – форсируем развитие сцены
        if not self.stage_data.get("npc_actions") and not self.stage_data.get("event_occurred"):
            extra_instruction = (
                "\n\n**ВАЖНО:** В этой сцене нет активных NPC и не произошло случайного события. "
                "Ты ОБЯЗАН продвинуть сюжет: опиши, как проходит 5-10 минут, или добавь внешнее изменение "
                "(звук, скрип, чей-то голос), или заставь NPC (если он есть) совершить простое действие. "
                "Не оставляй сцену замороженной."
            )
            prompt += extra_instruction
            self._display_system("⚠️ Сцена статична – добавлена инструкция принудительного развития.\n")

        messages = [{"role": "user", "content": prompt}]
        self.main_app.center_panel.start_temp_response()
        self._send_request(
            messages,
            lambda content, extra: self._after_stage3_final(content, extra),
            extra={"retry_count": retry_count},
            stage_name="stage3_final",
            use_temp=False,
            show_in_thinking=True
        )

    def _after_stage3_final(self, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_full_response("stage3_final", content)

        final = content.strip() if content else ""
        # --- ИСПРАВЛЕНИЕ ЭКРАНИРОВАННЫХ ПЕРЕНОСОВ ---
        final = final.replace('\\n', '\n')
        # -------------------------------------------
        if not final:
            limit = self._get_retry_limit("stage3_final")
            if retry_count < limit:
                self._display_error("⚠️ Пустой ответ, повтор...\n")
                self._stage3_final(retry_count+1)
                return
            final = "(Рассказчик молчит)"

        import re
        forbidden_patterns = [
            r'^Ты можешь\b', r'^Можешь\b', r'^Попробуй\b',
            r'^Ты можешь выбрать\b', r'^Ты лежишь\b', r'^Ты просыпаешься\b',
            r'^Ты открываешь глаза\b', r'^Ты видишь\b', r'^Ты чувствуешь\b',
            r'^Ты понимаешь\b', r'^Кажется\b', r'^Словно\b'
        ]
        lines = final.split('\n')
        filtered_lines = []
        for line in lines:
            if any(re.match(p, line.strip(), re.IGNORECASE) for p in forbidden_patterns):
                continue
            filtered_lines.append(line)
        final = '\n'.join(filtered_lines)

        # Убираем двойные переносы строк
        final = final.replace('\n\n', '\n')
        final = '\n'.join(line.strip() for line in final.split('\n'))

        self.stage_data["final_response"] = final
        self.main_app.center_panel.clear_temp_response()
        self._stage11_validation()
        
    # --------------------------------------------------------------------------
    # СТАДИЯ 8: валидация финального ответа
    # --------------------------------------------------------------------------
    def _stage11_validation(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage11_validation", True):
            self._log_debug("STAGE11_SKIPPED", "Stage11 (validation) disabled")
            self._stage4_summary()
            return

        self._log_debug(f"=== STAGE11: validation (attempt {retry_count+1}) ===")
        self._display_system(f"✅ Этап 8/10: Валидация результата (попытка {retry_count+1})...\n")

        final_response = self.stage_data.get("final_response", "")
        if not final_response:
            self._stage4_summary()
            return

        scene_location_id = self.stage_data.get('scene_location_id', '')
        scene_character_ids = ', '.join(self.stage_data.get('scene_character_ids', []))
        scene_item_ids = ', '.join(self.stage_data.get('scene_item_ids', []))
        descriptions = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data['descriptions'].items()])

        player_action_desc = self.stage_data.get('player_action_desc', '')
        player_action_dice = self.stage_data.get('player_action_dice', 'неизвестно')

        event_occurred = self.stage_data.get('event_occurred', False)
        event_occurrence_dice = self.stage_data.get('event_occurrence_dice', 'неизвестно')
        event_quality_dice = self.stage_data.get('event_quality_dice', 'неизвестно')
        event_desc = self.stage_data.get('event_desc', '')

        npc_actions_lines = []
        for cid, action in self.stage_data.get('npc_actions', {}).items():
            char = self.main_app.characters.get(cid)
            name = char.name if char else cid
            npc_actions_lines.append(f"{name}: {action}")
        npc_actions = "\n".join(npc_actions_lines)

        npc_dice_lines = []
        for cid in self.stage_data.get('scene_character_ids', []):
            char = self.main_app.characters.get(cid)
            if char and not char.is_player:
                dice_val = self._pop_dice('d20')
                npc_dice_lines.append(f"{char.name}: d20={dice_val}")
        dice_summary_npc = "\n".join(npc_dice_lines)

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage11_validation")
        if not prompt_template:
            self._display_error("❌ Промт 'stage11_validation' не загружен. Валидация пропущена.\n")
            self._stage4_summary()
            return

        validation_prompt = prompt_template.format(
            scene_location_id=scene_location_id,
            scene_character_ids=scene_character_ids,
            scene_item_ids=scene_item_ids,
            descriptions=descriptions,
            player_action_desc=player_action_desc,
            player_action_dice=player_action_dice,
            event_occurred=event_occurred,
            event_occurrence_dice=event_occurrence_dice,
            event_quality_dice=event_quality_dice,
            event_desc=event_desc,
            npc_actions=npc_actions,
            dice_summary_npc=dice_summary_npc,
            final_response=final_response
        )

        messages = [
            {"role": "system", "content": "Ты проверяешь и при необходимости исправляешь ответ ассистента."},
            {"role": "user", "content": validation_prompt}
        ]

        self._send_request(
            messages,
            lambda content, extra: self._after_stage11_validation(content, extra),
            extra={"retry_count": retry_count},
            stage_name="stage11_validation",
            use_temp=False,
            show_in_thinking=True
        )

    def _after_stage11_validation(self, content, extra):
        retry_count = extra.get("retry_count", 0)
        max_retries = self._get_retry_limit("stage11_validation")  # обычно 2-3
        self._log_full_response("stage11_validation", content)

        corrected = None

        # Попытка распарсить корректный вызов validate_response
        tool_calls = self._try_parse_tool_calls_from_text(content, expected_func_names=["validate_response"])
        if tool_calls:
            call = tool_calls[-1]
            try:
                args = json.loads(call["function"]["arguments"])
                # Ожидаемый формат: validate_response(["текст"])  -> args = ["текст"]
                # Ошибочный формат: validate_response(["строка1", "строка2"], []) -> args = (["строка1","строка2"], [])
                # Нормализуем:
                if isinstance(args, list) and len(args) == 1 and isinstance(args[0], str):
                    corrected = args[0]
                elif isinstance(args, list) and len(args) == 1 and isinstance(args[0], list) and len(args[0]) == 1:
                    # случай: [["текст"]]
                    corrected = args[0][0] if args[0] else ""
                elif isinstance(args, tuple) and len(args) == 2 and args[1] == []:
                    # ошибочный формат: (["строка1", "строка2"], [])
                    if isinstance(args[0], list) and args[0]:
                        # склеиваем строки через \n
                        corrected = "\n".join(args[0])
                elif isinstance(args, list) and len(args) > 1 and all(isinstance(x, str) for x in args):
                    # ошибочный формат: ["строка1", "строка2"] (без второго списка)
                    corrected = "\n".join(args)
                else:
                    self._log_debug("VALIDATION_WRONG_FORMAT", f"Неизвестный формат args: {args}")
            except Exception as e:
                self._log_debug("ERROR", f"validate_response parse error: {e}")

        # Если не удалось получить corrected из вызова, пробуем извлечь из текста по паттернам
        if corrected is None and content:
            patterns = [
                r'validate_response\(\s*\[\s*"(.+?)"\s*\]\s*\)',
                r'Исправленный текст:\s*(.+?)(?=\n\n|\Z)',
                r'Исправленный ответ:\s*(.+?)(?=\n\n|\Z)',
            ]
            for pat in patterns:
                match = re.search(pat, content, re.DOTALL | re.IGNORECASE)
                if match:
                    corrected = match.group(1).strip()
                    break

        # Если corrected получен и не пуст (или пустая строка — означает "без изменений")
        if corrected is not None and isinstance(corrected, str):
            # Пустая строка -> валидация пройдена, без изменений
            if corrected.strip() == "":
                self._display_system("✅ Валидация пройдена, ответ корректен.\n")
                self._stage4_summary()
                return

            # Применяем минимальные исправления
            corrected = corrected.replace('\\n', '\n')
            import re
            forbidden = [r'ты можешь', r'можешь выбрать', r'ты видишь', r'ты чувствуешь', r'ты лежишь']
            if any(re.search(p, corrected, re.IGNORECASE) for p in forbidden):
                self._display_system("⚠️ Валидатор пропустил запрещённые фразы, применяю дополнительную очистку.\n")
                for p in forbidden:
                    corrected = re.sub(p, '', corrected, flags=re.IGNORECASE)
                corrected = re.sub(r'\s+', ' ', corrected).strip()
            corrected = corrected.replace('\n\n', '\n')
            corrected = '\n'.join(line.strip() for line in corrected.split('\n'))
            self.stage_data["final_response"] = corrected.strip()
            self._display_system("✅ Ответ исправлен по результатам валидации.\n")
            self._stage4_summary()
            return

        # Если corrected не получен или пуст (и при этом не пустая строка-признак)
        if retry_count < max_retries:
            self._display_error(f"⚠️ Валидатор вернул некорректный формат. Повтор ({retry_count+1}/{max_retries})...\n")
            self._stage11_validation(retry_count + 1)
            return
        else:
            self._display_system("⚠️ Не удалось получить корректный ответ валидатора после всех попыток. Пропускаем валидацию.\n")
            self._stage4_summary()

    # --------------------------------------------------------------------------
    # СТАДИЯ 9: краткая память (summary)
    # --------------------------------------------------------------------------
    def _stage4_summary(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage4_summary", True):
            self._log_debug("STAGE9_SKIPPED", "Stage9 (summary) disabled")
            self._stage10_associative_memory()
            return

        self._log_debug(f"=== STAGE9: summary (attempt {retry_count+1}) ===")
        self._display_system(f"📝 Этап 9/10: Краткая память (попытка {retry_count+1})...\n")

        last_user = self.stage_data["original_user_message"]
        last_assistant = self.stage_data.get("final_response", "")
        if not last_assistant and self.main_app.conversation_history:
            for msg in reversed(self.main_app.conversation_history):
                if msg["role"] == "assistant":
                    last_assistant = msg["content"]
                    break

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage4_summary")
        if not prompt_template:
            raise RuntimeError("Промт 'stage4_summary' не загружен.")
        prompt = prompt_template.format(
            last_user_msg=last_user,
            last_assistant_msg=last_assistant
        )
        messages = [
            {"role": "system", "content": "Ты выделяешь одно ключевое изменение."},
            {"role": "user", "content": prompt}
        ]
        self.main_app.center_panel.start_temp_response()
        self._send_request(
            messages,
            lambda content, extra: self._after_stage4_summary(content, extra),
            extra={"retry_count": retry_count},
            stage_name="stage4_summary",
            use_temp=True,
            show_in_thinking=True
        )

    def _after_stage4_summary(self, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_full_response("stage4_summary", content)
        self.main_app.center_panel.clear_temp_response()
        summary = content.strip() if content else ""
        if not summary or len(summary) > 100:
            limit = self._get_retry_limit("stage4_summary")
            if retry_count < limit:
                self._display_error("⚠️ Слишком длинно или пусто, повтор...\n")
                self._stage4_summary(retry_count+1)
                return
            summary = "Игрок продолжил действия."
        self.main_app.record_added_summary(summary)
        self._display_system(f"🧠 Память: {summary[:100]}\n")
        self._stage10_associative_memory()

    # --------------------------------------------------------------------------
    # СТАДИЯ 10: ассоциативная память объектов (пропускается, если выключена)
    # --------------------------------------------------------------------------
    def _stage10_associative_memory(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage10_associative_memory", True) or not self.main_app.enable_associative_memory:
            self._log_debug("STAGE10_SKIPPED", "Stage10 (associative) disabled")
            self._finish_generation()
            return

        self._log_debug(f"=== STAGE10: associative (attempt {retry_count+1}) ===")
        self._display_system(f"🧠 Этап 10/10: Ассоциативная память (попытка {retry_count+1})...\n")

        final = self.stage_data.get("final_response", "")
        if not final:
            self._finish_generation()
            return

        objects_info = []
        for oid, desc in self.stage_data["descriptions"].items():
            obj = self.main_app._get_object_by_id(oid)
            if obj:
                assoc = self.main_app.get_associative_memory_for_object(oid)
                objects_info.append(f"{oid} ({obj.name}): {desc}\n{assoc}")
        objects_text = "\n\n".join(objects_info) if objects_info else "Нет объектов."

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage10_associative_memory")
        if not prompt_template:
            raise RuntimeError("Промт 'stage10_associative_memory' не загружен.")
        prompt = prompt_template.format(
            final_response=final,
            objects=objects_text
        )
        prompt += "\n\n⚠️ Формат: object_id: изменение"
        messages = [{"role": "user", "content": prompt}]
        self._send_request(
            messages,
            lambda content, extra: self._after_stage10_associative_memory(content, extra),
            extra={"retry_count": retry_count},
            stage_name="stage10_associative_memory",
            use_temp=True,
            show_in_thinking=True
        )

    def _after_stage10_associative_memory(self, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_full_response("stage10_associative_memory", content)
        if not content or len(content.strip()) < 5:
            limit = self._get_retry_limit("stage10_associative_memory")
            if retry_count < limit:
                self._display_error("⚠️ Повтор...\n")
                self._stage10_associative_memory(retry_count+1)
                return
            self._finish_generation()
            return

        updated = 0
        changed_ids = [] 
        for line in content.strip().split('\n'):
            if ':' in line:
                obj_id, change = line.split(':', 1)
                obj_id = obj_id.strip()
                change = change.strip()
                if obj_id and change and len(change) > 3:
                    self.main_app.record_added_assoc(obj_id, change)
                    updated += 1
                    changed_ids.append(obj_id)   
        self.last_changed_objects = list(set(changed_ids))  
        self._display_system(f"✅ Память обновлена для {updated} объектов.\n")
        self._finish_generation()