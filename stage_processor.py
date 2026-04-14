import json
import random
import re
import threading
from typing import Dict, List, Optional, Any, Callable, Tuple

from models import Character
import time


class UniversalParser:
    """
    Извлекает вызовы функций из текстового ответа модели, если они не были переданы через tool_calls.
    Поддерживает форматы:
      - function_name(param1=value1, param2=value2)
      - {"name": "function_name", "arguments": {...}}
      - function_name({"param": value})
      - Простые ключ=значение, если функция очевидна из контекста.
    """

    FUNC_CALL_PATTERN = re.compile(
        r'(?P<func>\w+)\s*\(\s*(?P<args>[^)]+?)\s*\)',
        re.DOTALL | re.IGNORECASE
    )
    JSON_PATTERN = re.compile(r'\{[^{}]*\}+')

    @classmethod
    def parse(cls, text: str) -> List[Tuple[str, Dict[str, Any]]]:
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
                    elif 'function' in obj and 'arguments' in obj:
                        results.append((obj['function'], obj['arguments']))
                except json.JSONDecodeError:
                    continue
        if not results and ('location_id' in text.lower() or 'character_ids' in text.lower()):
            args = cls._extract_simple_dict(text)
            if args:
                if 'location_id' in args or 'character_ids' in args:
                    results.append(('confirm_scene', args))
                elif 'valid' in args:
                    results.append(('report_validation_result', args))
                elif 'violation' in args or 'edited_message' in args:
                    results.append(('report_truth_check', args))
                elif 'dice_value' in args and 'description' in args:
                    results.append(('report_player_action', args))
                elif 'event_occurred' in args:
                    results.append(('report_random_event', args))
        return results

    @classmethod
    def _parse_arguments(cls, args_str: str) -> Optional[Dict[str, Any]]:
        args_str = args_str.strip()
        if not args_str:
            return None
        if args_str.startswith('{') and args_str.endswith('}'):
            try:
                return json.loads(args_str)
            except:
                pass
        result = {}
        parts = cls._split_args_preserve_brackets(args_str)
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
                    items = [cls._parse_single_value(x.strip()) for x in cls._split_args_preserve_brackets(inner, sep=',')]
                    value = items
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

    @classmethod
    def _extract_simple_dict(cls, text: str) -> Dict[str, Any]:
        result = {}
        pairs = re.findall(r'(\w+)\s*[:=]\s*([^,;\n]+(?:,[^,;\n]+)*)', text)
        for key, value_str in pairs:
            key = key.strip()
            value_str = value_str.strip()
            if value_str.startswith(("'", '"')) and value_str.endswith(("'", '"')):
                value_str = value_str[1:-1]
            if ',' in value_str:
                value = [v.strip() for v in value_str.split(',')]
            else:
                value = value_str
            result[key] = value
        return result


