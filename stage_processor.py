import json
import random
import re
from typing import Dict, List, Optional, Any, Callable, Tuple

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
    """
    CONFIGURABLE_STAGES = [
        "stage1_request_descriptions",
        "stage1_truth_check",
        "stage1_player_action",
        "stage1_random_event",
        "stage1_random_event_request_objects",
        "stage2_npc_action",
        "stage4_summary",
        "stage10_associative_memory"
    ]

    def __init__(self, main_app):
        self.main_app = main_app
        self.generation_start_time = None
        self.stage = None
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

    def _get_object_by_id(self, obj_id: str):
        return self.main_app._get_object_by_id(obj_id)

    def _get_object_description_with_local(self, obj_id: str) -> str:
        return self.main_app.get_description_for_model(obj_id)

    def _send_request(self, messages, callback, extra=None, expect_tool_calls=True,
                      stage_name: str = None, use_temp: bool = False, tools_override=None,
                      show_in_thinking: bool = False):
        self.main_app._send_model_request(
            messages, callback, extra, expect_tool_calls,
            stage_name, use_temp, tools_override, show_in_thinking
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
            self._display_system(f"✅ Генерация завершена за {total_time:.2f} секунд.\n")
            self._log_debug("GENERATION_COMPLETED", f"Total time: {total_time:.2f} sec")
            self.generation_start_time = None
        else:
            self._log_debug("GENERATION_COMPLETED")
        self.main_app.is_generating = False
        self.main_app.center_panel.set_input_state("normal")
        self.main_app.center_panel.update_translation_button_state()
        self.main_app.current_debug_log_path = None

    def _save_current_session(self):
        self.main_app._save_current_session_safe()

    def _try_parse_tool_calls_from_text(self, content: str, expected_func_names: List[str] = None) -> List[Dict]:
        if not content:
            return []
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

    # --------------------------------------------------------------------------
    # Синхронное получение описаний объектов
    # --------------------------------------------------------------------------
    def _fetch_descriptions_sync(self, obj_ids: List[str]):
        """Синхронно получает описания для всех объектов и сохраняет в stage_data["descriptions"]."""
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
            self._stage3_truth_check()
            return

        self._log_debug(f"=== STAGE1.1: request_descriptions (attempt {retry_count+1}) ===")
        self._display_system(f"🔍 Этап 1.1/9: Определение необходимых объектов (попытка {retry_count+1})...\n")

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

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_request_descriptions")
        if not prompt_template:
            raise RuntimeError("Промт 'stage1_request_descriptions' не загружен. Проверьте файлы промтов.")
        main_prompt = prompt_template.format(
            user_message=self.stage_data["user_message"],
            available_objects=available
        )
        # Жёсткое указание формата
        main_prompt += "\n\n⚠️ Ты должен ответить ТОЛЬКО вызовом send_object_info с массивом ID объектов. Пример: send_object_info(['l1','c2','c3']). Никакого другого текста."

        messages = [
            {"role": "user", "content": f"Сообщение игрока: {self.stage_data['user_message']}"},
            {"role": "system", "content": main_prompt}
        ]

        self._send_request(
            messages,
            lambda tc, cont, extra: self._after_stage1_request_descriptions(tc, cont, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_request_descriptions",
            show_in_thinking=True
        )

    def _after_stage1_request_descriptions(self, tool_calls, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_debug("AFTER stage1_request_descriptions", f"tool_calls: {tool_calls}\ncontent: {content[:500] if content else ''}")

        send_call = None
        for tc in tool_calls:
            if tc["function"]["name"] == "send_object_info":
                send_call = tc
                break

        if not send_call and content:
            parsed = self._try_parse_tool_calls_from_text(content, expected_func_names=["send_object_info"])
            if parsed:
                send_call = parsed[0]
                self._display_system("📝 Извлёк send_object_info из текста.\n")

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

        if retry_count < 2:
            self._display_error(f"⚠️ Модель не вызвала send_object_info. Повтор ({retry_count+1}/2)...\n")
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
        self._stage3_truth_check()

    # --------------------------------------------------------------------------
    # СТАДИЯ 1.2: создание сцены на основе полученных описаний
    # --------------------------------------------------------------------------
    def _stage1_create_scene(self, retry_count=0):
        self._log_debug(f"=== STAGE1.2: create_scene (attempt {retry_count+1}) ===")
        self._display_system(f"🎬 Этап 1.2/9: Создание сцены (попытка {retry_count+1})...\n")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_create_scene")
        if not prompt_template:
            raise RuntimeError("Промт 'stage1_create_scene' не загружен. Проверьте файлы промтов.")
        main_prompt = prompt_template.format(
            user_message=self.stage_data["user_message"],
            descriptions=descriptions_text
        )
        # Используем позиционные аргументы, строгий формат
        main_prompt += "\n\n⚠️ Ты должен ответить ТОЛЬКО вызовом confirm_scene с позиционными аргументами: confirm_scene(location_id, character_ids, item_ids). Пример: confirm_scene('l1', ['c2','c3'], []). Никакого другого текста."

        messages = [
            {"role": "user", "content": f"Сообщение игрока: {self.stage_data['user_message']}"},
            {"role": "system", "content": main_prompt}
        ]

        self._send_request(
            messages,
            lambda tc, cont, extra: self._after_stage1_create_scene(tc, cont, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_create_scene",
            show_in_thinking=True
        )

    def _after_stage1_create_scene(self, tool_calls, content, extra):
        retry_count = extra.get("retry_count", 0)
        confirm_call = None
        for tc in tool_calls:
            if tc["function"]["name"] == "confirm_scene":
                confirm_call = tc
                break
        if not confirm_call and content:
            parsed = self._try_parse_tool_calls_from_text(content, expected_func_names=["confirm_scene"])
            if parsed:
                confirm_call = parsed[0]
                self._display_system("📝 Извлёк confirm_scene из текста.\n")

        if confirm_call:
            try:
                args = json.loads(confirm_call["function"]["arguments"])
                location_id = None
                character_ids = []
                item_ids = []

                # Поддержка позиционных аргументов: ['l1', ['c2','c3'], []]
                if isinstance(args, list) and len(args) >= 3:
                    location_id = args[0] if isinstance(args[0], str) else None
                    character_ids = args[1] if isinstance(args[1], list) else []
                    item_ids = args[2] if isinstance(args[2], list) else []
                else:
                    location_id = args.get("location_id")
                    character_ids = args.get("character_ids", [])
                    item_ids = args.get("item_ids", [])

                if not isinstance(location_id, str):
                    location_id = None

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
                self._stage3_truth_check()
                return
            except Exception as e:
                self._log_debug("ERROR", f"confirm_scene parse error: {e}")

        if retry_count < 2:
            self._display_error(f"⚠️ Модель не вызвала confirm_scene. Повтор ({retry_count+1}/2)...\n")
            self._stage1_create_scene(retry_count+1)
        else:
            self._display_system("⚠️ Не удалось получить confirm_scene. Создаём сцену по умолчанию.\n")
            self._create_default_scene()

    # --------------------------------------------------------------------------
    # СТАДИЯ 2: проверка правдивости
    # --------------------------------------------------------------------------
    def _stage3_truth_check(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage1_truth_check", True):
            self._log_debug("STAGE2_SKIPPED", "Stage2 (truth_check) disabled")
            self._stage4_player_action()
            return

        self._log_debug(f"=== STAGE2: truth_check (attempt {retry_count+1}) ===")
        self._display_system(f"🔍 Этап 2/9: Проверка правдивости (попытка {retry_count+1})...\n")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_truth_check")
        if not prompt_template:
            raise RuntimeError("Промт 'stage1_truth_check' не загружен.")
        main_prompt = prompt_template.format(
            user_message=self.stage_data["user_message"],
            descriptions=descriptions_text
        )
        main_prompt += "\n\n⚠️ Вызови report_truth_check(violation='...', edited_message='...')"

        messages = [
            {"role": "user", "content": f"Проверь сообщение: {self.stage_data['user_message']}"},
            {"role": "system", "content": main_prompt}
        ]

        self._send_request(
            messages,
            lambda tc, cont, extra: self._after_stage3_truth_check(tc, cont, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_truth_check",
            show_in_thinking=True
        )

    def _after_stage3_truth_check(self, tool_calls, content, extra):
        retry_count = extra.get("retry_count", 0)
        report_call = None
        for tc in tool_calls:
            if tc["function"]["name"] == "report_truth_check":
                report_call = tc
                break
        if not report_call and content:
            parsed = self._try_parse_tool_calls_from_text(content, ["report_truth_check"])
            if parsed:
                report_call = parsed[0]

        if not report_call:
            if retry_count < 2:
                self._display_error(f"⚠️ Повтор truth_check...\n")
                self._stage3_truth_check(retry_count+1)
                return
            else:
                self.stage_data["truth_violation"] = ""
                self._stage4_player_action()
                return

        try:
            args = json.loads(report_call["function"]["arguments"])
            self.stage_data["truth_violation"] = args.get("violation", "")
            if args.get("edited_message"):
                self.stage_data["user_message"] = args["edited_message"]
                self._display_system(f"✏️ Сообщение изменено: {self.stage_data['user_message']}\n")
            self._stage4_player_action()
        except Exception as e:
            self._log_debug("ERROR", f"truth_check parse error: {e}")
            if retry_count < 2:
                self._stage3_truth_check(retry_count+1)
            else:
                self.stage_data["truth_violation"] = ""
                self._stage4_player_action()

    # --------------------------------------------------------------------------
    # СТАДИЯ 3: действие игрока
    # --------------------------------------------------------------------------
    def _stage4_player_action(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage1_player_action", True):
            self._log_debug("STAGE3_SKIPPED", "Stage3 (player_action) disabled")
            self._stage5_random_event_determine()
            return

        self._log_debug(f"=== STAGE3: player_action (attempt {retry_count+1}) ===")
        self._display_system(f"🎲 Этап 3/9: Действие игрока (попытка {retry_count+1})...\n")

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
        main_prompt += f"\n\n⚠️ Вызови report_player_action({dice_value}, 'твоё описание')."

        messages = [
            {"role": "user", "content": f"Игрок: {self.stage_data['user_message']}"},
            {"role": "system", "content": main_prompt}
        ]

        self._send_request(
            messages,
            lambda tc, cont, extra: self._after_stage4_player_action(tc, cont, extra),
            extra={"retry_count": retry_count, "expected_dice": dice_value},
            stage_name="stage1_player_action",
            show_in_thinking=True
        )

    def _after_stage4_player_action(self, tool_calls, content, extra):
        retry_count = extra.get("retry_count", 0)
        expected_dice = extra.get("expected_dice")

        report_call = None
        for tc in tool_calls:
            if tc["function"]["name"] in ("report_player_action", "player_action"):
                report_call = tc
                break
        if not report_call and content:
            parsed = self._try_parse_tool_calls_from_text(content, ["report_player_action", "player_action"])
            if parsed:
                report_call = parsed[0]

        if not report_call:
            if retry_count < 2:
                self._display_error(f"⚠️ Модель не вызвала report_player_action. Повтор...\n")
                self._stage4_player_action(retry_count+1)
                return
            else:
                self.stage_data["player_action_desc"] = "Игрок действует."
                self._stage5_random_event_determine()
                return

        try:
            args = json.loads(report_call["function"]["arguments"])
            if isinstance(args, list) and len(args) >= 2:
                description = args[1] if isinstance(args[1], str) else str(args[1])
            else:
                description = args.get("description", "")
            self.stage_data["player_action_desc"] = description or "Действие выполнено."
            self._display_system(f"✍️ Результат: {description[:100]}...\n")
            self._stage5_random_event_determine()
        except Exception as e:
            self._log_debug("ERROR", f"report_player_action error: {e}")
            if retry_count < 2:
                self._stage4_player_action(retry_count+1)
            else:
                self.stage_data["player_action_desc"] = "Действие выполнено."
                self._stage5_random_event_determine()

    # --------------------------------------------------------------------------
    # СТАДИЯ 4: определение случайного события (произошло ли)
    # --------------------------------------------------------------------------
    def _stage5_random_event_determine(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage1_random_event", True):
            self._log_debug("STAGE4_SKIPPED", "Stage4 (random_event) disabled")
            self._stage7_process_npcs()
            return

        self._log_debug(f"=== STAGE4: random_event (determine) (attempt {retry_count+1}) ===")
        self._display_system(f"🎲 Этап 4/9: Определение случайного события (попытка {retry_count+1})...\n")

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
        main_prompt += "\n\n⚠️ Вызови report_random_event с параметрами dice_value, event_occurred (true/false) и description=''."

        messages = [
            {"role": "user", "content": f"Действие игрока: {player_action}"},
            {"role": "system", "content": main_prompt}
        ]

        self._send_request(
            messages,
            lambda tc, cont, extra: self._after_stage5_random_event_determine(tc, cont, extra),
            extra={"retry_count": retry_count, "dice_value": dice_value, "event_chance": event_chance},
            stage_name="stage1_random_event",
            show_in_thinking=True
        )

    def _after_stage5_random_event_determine(self, tool_calls, content, extra):
        retry_count = extra.get("retry_count", 0)
        expected_dice = extra.get("dice_value")

        report_call = None
        for tc in tool_calls:
            if tc["function"]["name"] == "report_random_event":
                report_call = tc
                break
        if not report_call and content:
            parsed = self._try_parse_tool_calls_from_text(content, ["report_random_event"])
            if parsed:
                report_call = parsed[0]
                self._display_system("📝 Извлёк report_random_event из текста.\n")

        if report_call:
            try:
                args = json.loads(report_call["function"]["arguments"])
                if isinstance(args, list) and len(args) >= 2:
                    dice_val = args[0]
                    event_occurred = args[1]
                else:
                    dice_val = args.get("dice_value")
                    event_occurred = args.get("event_occurred")
                if dice_val != expected_dice:
                    self._display_error(f"⚠️ Модель вернула dice_value={dice_val}, ожидалось {expected_dice}. Использую значение модели.\n")
                if isinstance(event_occurred, str):
                    event_occurred = event_occurred.lower() in ('true', 'yes', '1')
                self.stage_data["event_occurred"] = bool(event_occurred)

                self._display_system(f"✨ Событие: {'произошло' if self.stage_data['event_occurred'] else 'НЕ произошло'} (d100={dice_val})\n")
                if self.stage_data["event_occurred"]:
                    self._stage5_random_event_request_objects()
                else:
                    self._stage7_process_npcs()
                return
            except Exception as e:
                self._log_debug("ERROR", f"report_random_event parse error: {e}")

        if retry_count < 2:
            self._display_error(f"⚠️ Модель не вызвала report_random_event. Повтор ({retry_count+1}/2)...\n")
            self._stage5_random_event_determine(retry_count+1)
        else:
            self._display_system("⚠️ Модель не определила событие. Считаем, что событие не произошло.\n")
            self.stage_data["event_occurred"] = False
            self._stage7_process_npcs()

    # --------------------------------------------------------------------------
    # СТАДИЯ 5.1: запрос недостающих объектов для случайного события
    # --------------------------------------------------------------------------
    def _stage5_random_event_request_objects(self, retry_count=0):
        self._log_debug(f"=== STAGE5.1: request objects for event (attempt {retry_count+1}) ===")
        self._display_system(f"📦 Этап 5.1/9: Запрос объектов для события (попытка {retry_count+1})...\n")

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

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_random_event_request_objects")
        if not prompt_template:
            raise RuntimeError("Промт 'stage1_random_event_request_objects' не загружен.")
        main_prompt = prompt_template.format(
            event_dice=event_dice,
            descriptions=descriptions_text,
            player_action=player_action,
            available_objects=available
        )
        main_prompt += "\n\n⚠️ Если не хватает объектов, вызови send_object_info. Если хватает, ничего не вызывай и ответь 'OK'."

        messages = [
            {"role": "user", "content": "Определи, нужны ли дополнительные объекты для описания события."},
            {"role": "system", "content": main_prompt}
        ]

        self._send_request(
            messages,
            lambda tc, cont, extra: self._after_stage5_random_event_request_objects(tc, cont, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_random_event_request_objects",
            show_in_thinking=True
        )

    def _after_stage5_random_event_request_objects(self, tool_calls, content, extra):
        retry_count = extra.get("retry_count", 0)

        send_call = None
        for tc in tool_calls:
            if tc["function"]["name"] == "send_object_info":
                send_call = tc
                break
        if not send_call and content:
            parsed = self._try_parse_tool_calls_from_text(content, expected_func_names=["send_object_info"])
            if parsed:
                send_call = parsed[0]
                self._display_system("📝 Извлёк send_object_info из текста.\n")

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
                    self._stage5_random_event_details()
                    return
                else:
                    self._display_error("⚠️ send_object_info вызван без корректного списка object_ids.\n")
            except Exception as e:
                self._log_debug("ERROR", f"send_object_info parse error: {e}")

        self._display_system("✅ Дополнительные объекты не требуются.\n")
        self._stage5_random_event_details()

    # --------------------------------------------------------------------------
    # СТАДИЯ 5.2: описание случайного события (с броском качества d20)
    # --------------------------------------------------------------------------
    def _stage5_random_event_details(self, retry_count=0):
        self._log_debug(f"=== STAGE5.2: event details (attempt {retry_count+1}) ===")
        self._display_system(f"✨ Этап 5.2/9: Описание события (попытка {retry_count+1})...\n")

        quality_dice = self._pop_dice('d20')
        self.stage_data["event_quality_dice"] = quality_dice
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
        main_prompt += "\n\n⚠️ Вызови report_random_event с параметрами: dice_value, event_occurred=true, description='...'"

        messages = [
            {"role": "user", "content": "Опиши событие."},
            {"role": "system", "content": main_prompt}
        ]

        self._send_request(
            messages,
            lambda tc, cont, extra: self._after_stage5_random_event_details(tc, cont, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_random_event_continue",
            show_in_thinking=True
        )

    def _after_stage5_random_event_details(self, tool_calls, content, extra):
        retry_count = extra.get("retry_count", 0)
        report_call = None
        for tc in tool_calls:
            if tc["function"]["name"] == "report_random_event":
                report_call = tc
                break
        if not report_call and content:
            parsed = self._try_parse_tool_calls_from_text(content, ["report_random_event"])
            if parsed:
                report_call = parsed[0]

        if report_call:
            try:
                args = json.loads(report_call["function"]["arguments"])
                if isinstance(args, list) and len(args) >= 3:
                    description = args[2]
                else:
                    description = args.get("description", "")
                self.stage_data["event_desc"] = description
                self._display_system(f"✨ Событие: {description[:100]}...\n")
                self._stage7_process_npcs()
                return
            except Exception as e:
                self._log_debug("ERROR", f"event parse error: {e}")

        if retry_count < 2:
            self._display_error(f"⚠️ Модель не описала событие. Повтор...\n")
            self._stage5_random_event_details(retry_count+1)
        else:
            self.stage_data["event_desc"] = "Произошло что-то неожиданное."
            self._stage7_process_npcs()

    # --------------------------------------------------------------------------
    # СТАДИЯ 6: обработка NPC (действия)
    # --------------------------------------------------------------------------
    def _stage7_process_npcs(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage2_npc_action", True):
            self._log_debug("STAGE6_SKIPPED", "Stage6 (NPC) disabled")
            self._stage8_final()
            return

        self._log_debug(f"=== STAGE6: NPCs (attempt {retry_count+1}) ===")
        self._display_system(f"🎭 Этап 6/9: Обработка NPC (попытка {retry_count+1})...\n")

        npc_ids = [cid for cid in self.stage_data.get("scene_character_ids", [])
                   if not self.main_app.characters.get(cid, Character(is_player=False)).is_player]
        if not npc_ids:
            self._display_system("Нет NPC.\n")
            self._stage8_final()
            return

        if not self.stage_data["npc_actions"]:
            self.stage_data["current_npc_index"] = 0
            self.stage_data["npc_actions"] = {}

        if self.stage_data["current_npc_index"] >= len(npc_ids):
            self._display_system("✅ Все NPC обработаны.\n")
            self._stage8_final()
            return

        npc_id = npc_ids[self.stage_data["current_npc_index"]]
        npc = self.main_app.characters.get(npc_id)
        if not npc:
            self.stage_data["current_npc_index"] += 1
            self._stage7_process_npcs()
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
            lambda tc, cont, extra: self._after_stage7_npc_action(tc, cont, extra),
            extra={"npc_id": npc_id, "npc_name": npc.name, "retry_count": retry_count},
            expect_tool_calls=False,
            stage_name="stage2_npc_action",
            show_in_thinking=True
        )

    def _after_stage7_npc_action(self, tool_calls, content, extra):
        npc_id = extra["npc_id"]
        npc_name = extra.get("npc_name", "NPC")
        retry_count = extra.get("retry_count", 0)

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
            if retry_count < 2:
                self._display_error(f"⚠️ Повтор для {npc_name}...\n")
                self._stage7_process_npcs(retry_count+1)
                return
            else:
                intent = f"{npc_name} наблюдает."

        self.stage_data["npc_actions"][npc_id] = intent
        self._display_system(f"✍️ {npc_name}: {intent[:100]}\n")
        self.stage_data["current_npc_index"] += 1
        self._stage7_process_npcs()

    # --------------------------------------------------------------------------
    # СТАДИЯ 7: финальный рассказ (СТАДИЯ 8 по логике)
    # --------------------------------------------------------------------------
    def _stage8_final(self, retry_count=0):
        self._log_debug(f"=== STAGE7: final (attempt {retry_count+1}) ===")
        self._display_system(f"📖 Этап 7/9: Генерация финального ответа (попытка {retry_count+1})...\n")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])

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
            dice_rules=dice_rules,
            all_objects=descriptions_text
        )
        messages = [{"role": "user", "content": prompt}]
        self.main_app.center_panel.start_temp_response()
        self._send_request(
            messages,
            lambda tc, cont, extra: self._after_stage8_final(tc, cont, extra),
            extra={"retry_count": retry_count},
            stage_name="stage3_final",
            use_temp=True,
            expect_tool_calls=False,
            show_in_thinking=False
        )

    def _after_stage8_final(self, tool_calls, content, extra):
        retry_count = extra.get("retry_count", 0)
        final = content.strip() if content else ""
        if not final and retry_count < 2:
            self._display_error("⚠️ Пустой ответ, повтор...\n")
            self._stage8_final(retry_count+1)
            return
        if not final:
            final = "(Рассказчик молчит)"

        self.main_app.center_panel.clear_temp_response()
        self.main_app.center_panel.display_message(f"\nАссистент: {final}\n\n", "assistant")
        self.main_app.conversation_history.append({"role": "assistant", "content": final})
        self.stage_data["final_response"] = final
        self._save_current_session()
        self._stage9_summary()

    # --------------------------------------------------------------------------
    # СТАДИЯ 8: краткая память (summary)
    # --------------------------------------------------------------------------
    def _stage9_summary(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage4_summary", True):
            self._log_debug("STAGE8_SKIPPED", "Stage8 (summary) disabled")
            self._stage10_associative_memory()
            return

        self._log_debug(f"=== STAGE8: summary (attempt {retry_count+1}) ===")
        self._display_system(f"📝 Этап 8/9: Краткая память (попытка {retry_count+1})...\n")

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
            lambda tc, cont, extra: self._after_stage9_summary(tc, cont, extra),
            extra={"retry_count": retry_count},
            expect_tool_calls=False,
            stage_name="stage4_summary",
            use_temp=True,
            tools_override=[],
            show_in_thinking=True
        )

    def _after_stage9_summary(self, tool_calls, content, extra):
        retry_count = extra.get("retry_count", 0)
        self.main_app.center_panel.clear_temp_response()
        summary = content.strip() if content else ""
        if not summary or len(summary) > 100:
            if retry_count < 1:
                self._display_error("⚠️ Слишком длинно или пусто, повтор...\n")
                self._stage9_summary(retry_count+1)
                return
            summary = "Игрок продолжил действия."
        self.main_app.memory_summaries.append(summary)
        if len(self.main_app.memory_summaries) > self.main_app.max_memory_summaries:
            self.main_app.memory_summaries = self.main_app.memory_summaries[-self.main_app.max_memory_summaries:]
        self._save_current_session()
        self._display_system(f"🧠 Память: {summary[:100]}\n")
        self._stage10_associative_memory()

    # --------------------------------------------------------------------------
    # СТАДИЯ 9: ассоциативная память объектов
    # --------------------------------------------------------------------------
    def _stage10_associative_memory(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage10_associative_memory", True):
            self._log_debug("STAGE9_SKIPPED", "Stage9 (associative) disabled")
            self._finish_generation()
            return

        self._log_debug(f"=== STAGE9: associative (attempt {retry_count+1}) ===")
        self._display_system(f"🧠 Этап 9/9: Ассоциативная память (попытка {retry_count+1})...\n")

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
            lambda tc, cont, extra: self._after_stage10_associative_memory(tc, cont, extra),
            extra={"retry_count": retry_count},
            expect_tool_calls=False,
            stage_name="stage10_associative_memory",
            use_temp=True,
            show_in_thinking=True
        )

    def _after_stage10_associative_memory(self, tool_calls, content, extra):
        retry_count = extra.get("retry_count", 0)
        if not content or len(content.strip()) < 5:
            if retry_count < 2:
                self._display_error("⚠️ Повтор...\n")
                self._stage10_associative_memory(retry_count+1)
                return
            self._finish_generation()
            return

        updated = 0
        for line in content.strip().split('\n'):
            if ':' in line:
                obj_id, change = line.split(':', 1)
                obj_id = obj_id.strip()
                change = change.strip()
                if obj_id and change and len(change) > 3:
                    self.main_app.update_associative_memory(obj_id, change)
                    updated += 1
        self._display_system(f"✅ Память обновлена для {updated} объектов.\n")
        self._finish_generation()