class StageProcessor:
    """
    Управляет поэтапной генерацией ответа ассистента в соответствии с Logic 2.txt.
    """
    # Список стадий, которые можно отключать (кроме финальной)
    CONFIGURABLE_STAGES = [
        "stage1_request_descriptions",
        "stage1_validate_scene",
        "stage1_truth_check",
        "stage1_player_action",
        "stage1_random_event",
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
            "event_dice": None,
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

    def start_generation(self, user_message: str):
        self.generation_start_time = time.time()
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
            "event_dice": None,
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

    def _get_next_dice_value(self, dice_type: str) -> Optional[int]:
        return self.main_app.get_next_dice_value(dice_type)

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
        if tag == "system":
            self.main_app.center_panel.display_message(msg, "system")
        else:
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
            "не могу согласиться", "не подтверждаю", "не вижу объектов", "не подходит для сцены",
            "не хочу", "не буду", "не нахожу", "не обнаружил", "не подходит под описание",
            "не удовлетворяет", "не может быть", "не подходит по смыслу"
        ]
        text_lower = text.lower()
        return any(phrase in text_lower for phrase in rejection_phrases)

    # --------------------------------------------------------------------------
    # СТАДИЯ 1: запрос описаний объектов и формирование сцены
    # --------------------------------------------------------------------------
    def _stage1_request_descriptions(self, retry_count=0):
        # Проверка, включена ли стадия
        if not self.main_app.enabled_stages.get("stage1_request_descriptions", True):
            self._log_debug("STAGE1_SKIPPED", "Stage1 disabled")
            self._stage2_validate_scene()
            return

        self._log_debug(f"=== STAGE1: request_descriptions (attempt {retry_count+1}) ===")
        self._display_system(f"🔍 Этап 1/10: Определение объектов сцены (попытка {retry_count+1})...\n")
        if self.generation_start_time:
            elapsed = time.time() - self.generation_start_time
            self._log_debug(f"STAGE1 start at {elapsed:.2f}s")

        if retry_count > 0:
            self.stage_data["descriptions"] = {}
            self.stage_data["scene_location_id"] = None
            self.stage_data["scene_character_ids"] = []
            self.stage_data["scene_item_ids"] = []
            self.stage_data["scene_summary"] = ""

        objects_text = []
        for lid in self.main_app.current_profile.enabled_locations:
            loc = self.main_app.locations.get(lid)
            if loc:
                objects_text.append(f"Локация: {lid} - {loc.name}")
        for cid in self.main_app.current_profile.enabled_characters:
            char = self.main_app.characters.get(cid)
            if char:
                objects_text.append(f"Персонаж: {cid} - {char.name}{' (ИГРОК)' if char.is_player else ''}")
        for iid in self.main_app.current_profile.enabled_items:
            item = self.main_app.items.get(iid)
            if item:
                objects_text.append(f"Предмет: {iid} - {item.name}")
        available = "\n".join(objects_text) if objects_text else "Нет доступных объектов."

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_request_descriptions")
        hint = "\n\nВАЖНО: Если у тебя не получается вызвать функцию confirm_scene, напиши её в тексте в формате: confirm_scene(location_id='ID', character_ids=['ID1','ID2'], item_ids=['ID1'])"
        main_prompt = prompt_template.format(
            user_message=self.stage_data["user_message"],
            available_objects=available
        ) + hint
        system_messages = self.main_app._build_context_messages(
            stage_name="stage1_request_descriptions",
            main_prompt=main_prompt
        )
        messages = [
            {"role": "user", "content": f"Сообщение игрока: {self.stage_data['user_message']}"}
        ] + system_messages

        self._send_request(
            messages,
            lambda tc, cont, extra: self._after_stage1_descriptions(tc, cont, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_request_descriptions",
            show_in_thinking=True
        )

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

        all_ids = []
        if location_id:
            all_ids.append(location_id)
        all_ids.extend(character_ids)
        all_ids.extend(item_ids)

        if all_ids:
            self._display_system(f"📦 Запрос описаний для {len(all_ids)} объектов...\n")
            self._fetch_descriptions_async(all_ids, 0, self._stage2_validate_scene)
        else:
            self._stage2_validate_scene()

    def _after_stage1_descriptions(self, tool_calls, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_debug("AFTER stage1_descriptions", f"tool_calls: {tool_calls}\ncontent: {content[:500] if content else ''}")

        confirm_call = None
        for tc in tool_calls:
            if tc["function"]["name"] == "confirm_scene":
                confirm_call = tc
                break

        if not confirm_call and content:
            parsed_calls = self._try_parse_tool_calls_from_text(content, expected_func_names=["confirm_scene"])
            if parsed_calls:
                confirm_call = parsed_calls[0]
                self._log_debug("PARSED_CONFIRM_SCENE", f"Extracted from text: {confirm_call}")
                self._display_system("📝 Извлёк вызов confirm_scene из текста ответа модели.\n")

        if confirm_call:
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
                self._display_system(f"✅ Сцена сгенерирована моделью:\n{summary}\n")

                all_ids = []
                if location_id:
                    all_ids.append(location_id)
                all_ids.extend(character_ids)
                all_ids.extend(item_ids)

                if all_ids:
                    self._display_system(f"📦 Запрос описаний для {len(all_ids)} объектов...\n")
                    self._fetch_descriptions_async(all_ids, 0, self._stage2_validate_scene)
                else:
                    self._display_system("✅ Все описания объектов получены. Модель приступает к валидации сцены.\n")
                    self._stage2_validate_scene()
                return
            except Exception as e:
                self._log_debug("ERROR", f"confirm_scene parse error: {e}")
                if retry_count < 2:
                    self._display_error(f"⚠️ Техническая ошибка при обработке confirm_scene: {e}. Повтор ({retry_count+1}/2)...\n")
                    self._stage1_request_descriptions(retry_count+1)
                    return
                else:
                    self._display_error(f"⚠️ Техническая ошибка после 3 попыток. Продолжаем с последней полученной сценой (если есть).\n")
                    if self.stage_data["scene_location_id"] or self.stage_data["scene_character_ids"]:
                        all_ids = []
                        if self.stage_data["scene_location_id"]:
                            all_ids.append(self.stage_data["scene_location_id"])
                        all_ids.extend(self.stage_data["scene_character_ids"])
                        all_ids.extend(self.stage_data["scene_item_ids"])
                        if all_ids:
                            self._fetch_descriptions_async(all_ids, 0, self._stage2_validate_scene)
                        else:
                            self._stage2_validate_scene()
                        return
                    else:
                        self._create_default_scene()
                        return

        if retry_count >= 2:
            self._display_system("⚠️ Модель не вызвала confirm_scene после 3 попыток. Создаём сцену по умолчанию.\n")
            self._create_default_scene()
            return

        if self._is_model_rejection(content):
            self._display_system(
                f"⚠️ Модель отклонила сцену. Причина:\n{content[:300]}\n"
                "Создаём сцену по умолчанию.\n"
            )
            self._create_default_scene()
            return

        if retry_count < 2:
            self._display_error(
                f"⚠️ Модель не вызвала confirm_scene. Повторная попытка ({retry_count+1}/2)...\n"
                f"Ответ модели: {content[:200] if content else 'пустой ответ'}\n"
            )
            self._stage1_request_descriptions(retry_count+1)
        else:
            self._display_error("❌ Модель не вызвала confirm_scene после 3 попыток. Создаём сцену по умолчанию.\n")
            self._create_default_scene()

    # --------------------------------------------------------------------------
    # Асинхронное получение описаний объектов
    # --------------------------------------------------------------------------
    def _fetch_descriptions_async(self, obj_ids: List[str], index: int, on_complete: Callable):
        if index >= len(obj_ids):
            self._display_system("✅ Все описания объектов получены.\n")
            self._display_system("🔍 Модель анализирует полученные описания...\n")
            on_complete()
            return

        obj_id = obj_ids[index]
        self._display_system(f"📦 Получение описания для {obj_id}...\n")
        self.main_app.update_idletasks()

        def fetch_in_thread():
            try:
                desc = self._get_object_description_with_local(obj_id)
                self.main_app.after(0, lambda: self._on_description_fetched(obj_id, desc, obj_ids, index + 1, on_complete))
            except Exception as e:
                error_msg = str(e)
                self._log_debug("ERROR", f"Ошибка получения описания {obj_id}: {error_msg}")
                self.main_app.after(0, lambda: self._on_description_fetched(obj_id, f"Ошибка: {error_msg}", obj_ids, index + 1, on_complete))

        threading.Thread(target=fetch_in_thread, daemon=True).start()

    def _on_description_fetched(self, obj_id: str, description: str, obj_ids: List[str], next_index: int, on_complete: Callable):
        self.stage_data["descriptions"][obj_id] = description
        self._display_system(f"✅ Описание {obj_id} получено.\n")
        self._display_system(f"📄 Содержание: {description[:200]}...\n\n")
        self.main_app.update_idletasks()
        self._fetch_descriptions_async(obj_ids, next_index, on_complete)

    # --------------------------------------------------------------------------
    # СТАДИЯ 2: валидация сцены
    # --------------------------------------------------------------------------
    def _stage2_validate_scene(self, retry_count=0):
        # Проверка, включена ли стадия
        if not self.main_app.enabled_stages.get("stage1_validate_scene", True):
            self._log_debug("STAGE2_SKIPPED", "Stage2 disabled")
            self._stage3_truth_check()
            return

        self._log_debug(f"=== STAGE2: validate_scene (attempt {retry_count+1}) ===")
        self._display_system(f"🔍 Этап 2/10: Валидация сцены (попытка {retry_count+1})...\n")
        if self.generation_start_time:
            elapsed = time.time() - self.generation_start_time
            self._log_debug(f"STAGE1 start at {elapsed:.2f}s")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_validate_scene")
        main_prompt = prompt_template.format(
            scene_summary=self.stage_data["scene_summary"],
            descriptions=descriptions_text,
            user_message=self.stage_data["user_message"]
        )
        system_messages = self.main_app._build_context_messages(
            stage_name="stage1_validate_scene",
            main_prompt=main_prompt
        )
        messages = [
            {"role": "user", "content": f"Проверь корректность сцены для сообщения: {self.stage_data['user_message']}"}
        ] + system_messages

        self._send_request(
            messages,
            lambda tc, cont, extra: self._after_stage2_validate_scene(tc, cont, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_validate_scene",
            show_in_thinking=True
        )

    def _after_stage2_validate_scene(self, tool_calls, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_debug("AFTER stage2_validate_scene", f"tool_calls: {tool_calls}")

        report_call = None
        for tc in tool_calls:
            if tc["function"]["name"] == "report_validation_result":
                report_call = tc
                break

        if not report_call and content:
            parsed = self._try_parse_tool_calls_from_text(content, expected_func_names=["report_validation_result"])
            if parsed:
                report_call = parsed[0]
                self._log_debug("PARSED_VALIDATION", f"Extracted: {report_call}")

        if not report_call:
            if retry_count < 2:
                self._display_error(f"⚠️ Модель не вызвала report_validation_result. Повтор ({retry_count+1}/2)...\n")
                self._stage2_validate_scene(retry_count+1)
                return
            else:
                self._display_system("⚠️ Модель не вызвала report_validation_result после 3 попыток. Считаем сцену валидной.\n")
                self._stage3_truth_check()
                return

        try:
            args = json.loads(report_call["function"]["arguments"])
            valid = args.get("valid", False)
            feedback = args.get("feedback", "")
            if valid:
                self._display_system("✅ Сцена успешно прошла валидацию.\n")
                self._stage3_truth_check()
            else:
                self._display_system(f"❌ Сцена не прошла валидацию. Причина: {feedback}\n")
                self._retry_scene_generation()
        except Exception as e:
            self._log_debug("ERROR", f"report_validation_result parse error: {e}")
            if retry_count < 2:
                self._display_error(f"⚠️ Ошибка обработки report_validation_result: {e}. Повтор ({retry_count+1}/2)...\n")
                self._stage2_validate_scene(retry_count+1)
            else:
                self._display_system(f"⚠️ Ошибка после 3 попыток: {e}. Считаем сцену валидной.\n")
                self._stage3_truth_check()

    def _retry_scene_generation(self):
        retry_key = "scene_generation_retries"
        current = self.stage_data.get(retry_key, 0)
        if current < 2:
            self.stage_data[retry_key] = current + 1
            self._display_system(f"🔄 Повторная генерация сцены (попытка {current+1}/2)...\n")
            self._stage1_request_descriptions(retry_count=current+1)
        else:
            self._display_system("⚠️ Сцена не прошла валидацию после 3 попыток. Продолжаем с текущей сценой.\n")
            self._stage3_truth_check()

    # --------------------------------------------------------------------------
    # СТАДИЯ 3: проверка правдивости
    # --------------------------------------------------------------------------
    def _stage3_truth_check(self, retry_count=0):
        # Проверка, включена ли стадия
        if not self.main_app.enabled_stages.get("stage1_truth_check", True):
            self._log_debug("STAGE3_SKIPPED", "Stage3 disabled")
            self._stage4_player_action()
            return

        self._log_debug(f"=== STAGE3: truth_check (attempt {retry_count+1}) ===")
        self._display_system(f"🔍 Этап 3/10: Проверка правдивости сообщения (попытка {retry_count+1})...\n")
        if self.generation_start_time:
            elapsed = time.time() - self.generation_start_time
            self._log_debug(f"STAGE1 start at {elapsed:.2f}s")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_truth_check")
        main_prompt = prompt_template.format(
            user_message=self.stage_data["user_message"],
            descriptions=descriptions_text
        )
        system_messages = self.main_app._build_context_messages(
            stage_name="stage1_truth_check",
            main_prompt=main_prompt
        )
        messages = [
            {"role": "user", "content": f"Проверь сообщение игрока на правдивость: {self.stage_data['user_message']}"}
        ] + system_messages

        self._send_request(
            messages,
            lambda tc, cont, extra: self._after_stage3_truth_check(tc, cont, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_truth_check",
            show_in_thinking=True
        )

    def _after_stage3_truth_check(self, tool_calls, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_debug("AFTER stage3_truth_check", f"tool_calls: {tool_calls}")

        report_call = None
        for tc in tool_calls:
            if tc["function"]["name"] == "report_truth_check":
                report_call = tc
                break

        if not report_call and content:
            parsed = self._try_parse_tool_calls_from_text(content, expected_func_names=["report_truth_check"])
            if parsed:
                report_call = parsed[0]

        if not report_call:
            if retry_count < 2:
                self._display_error(f"⚠️ Модель не вызвала report_truth_check. Повтор ({retry_count+1}/2)...\n")
                self._stage3_truth_check(retry_count+1)
                return
            else:
                self._display_system("⚠️ Модель не вызвала report_truth_check после 3 попыток. Продолжаем с исходным сообщением.\n")
                self.stage_data["truth_violation"] = ""
                self._stage4_player_action()
                return

        try:
            args = json.loads(report_call["function"]["arguments"])
            violation = args.get("violation", "")
            edited_message = args.get("edited_message", "")
            self.stage_data["truth_violation"] = violation
            if edited_message:
                self.stage_data["user_message"] = edited_message
                self._display_system(f"✏️ Сообщение игрока отредактировано моделью: '{edited_message}'\n")
            if violation:
                self._display_system(f"⚠️ Обнаружено нарушение: {violation[:200]}...\n")
            else:
                self._display_system("✅ Сообщение игрока не противоречит известным фактам.\n")
            self._stage4_player_action()
        except Exception as e:
            self._log_debug("ERROR", f"report_truth_check parse error: {e}")
            if retry_count < 2:
                self._display_error(f"⚠️ Ошибка обработки report_truth_check: {e}. Повтор ({retry_count+1}/2)...\n")
                self._stage3_truth_check(retry_count+1)
            else:
                self._display_system(f"⚠️ Ошибка после 3 попыток: {e}. Продолжаем с исходным сообщением.\n")
                self.stage_data["truth_violation"] = ""
                self._stage4_player_action()

    # --------------------------------------------------------------------------
    # СТАДИЯ 4: действие игрока
    # --------------------------------------------------------------------------
    def _stage4_player_action(self, retry_count=0):
        # Проверка, включена ли стадия
        if not self.main_app.enabled_stages.get("stage1_player_action", True):
            self._log_debug("STAGE4_SKIPPED", "Stage4 disabled")
            self._stage5_random_event_determine()
            return

        self._log_debug(f"=== STAGE4: player_action (attempt {retry_count+1}) ===")
        self._display_system(f"🎲 Этап 4/10: Обработка действия игрока (попытка {retry_count+1})...\n")
        if self.generation_start_time:
            elapsed = time.time() - self.generation_start_time
            self._log_debug(f"STAGE1 start at {elapsed:.2f}s")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        dice_rules = self.main_app.prompt_manager.get_prompt_content("dice_rules")
        violation_text = self.stage_data.get("truth_violation", "")
        violation_section = f"\nВНИМАНИЕ: Игрок попытался смошенничать или противоречить фактам:\n{violation_text}\n" if violation_text else ""
        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_player_action")
        main_prompt = prompt_template.format(
            user_message=self.stage_data["user_message"],
            descriptions=descriptions_text,
            dice_rules=dice_rules,
            truth_violation=violation_section
        )
        system_messages = self.main_app._build_context_messages(
            stage_name="stage1_player_action",
            main_prompt=main_prompt
        )
        messages = [
            {"role": "user", "content": f"Игрок хочет: {self.stage_data['user_message']}. Вызови roll_dice(dice_type='d20'), получи результат, опиши действие и вызови report_player_action. Учти информацию о нарушении, если она есть."}
        ] + system_messages

        self._send_request(
            messages,
            lambda tc, cont, extra: self._after_stage4_player_action(tc, cont, extra),
            extra={"retry_count": retry_count},
            expect_tool_calls=True,
            stage_name="stage1_player_action",
            show_in_thinking=True
        )

    def _after_stage4_player_action(self, tool_calls, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_debug("AFTER stage4_player_action", f"tool_calls: {tool_calls}")

        report_call = None
        for tc in tool_calls:
            if tc["function"]["name"] == "report_player_action":
                report_call = tc
                break

        if not report_call and content:
            parsed = self._try_parse_tool_calls_from_text(content, expected_func_names=["report_player_action"])
            if parsed:
                report_call = parsed[0]

        if not report_call:
            if retry_count < 2:
                self._display_error(f"⚠️ Модель не вызвала report_player_action. Повтор ({retry_count+1}/2)...\n")
                self._stage4_player_action(retry_count+1)
                return
            else:
                self._display_system("⚠️ Модель не вызвала report_player_action после 3 попыток. Используем действие по умолчанию.\n")
                self.stage_data["player_action_dice"] = 10
                self.stage_data["player_action_desc"] = "Игрок действует осторожно, но результат не очевиден."
                self._stage5_random_event_determine()
                return

        try:
            args = json.loads(report_call["function"]["arguments"])
            dice_value = args.get("dice_value")
            description = args.get("description", "")
            self.stage_data["player_action_dice"] = dice_value
            self.stage_data["player_action_desc"] = description
            self._display_system(f"🎲 Бросок d20: {dice_value}\n")
            self._display_system(f"✍️ Результат: {description[:100]}...\n")
            self._stage5_random_event_determine()
        except Exception as e:
            self._log_debug("ERROR", f"report_player_action parse error: {e}")
            if retry_count < 2:
                self._display_error(f"⚠️ Ошибка обработки report_player_action: {e}. Повтор ({retry_count+1}/2)...\n")
                self._stage4_player_action(retry_count+1)
            else:
                self._display_system(f"⚠️ Ошибка после 3 попыток: {e}. Используем действие по умолчанию.\n")
                self.stage_data["player_action_dice"] = 10
                self.stage_data["player_action_desc"] = "Игрок действует осторожно, но результат не очевиден."
                self._stage5_random_event_determine()

    # --------------------------------------------------------------------------
    # СТАДИЯ 5: определение случайного события (только d100)
    # --------------------------------------------------------------------------
    def _stage5_random_event_determine(self, retry_count=0):
        # Проверка, включена ли стадия
        if not self.main_app.enabled_stages.get("stage1_random_event", True):
            self._log_debug("STAGE5_SKIPPED", "Stage5 disabled")
            self._stage7_process_npcs()
            return

        self._log_debug(f"=== STAGE5: random_event_determine (attempt {retry_count+1}) ===")
        self._display_system(f"🎲 Этап 5/10: Проверка случайного события (бросок d100) (попытка {retry_count+1})...\n")
        if self.generation_start_time:
            elapsed = time.time() - self.generation_start_time
            self._log_debug(f"STAGE1 start at {elapsed:.2f}s")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_random_event")
        main_prompt = prompt_template.format(
            descriptions=descriptions_text,
            player_action=self.stage_data["player_action_desc"]
        )
        main_prompt += "\n\nВАЖНО: Сейчас нужно ТОЛЬКО определить, произошло ли событие. Вызови roll_dice('d100'), затем report_random_event с event_occurred=true/false. НЕ описывай событие и НЕ бросай d20 на этом этапе."
        system_messages = self.main_app._build_context_messages(
            stage_name="stage1_random_event",
            main_prompt=main_prompt
        )
        messages = [
            {"role": "user", "content": f"Проверь случайное событие. Вызови roll_dice('d100'), затем report_random_event с event_occurred."}
        ] + system_messages

        self._send_request(
            messages,
            lambda tc, cont, extra: self._after_stage5_random_event_determine(tc, cont, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_random_event",
            show_in_thinking=True
        )

    def _after_stage5_random_event_determine(self, tool_calls, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_debug("AFTER stage5_random_event_determine", f"tool_calls: {tool_calls}")

        report_call = None
        for tc in tool_calls:
            if tc["function"]["name"] == "report_random_event":
                report_call = tc
                break

        if not report_call and content:
            parsed = self._try_parse_tool_calls_from_text(content, expected_func_names=["report_random_event"])
            if parsed:
                report_call = parsed[0]

        if not report_call:
            if self._try_extract_event_occurred_from_text(content):
                self._display_system("✅ Случайное событие (факт) извлечено из текста.\n")
                if self.stage_data.get("event_occurred"):
                    self._stage5_random_event_details(retry_count=0)
                else:
                    self._stage7_process_npcs()
                return
            if retry_count < 2:
                self._display_error(f"⚠️ Модель не вызвала report_random_event. Повтор ({retry_count+1}/2)...\n")
                self._stage5_random_event_determine(retry_count+1)
                return
            else:
                self._display_system("⚠️ Модель не вызвала report_random_event после 3 попыток. Событие считается отсутствующим.\n")
                self.stage_data["event_occurred"] = False
                self.stage_data["event_desc"] = ""
                self.stage_data["event_dice"] = None
                self._stage7_process_npcs()
                return

        try:
            args = json.loads(report_call["function"]["arguments"])
            dice_value = args.get("dice_value")
            event_occurred = args.get("event_occurred", False)
            self.stage_data["event_occurred"] = event_occurred
            self.stage_data["event_dice"] = dice_value
            if event_occurred:
                self._display_system(f"✨ Случайное событие произошло! (d100={dice_value})\n")
                self._stage5_random_event_details(retry_count=0)
            else:
                self._display_system(f"✅ Случайное событие не произошло. (d100={dice_value})\n")
                self._stage7_process_npcs()
        except Exception as e:
            self._log_debug("ERROR", f"report_random_event parse error: {e}")
            if retry_count < 2:
                self._display_error(f"⚠️ Ошибка обработки report_random_event: {e}. Повтор ({retry_count+1}/2)...\n")
                self._stage5_random_event_determine(retry_count+1)
            else:
                self._display_system(f"⚠️ Ошибка после 3 попыток: {e}. Событие считается отсутствующим.\n")
                self.stage_data["event_occurred"] = False
                self.stage_data["event_desc"] = ""
                self._stage7_process_npcs()

    def _try_extract_event_occurred_from_text(self, content: str) -> bool:
        if not content:
            return False
        d100_match = re.search(r'd100[^\d]*(\d{1,3})', content, re.IGNORECASE)
        no_event_keywords = ["не произошло", "не случилось", "ничего не", "события нет", "не было"]
        event_occurred = not any(kw in content.lower() for kw in no_event_keywords)
        if d100_match:
            dice_val = int(d100_match.group(1))
            self.stage_data["event_dice"] = dice_val
            self.stage_data["event_occurred"] = event_occurred
            return True
        return False

    # --------------------------------------------------------------------------
    # СТАДИЯ 5.1 и 5.2: детали события
    # --------------------------------------------------------------------------
    def _stage5_random_event_details(self, retry_count=0):
        # Эта часть не отключается отдельно, она следует за stage1_random_event
        self._log_debug(f"=== STAGE5.1: random_event_details (attempt {retry_count+1}) ===")
        self._display_system(f"✨ Этап 5.1/10: Запрос дополнительных объектов для события (попытка {retry_count+1})...\n")
        if self.generation_start_time:
            elapsed = time.time() - self.generation_start_time
            self._log_debug(f"STAGE1 start at {elapsed:.2f}s")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_random_event_request_objects")
        main_prompt = prompt_template.format(
            event_dice=self.stage_data['event_dice'],
            descriptions=descriptions_text,
            player_action=self.stage_data['player_action_desc'],
            available_objects=self._get_available_objects_list()
        )
        system_messages = self.main_app._build_context_messages(
            stage_name="stage1_random_event_request_objects",
            main_prompt=main_prompt
        )
        messages = [{"role": "user", "content": "Опиши случайное событие."}] + system_messages

        self._send_request(
            messages,
            lambda tc, cont, extra: self._after_stage5_random_event_details(tc, cont, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_random_event_request_objects",
            expect_tool_calls=True,
            show_in_thinking=True
        )

    def _after_stage5_random_event_details(self, tool_calls, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_debug("AFTER stage5_random_event_details", f"tool_calls: {tool_calls}")

        for tc in tool_calls:
            if tc["function"]["name"] == "send_object_info":
                try:
                    args = json.loads(tc["function"]["arguments"])
                    object_ids = args.get("object_ids", [])
                    result = self.main_app._handle_send_object_info({"object_ids": object_ids})
                    descriptions = result.get("descriptions", {})
                    for oid, desc in descriptions.items():
                        self.stage_data["descriptions"][oid] = desc
                        self.stage_data.setdefault("event_additional_ids", []).append(oid)
                    self._display_system(f"📦 Получены описания для {', '.join(object_ids)}\n")
                    self._continue_random_event_details_with_descriptions(retry_count)
                    return
                except Exception as e:
                    self._log_debug("ERROR", f"send_object_info in event: {e}")

        report_call = None
        for tc in tool_calls:
            if tc["function"]["name"] == "report_random_event":
                report_call = tc
                break

        if not report_call and content:
            parsed = self._try_parse_tool_calls_from_text(content, expected_func_names=["report_random_event"])
            if parsed:
                report_call = parsed[0]

        if report_call:
            try:
                args = json.loads(report_call["function"]["arguments"])
                dice_value = args.get("dice_value")
                event_desc = args.get("description", "")
                self.stage_data["event_desc"] = event_desc
                self.stage_data["event_dice"] = dice_value
                self._display_system(f"✨ Событие: {event_desc[:100]}...\n")
                if self.stage_data.get("event_additional_ids"):
                    self._stage2_validate_scene_for_event(retry_count=0)
                else:
                    self._update_associative_memory_for_event_objects()
                    self._stage7_process_npcs()
            except Exception as e:
                self._log_debug("ERROR", f"report_random_event parse error: {e}")
                if retry_count < 2:
                    self._display_error(f"⚠️ Ошибка обработки report_random_event: {e}. Повтор ({retry_count+1}/2)...\n")
                    self._stage5_random_event_details(retry_count+1)
                else:
                    self._display_system(f"⚠️ Ошибка после 3 попыток. Событие пропускается.\n")
                    self.stage_data["event_occurred"] = False
                    self.stage_data["event_desc"] = ""
                    self._stage7_process_npcs()
            return

        if content:
            desc_match = re.search(r'(?:описание|событие|произошло)[:：]\s*(.+?)(?=\n|$)', content, re.IGNORECASE)
            if desc_match:
                self.stage_data["event_desc"] = desc_match.group(1).strip()
                self._display_system(f"✨ Событие извлечено из текста: {self.stage_data['event_desc'][:100]}...\n")
                self._update_associative_memory_for_event_objects()
                self._stage7_process_npcs()
                return

        if retry_count < 2:
            self._display_error(f"⚠️ Модель не предоставила описание события. Повтор ({retry_count+1}/2)...\n")
            self._stage5_random_event_details(retry_count+1)
        else:
            self._display_system("⚠️ Модель не смогла описать событие после 3 попыток. Событие пропускается.\n")
            self.stage_data["event_occurred"] = False
            self.stage_data["event_desc"] = ""
            self._stage7_process_npcs()

    def _continue_random_event_details_with_descriptions(self, retry_count):
        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_random_event_continue")
        main_prompt = prompt_template.format(
            descriptions=descriptions_text,
            player_action=self.stage_data['player_action_desc']
        )
        system_messages = self.main_app._build_context_messages(
            stage_name="stage1_random_event_continue",
            main_prompt=main_prompt
        )
        messages = [{"role": "user", "content": "Опиши случайное событие с учётом полученных описаний."}] + system_messages

        self._send_request(
            messages,
            lambda tc, cont, extra: self._after_stage5_random_event_details(tc, cont, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_random_event_continue",
            expect_tool_calls=True,
            show_in_thinking=True
        )

    def _stage2_validate_scene_for_event(self, retry_count=0):
        self._log_debug(f"=== STAGE2 (for event): validate_scene (attempt {retry_count+1}) ===")
        self._display_system(f"🔍 Проверка новых объектов события (попытка {retry_count+1})...\n")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_validate_scene")
        main_prompt = prompt_template.format(
            scene_summary=self.stage_data["scene_summary"] + f"\nДополнительные объекты события: {', '.join(self.stage_data['event_additional_ids'])}",
            descriptions=descriptions_text,
            user_message=self.stage_data["user_message"]
        )
        system_messages = self.main_app._build_context_messages(
            stage_name="stage1_validate_scene",
            main_prompt=main_prompt
        )
        messages = [
            {"role": "user", "content": f"Проверь корректность сцены с учётом новых объектов события."}
        ] + system_messages

        self._send_request(
            messages,
            lambda tc, cont, extra: self._after_stage2_validate_scene_for_event(tc, cont, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_validate_scene",
            show_in_thinking=True
        )

    def _after_stage2_validate_scene_for_event(self, tool_calls, content, extra):
        retry_count = extra.get("retry_count", 0)
        report_call = None
        for tc in tool_calls:
            if tc["function"]["name"] == "report_validation_result":
                report_call = tc
                break
        if not report_call and content:
            parsed = self._try_parse_tool_calls_from_text(content, expected_func_names=["report_validation_result"])
            if parsed:
                report_call = parsed[0]

        if not report_call:
            if retry_count < 2:
                self._display_error(f"⚠️ Модель не вызвала report_validation_result. Повтор ({retry_count+1}/2)...\n")
                self._stage2_validate_scene_for_event(retry_count+1)
                return
            else:
                self._display_system("⚠️ Модель не ответила после 3 попыток. Продолжаем, но событие может быть некорректным.\n")
                self._update_associative_memory_for_event_objects()
                self._stage7_process_npcs()
                return

        try:
            args = json.loads(report_call["function"]["arguments"])
            valid = args.get("valid", False)
            if not valid:
                feedback = args.get("feedback", "")
                self._display_system(f"⚠️ Новые объекты события не прошли проверку: {feedback}\nСобытие отменяется.\n")
                self.stage_data["event_occurred"] = False
                self.stage_data["event_desc"] = ""
            else:
                self._display_system("✅ Новые объекты события корректны.\n")
                self._update_associative_memory_for_event_objects()
            self._stage7_process_npcs()
        except Exception as e:
            self._log_debug("ERROR", f"validate_scene_for_event parse error: {e}")
            self._update_associative_memory_for_event_objects()
            self._stage7_process_npcs()

    # --------------------------------------------------------------------------
    # СТАДИЯ 7: обработка NPC
    # --------------------------------------------------------------------------
    def _stage7_process_npcs(self, retry_count=0):
        # Проверка, включена ли стадия
        if not self.main_app.enabled_stages.get("stage2_npc_action", True):
            self._log_debug("STAGE7_SKIPPED", "Stage7 disabled")
            self._stage8_final()
            return

        self._log_debug(f"=== STAGE7: process_npcs (attempt {retry_count+1}) ===")
        self._display_system(f"🎭 Этап 7/10: Обработка NPC (попытка {retry_count+1})...\n")
        if self.generation_start_time:
            elapsed = time.time() - self.generation_start_time
            self._log_debug(f"STAGE1 start at {elapsed:.2f}s")

        npc_ids = [cid for cid in self.stage_data.get("scene_character_ids", [])
                if not self.main_app.characters.get(cid, Character(is_player=False)).is_player]

        if not npc_ids:
            self._display_system("Нет NPC в сцене. Переход к финальному этапу.\n")
            self._stage8_final()
            return

        if not self.stage_data["npc_actions"]:
            self.stage_data["current_npc_index"] = 0
            self.stage_data["npc_actions"] = {}

        if self.stage_data["current_npc_index"] >= len(npc_ids):
            self._display_system("✅ Все NPC обработаны. Переход к финальному этапу.\n")
            self._stage8_final()
            return

        npc_id = npc_ids[self.stage_data["current_npc_index"]]
        npc = self.main_app.characters.get(npc_id)
        if not npc:
            self.stage_data["current_npc_index"] += 1
            self._stage7_process_npcs()
            return

        self._log_debug(f"=== STAGE7: processing NPC {npc_id} ({npc.name}) attempt {retry_count+1} ===")
        self._display_system(f"🎭 Планирование действий NPC: {npc.name} (попытка {retry_count+1})...\n")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        player_action = self.stage_data["player_action_desc"]
        event_desc = self.stage_data["event_desc"] if self.stage_data["event_occurred"] else "Нет события"

        previous_actions_text = "Нет"
        if self.stage_data["npc_actions"]:
            lines = []
            for cid, action in self.stage_data["npc_actions"].items():
                char = self.main_app.characters.get(cid)
                if char:
                    lines.append(f"{char.name}: {action}")
            if lines:
                previous_actions_text = "\n".join(lines)

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage2_npc_action")
        main_prompt = prompt_template.format(
            npc_name=npc.name,
            npc_id=npc_id,
            descriptions=descriptions_text,
            player_action=player_action,
            event_description=event_desc,
            previous_actions=previous_actions_text
        )

        messages = [{"role": "user", "content": main_prompt}]
        self._send_request(
            messages,
            lambda tc, cont, extra: self._after_stage7_npc_action(tc, cont, extra),
            extra={"npc_id": npc_id, "retry_count": retry_count, "npc_name": npc.name},
            expect_tool_calls=False,
            stage_name="stage2_npc_action",
            show_in_thinking=True
        )

    def _after_stage7_npc_action(self, tool_calls, content, extra):
        npc_id = extra["npc_id"]
        npc_name = extra.get("npc_name", "Персонаж")
        retry_count = extra.get("retry_count", 0)

        self._log_debug(f"AFTER stage7_npc_action for {npc_id}", f"content: {content[:500] if content else ''}")

        intent = None
        if content:
            lines = content.strip().split('\n')
            thoughts = ""
            planned = ""

            for line in lines:
                lower = line.lower()
                if "думает" in lower or "мысль" in lower:
                    thoughts = line.split(':', 1)[-1].strip() if ':' in line else line
                elif "планирует" in lower or "намерен" in lower or "собирается" in lower:
                    planned = line.split(':', 1)[-1].strip() if ':' in line else line

            if not thoughts and not planned:
                sentences = re.split(r'[.!?]', content)
                sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
                if len(sentences) >= 2:
                    thoughts = sentences[0]
                    planned = sentences[1]
                elif len(sentences) == 1:
                    thoughts = sentences[0]
                    planned = "продолжает наблюдать"

            if thoughts or planned:
                intent = f"{thoughts} {planned}".strip()
            else:
                intent = content[:200].strip()

        if intent:
            bad_phrases = ["солнечный свет", "татами", "велосипед", "дверь осталась незапертой",
                        "тишина и спокойствие", "мгновение затишья", "большого пути"]
            lower_intent = intent.lower()
            if any(phrase in lower_intent for phrase in bad_phrases):
                self._log_debug("NPC_BAD_RESPONSE", f"Filtered out: {intent}")
                intent = None

        if not intent:
            if retry_count < 2:
                self._display_error(f"⚠️ Модель не предоставила корректный ответ для {npc_name}. Повтор ({retry_count+1}/2)...\n")
                self._stage7_process_npcs(retry_count + 1)
                return
            else:
                intent = f"{npc_name} задумался, но не предпринимает явных действий."
                self._display_system(f"⚠️ {npc_name} — использован ответ по умолчанию.\n")

        self.stage_data["npc_actions"][npc_id] = intent
        self._display_system(f"✍️ {npc_name}: {intent[:100]}...\n")
        self.stage_data["current_npc_index"] += 1
        self._stage7_process_npcs()

    # --------------------------------------------------------------------------
    # СТАДИЯ 8: финальное повествование
    # --------------------------------------------------------------------------
    def _stage8_final(self, retry_count=0):
        self._log_debug(f"=== STAGE8: final narration (attempt {retry_count+1}) ===")
        self._display_system(f"📖 Этап 8/10: Генерация финального ответа (попытка {retry_count+1})...\n")
        if self.generation_start_time:
            elapsed = time.time() - self.generation_start_time
            self._log_debug(f"STAGE1 start at {elapsed:.2f}s")

        location_id = self.stage_data.get("scene_location_id")
        location_desc = self.stage_data["descriptions"].get(location_id, "Локация не описана") if location_id else "Локация не определена"

        npc_actions_text = ""
        npc_ids = []
        for cid in self.stage_data.get("scene_character_ids", []):
            char = self.main_app.characters.get(cid)
            if char and not char.is_player:
                npc_ids.append(cid)
        for npc_id in npc_ids:
            npc = self.main_app.characters.get(npc_id)
            if npc and npc_id in self.stage_data["npc_actions"]:
                npc_actions_text += f"{npc.name}: {self.stage_data['npc_actions'][npc_id]}\n"

        is_game_start = self.stage_data["user_message"].startswith(("Начнем игру", "SYSTEM:"))
        if is_game_start:
            player_action_outcome = "Ты только начинаешь своё приключение."
            event_description = "Вокруг тихо и спокойно."
        else:
            player_action_outcome = self.stage_data["player_action_desc"]
            event_description = self.stage_data["event_desc"] if self.stage_data["event_occurred"] else "Ничего не произошло"

        dice_rules = self.main_app.prompt_manager.get_prompt_content("dice_rules")

        dice_results = []
        for npc_id in npc_ids:
            npc = self.main_app.characters.get(npc_id)
            if not npc:
                continue
            dice_val = self._get_next_dice_value("d20") or random.randint(1, 20)
            result_text = {1:"крит.провал",2:"провал",3:"провал",4:"провал"}.get(dice_val,
                        "успех" if 5 <= dice_val <= 15 else "большой успех" if dice_val <= 19 else "крит.успех")
            dice_results.append(f"{npc.name}: бросок d20 = {dice_val} → {result_text}")
            self.stage_data.setdefault("npc_dice", {})[npc_id] = dice_val
        dice_summary = "\n".join(dice_results) if dice_results else "Нет NPC."

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage3_final")
        prompt = prompt_template.format(
            location_desc=location_desc,
            player_action_outcome=player_action_outcome,
            event_description=event_description,
            npcs_actions=npc_actions_text,
            dice_results=dice_summary,
            dice_rules=dice_rules
        )

        messages = [{"role": "user", "content": prompt}] + self.main_app._build_context_messages(stage_name="stage3_final", main_prompt="")
        self.main_app.center_panel.start_temp_response()
        self._send_request(
            messages,
            lambda tc, cont, extra: self._after_stage8_final(tc, cont, extra),
            extra={"retry_count": retry_count},
            stage_name="stage3_final",
            use_temp=True,
            expect_tool_calls=False,
            show_in_thinking=False   # финальный ответ не в thinking
        )

    def _after_stage8_final(self, tool_calls, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_debug("AFTER stage8_final", f"content: {content[:500] if content else ''}")

        final_text = content.strip()
        if not final_text:
            if retry_count < 2:
                self._display_error("⚠️ Модель не сгенерировала ответ. Повтор...\n")
                self._stage8_final(retry_count+1)
                return
            else:
                final_text = "(Рассказчик молчит)"

        self.main_app.center_panel.clear_temp_response()
        self.main_app.center_panel.display_message(f"\nАссистент: {final_text}\n\n", "assistant")
        self.main_app.conversation_history.append({"role": "assistant", "content": final_text})
        self.stage_data["final_response"] = final_text
        self._save_current_session()
        self._stage9_summary()

    # --------------------------------------------------------------------------
    # СТАДИЯ 9: краткая выжимка
    # --------------------------------------------------------------------------
    def _stage9_summary(self, retry_count=0):
        # Проверка, включена ли стадия
        if not self.main_app.enabled_stages.get("stage4_summary", True):
            self._log_debug("STAGE9_SKIPPED", "Stage9 disabled")
            self._stage10_associative_memory()
            return

        self._log_debug(f"=== STAGE9: memory summary (attempt {retry_count+1}) ===")
        self._display_system(f"📝 Этап 9/10: Сохранение краткой памяти (попытка {retry_count+1})...\n")
        if self.generation_start_time:
            elapsed = time.time() - self.generation_start_time
            self._log_debug(f"STAGE1 start at {elapsed:.2f}s")

        last_user_msg = self.stage_data["original_user_message"]
        last_assistant_msg = self.stage_data.get("final_response", "")
        if not last_assistant_msg and self.main_app.conversation_history:
            for msg in reversed(self.main_app.conversation_history):
                if msg["role"] == "assistant":
                    last_assistant_msg = msg["content"]
                    break

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage4_summary")
        prompt = prompt_template.format(
            last_user_msg=last_user_msg,
            last_assistant_msg=last_assistant_msg
        )

        messages = [
            {"role": "system", "content": "Ты — полезный ассистент, который кратко резюмирует события."},
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
        self._log_debug("AFTER stage9_summary", f"content: {content[:200] if content else ''}")

        self.main_app.center_panel.clear_temp_response()

        summary = content.strip()
        if not summary or len(summary) > 100:
            if retry_count < 1:
                self._display_error("⚠️ Ответ слишком длинный или пустой. Повтор...\n")
                self._stage9_summary(retry_count+1)
                return
            else:
                summary = "Игрок продолжил свои действия."

        self.main_app.memory_summaries.append(summary)
        if len(self.main_app.memory_summaries) > self.main_app.max_memory_summaries:
            self.main_app.memory_summaries = self.main_app.memory_summaries[-self.main_app.max_memory_summaries:]

        self._save_current_session()
        self._display_system(f"🧠 Краткая память сохранена: {summary[:100]}...\n")
        self._stage10_associative_memory()

    # --------------------------------------------------------------------------
    # Вспомогательные методы
    # --------------------------------------------------------------------------
    def _get_available_objects_list(self) -> str:
        lines = []
        for lid in self.main_app.current_profile.enabled_locations:
            loc = self.main_app.locations.get(lid)
            if loc:
                assoc = self.main_app.get_associative_memory_for_object(lid)
                lines.append(f"Локация: {lid} - {loc.name}" + (f" ({assoc})" if assoc else ""))
        for cid in self.main_app.current_profile.enabled_characters:
            char = self.main_app.characters.get(cid)
            if char:
                assoc = self.main_app.get_associative_memory_for_object(cid)
                player_tag = " (ИГРОК)" if char.is_player else ""
                lines.append(f"Персонаж: {cid} - {char.name}{player_tag}" + (f" ({assoc})" if assoc else ""))
        for iid in self.main_app.current_profile.enabled_items:
            item = self.main_app.items.get(iid)
            if item:
                assoc = self.main_app.get_associative_memory_for_object(iid)
                lines.append(f"Предмет: {iid} - {item.name}" + (f" ({assoc})" if assoc else ""))
        return "\n".join(lines) if lines else "Нет доступных объектов."

    def _stage10_associative_memory(self, retry_count=0):
        # Проверка, включена ли стадия
        if not self.main_app.enabled_stages.get("stage10_associative_memory", True):
            self._log_debug("STAGE10_SKIPPED", "Stage10 disabled")
            self._finish_generation()
            return

        self._log_debug(f"=== STAGE10: associative memory (attempt {retry_count+1}) ===")
        self._display_system(f"🧠 Этап 10/10: Обновление ассоциативной памяти (попытка {retry_count+1})...\n")
        if self.generation_start_time:
            elapsed = time.time() - self.generation_start_time
            self._log_debug(f"STAGE1 start at {elapsed:.2f}s")

        final_response = self.stage_data.get("final_response", "")
        if not final_response:
            self._display_system("Нет финального ответа для анализа – пропускаем стадию 10.\n")
            self._finish_generation()
            return

        objects_info = []
        for oid, desc in self.stage_data["descriptions"].items():
            obj = self.main_app._get_object_by_id(oid)
            if obj:
                assoc = self.main_app.get_associative_memory_for_object(oid)
                objects_info.append(f"Объект {oid} ({obj.name}):\nОписание: {desc}\n{assoc}")
        objects_text = "\n\n".join(objects_info) if objects_info else "Нет объектов."

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage10_associative_memory")
        main_prompt = prompt_template.format(
            final_response=final_response,
            objects=objects_text
        )

        messages = [{"role": "user", "content": main_prompt}]
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
        self._log_debug("AFTER stage10_associative_memory", f"content: {content[:500] if content else ''}")

        if not content or len(content.strip()) < 5:
            if retry_count < 2:
                self._display_error("⚠️ Модель не вернула изменений. Повтор...\n")
                self._stage10_associative_memory(retry_count+1)
                return
            else:
                self._display_system("⚠️ Не удалось получить изменения. Память не обновлена.\n")
                self._finish_generation()
                return

        lines = content.strip().split('\n')
        updated = 0
        for line in lines:
            if ':' in line:
                obj_id, change = line.split(':', 1)
                obj_id = obj_id.strip()
                change = change.strip()
                if obj_id and change and len(change) > 3:
                    self.main_app.update_associative_memory(obj_id, change)
                    updated += 1
        self._display_system(f"✅ Ассоциативная память обновлена для {updated} объектов.\n")
        self._finish_generation()

    def _update_associative_memory_for_event_objects(self):
        if not self.stage_data.get("event_additional_ids"):
            return
        event_desc = self.stage_data.get("event_desc", "случайное событие")
        for obj_id in self.stage_data["event_additional_ids"]:
            change = f"Появился в результате случайного события: {event_desc[:50]}"
            self.main_app.update_associative_memory(obj_id, change)
        self._display_system(f"🧠 Ассоциативная память обновлена для {len(self.stage_data['event_additional_ids'])} объектов события.\n")