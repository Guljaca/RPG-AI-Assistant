# stage_processor.py (исправленная полная версия с отладочным выводом и выделением переменных)
import json
import random
import re
import copy
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
        "stage8_history_check",
        "stage11_validation",
        "stage12_emotions",
        "stage11_significant_changes",
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
            "scene_scenario_ids": [],
            "scene_summary": "",
            "scene_narrative": "",
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
            "emotion_map": {},
            "scene_generation_retries": 0,
            "random_event_retries": 0,
            "npc_retry_count": 0
        }
        self.stage_retries = {}
        self.dice_queue_d20 = []
        self.dice_queue_d100 = []
        self._refill_dice_queues()

        self.history_check_state = {}
        self.original_final_response = ""
        self.history_check_iteration_count = 0
        self.HISTORY_CHECK_MAX_ITERATIONS = 50

        # Режим отладки и пошаговое выполнение
        self.debug_mode = False
        self.pending_step = False
        self.pending_callback = None
        self.pending_callback_extra = None
        self.pending_stage_name = None
        self.pending_debug_inputs = None  # сохранённые входные данные для вывода после нажатия
        self.pending_state_snapshot = None  # сохранённый снимок состояния

        # История шагов для регенерации
        self.step_history = []
        self.current_step_index = -1

        self._validate_prompts()

    # ---------- Вспомогательные методы ----------
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

    def _get_retry_limit(self, stage_name: str) -> int:
        return self.main_app.stage_retry_limits.get(stage_name, 2)

    def abort(self):
        """Экстренная остановка генерации."""
        if not self.main_app.is_generating:
            return
        self.main_app.stop_generation_flag = True
        if self.pending_step:
            self.pending_step = False
            self.pending_callback = None
            self.pending_callback_extra = None
            self.pending_stage_name = None
            self.pending_debug_inputs = None
            self.pending_state_snapshot = None
            self.main_app.center_panel.set_step_button_state(False)
        self.main_app.is_generating = False
        self.main_app.center_panel.set_input_state("normal")
        self.main_app.center_panel.update_translation_button_state()
        self.main_app.current_debug_log_path = None
        self._display_system("🛑 Генерация прервана пользователем.\n")
        if hasattr(self.main_app, 'vn_frame') and self.main_app.vn_frame and self.main_app.vn_frame.winfo_viewable():
            self.main_app.vn_frame.set_freeze(False)

    def reset(self):
        self.main_app.stop_generation_flag = False
        if self.pending_step:
            self.pending_step = False
            self.pending_callback = None
            self.pending_callback_extra = None
            self.pending_stage_name = None
            self.pending_debug_inputs = None
            self.pending_state_snapshot = None
            self.main_app.center_panel.set_step_button_state(False)

    def _validate_prompts(self):
        required_prompts = [
            "stage1_request_descriptions",
            "stage1_create_scene",
            "stage1_truth_check",
            "stage1_player_action",
            "stage1_random_event",
            "stage1_random_event_continue",
            "stage1_random_event_request_objects",
            "stage1_turn_order",
            "stage1_validate_scene",
            "stage1_validate_random_event",
            "stage2_npc_action",
            "stage3_final",
            "stage4_summary",
            "stage8_history_check",
            "stage10_associative_memory",
            "stage11_validation",
            "stage11_significant_changes",
            "stage12_emotions",
            "compress_description",
            "dice_rules",
            "translator_system"
        ]
        for prompt_name in required_prompts:
            content = self.main_app.prompt_manager.get_prompt_content(prompt_name)
            if content is None or content.strip() == "":
                raise FileNotFoundError(f"Required prompt file '{prompt_name}.json' not found or empty.")

    def set_debug_mode(self, enabled: bool):
        self.debug_mode = enabled
        if not enabled:
            self.pending_step = False
            self.pending_callback = None
            self.pending_callback_extra = None
            self.pending_stage_name = None
            self.pending_debug_inputs = None
            self.pending_state_snapshot = None
            self.main_app.center_panel.set_step_button_state(False)

    def step_continue(self):
        if self.pending_step and self.pending_callback:
            # Перед вызовом колбэка выводим сохранённые состояние и входные данные
            if self.pending_state_snapshot:
                self._print_debug_section("Текущее состояние перед отправкой запроса", self.pending_state_snapshot, blank_lines_before=1, blank_lines_after=1)
            if self.pending_debug_inputs and self.pending_stage_name:
                self._print_debug_section(f"Входные данные для этапа {self.pending_stage_name}", self.pending_debug_inputs, blank_lines_before=0, blank_lines_after=1)
            cb = self.pending_callback
            extra = self.pending_callback_extra
            self.pending_step = False
            self.pending_callback = None
            self.pending_callback_extra = None
            self.pending_stage_name = None
            self.pending_debug_inputs = None
            self.pending_state_snapshot = None
            self.main_app.center_panel.set_step_button_state(False)
            cb(extra)

    def _wait_for_step(self, callback, extra=None, stage_name=None, debug_inputs=None, state_snapshot=None):
        """Приостанавливает выполнение до нажатия 'Следующий шаг'."""
        if not self.debug_mode:
            callback(extra)
            return
        if self.main_app.stop_generation_flag:
            self._display_system("🛑 Генерация остановлена. Ожидание отменено.\n")
            return
        # Сохраняем данные для вывода после нажатия
        self.pending_debug_inputs = debug_inputs
        self.pending_state_snapshot = state_snapshot
        self.pending_step = True
        self.pending_callback = callback
        self.pending_callback_extra = extra
        self.pending_stage_name = stage_name
        self.main_app.center_panel.set_step_button_state(True)

    # --------------------------------------------------------------------------
    # Отладочный вывод в требуемом формате с выделением переменных цветом
    # --------------------------------------------------------------------------
    def _print_debug_section(self, title: str, items: Dict[str, Any], blank_lines_before: int = 2, blank_lines_after: int = 1):
        """Выводит в центральную панель отформатированный блок с входными или выходными данными.
        Переменные выделяются символом '>>> ' и цветом."""
        if not self.debug_mode:
            return
        output_lines = []
        for _ in range(blank_lines_before):
            output_lines.append("")
        # Заголовок цветом (например, жёлтый)
        output_lines.append(f"=== {title} ===")
        for key, value in items.items():
            value_str = str(value)
            if len(value_str) > 500:
                value_str = value_str[:500] + "..."
            # Переменные цветом (например, зелёный)
            output_lines.append(f">>> {key}: {value_str}")
        for _ in range(blank_lines_after):
            output_lines.append("")
        # Используем разные теги для заголовка и переменных, если панель поддерживает
        # Для простоты выводим всё одним блоком, но с возможностью раскрасить в центральной панели
        # Здесь передаём обычный текст, раскраска будет в центральной панели при отображении
        self.main_app.center_panel.display_message("\n".join(output_lines), "system")

    def _get_state_snapshot(self):
        """Возвращает словарь с текущим состоянием stage_data и очередей для отладки."""
        snapshot = {}
        for key, value in self.stage_data.items():
            if value is None:
                continue
            if isinstance(value, (str, list, dict)):
                if not value:
                    continue
            if isinstance(value, str) and len(value) > 300:
                snapshot[key] = value[:300] + "..."
            else:
                snapshot[key] = value
        snapshot["dice_queue_d20"] = self.dice_queue_d20.copy()
        snapshot["dice_queue_d100"] = self.dice_queue_d100.copy()
        return snapshot

    # --------------------------------------------------------------------------
    # Сохранение чекпоинтов
    # --------------------------------------------------------------------------
    def _save_checkpoint(self, stage_name: str):
        if not self.debug_mode:
            return
        snapshot = {
            "stage": stage_name,
            "stage_data": copy.deepcopy(self.stage_data),
            "dice_queue_d20": self.dice_queue_d20.copy(),
            "dice_queue_d100": self.dice_queue_d100.copy(),
        }
        if self.current_step_index < len(self.step_history) - 1:
            self.step_history = self.step_history[:self.current_step_index + 1]
        self.step_history.append(snapshot)
        self.current_step_index += 1

    def regenerate_last_step(self):
        if not self.debug_mode:
            self._display_system("Режим отладки не включён. Перегенерация шага недоступна.\n")
            return False
        if self.current_step_index <= 0:
            self._display_system("Нет предыдущего шага для перегенерации.\n")
            return False
        self.step_history.pop()
        self.current_step_index -= 1
        prev = self.step_history[self.current_step_index]
        self.stage_data = copy.deepcopy(prev["stage_data"])
        self.dice_queue_d20 = prev["dice_queue_d20"].copy()
        self.dice_queue_d100 = prev["dice_queue_d100"].copy()
        stage_to_rerun = prev["stage"]
        self.pending_step = False
        self.pending_callback = None
        self.pending_callback_extra = None
        self.pending_stage_name = None
        self.pending_debug_inputs = None
        self.pending_state_snapshot = None
        self.main_app.center_panel.set_step_button_state(False)
        self.main_app.center_panel.clear_temp_response()
        self.main_app.center_panel.display_system_message(f"🔄 Перегенерация этапа {stage_to_rerun}...\n")
        method_name = f"_{stage_to_rerun}"
        if hasattr(self, method_name):
            getattr(self, method_name)(retry_count=0)
            return True
        else:
            self._display_system(f"❌ Неизвестный этап {stage_to_rerun}\n")
            return False

    def get_debug_state(self) -> dict:
        if not self.debug_mode:
            return {}
        return {
            "debug_mode": True,
            "stage_data": copy.deepcopy(self.stage_data),
            "dice_queue_d20": self.dice_queue_d20.copy(),
            "dice_queue_d100": self.dice_queue_d100.copy(),
            "step_history": copy.deepcopy(self.step_history),
            "current_step_index": self.current_step_index,
            "pending_stage_name": self.pending_stage_name,
            "pending_callback_name": self.pending_callback.__name__ if self.pending_callback else None,
            "pending_extra": self.pending_callback_extra,
        }

    def restore_debug_state(self, state: dict):
        if not state.get("debug_mode"):
            return
        self.debug_mode = True
        self.stage_data = copy.deepcopy(state["stage_data"])
        self.dice_queue_d20 = state["dice_queue_d20"].copy()
        self.dice_queue_d100 = state["dice_queue_d100"].copy()
        self.step_history = copy.deepcopy(state["step_history"])
        self.current_step_index = state["current_step_index"]
        self.pending_stage_name = state.get("pending_stage_name")
        self.pending_step = False
        self.pending_callback = None
        self.pending_callback_extra = None
        self.pending_debug_inputs = None
        self.pending_state_snapshot = None
        self.main_app.center_panel.set_step_button_state(False)
        self.main_app.center_panel.display_system_message("🔁 Восстановлено состояние отладки. Используйте 'Следующий шаг' для продолжения.\n")

    # --------------------------------------------------------------------------
    # Вспомогательные методы для логирования и отправки запросов
    # --------------------------------------------------------------------------
    def _safe_format(self, template: str, **kwargs) -> str:
        import re
        def replacer(match):
            key = match.group(1)
            if key in kwargs:
                return f"%%%{key}%%%"
            else:
                return f"{{{{{key}}}}}"
        pattern = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')
        template = pattern.sub(replacer, template)
        template = template.replace('{', '{{').replace('}', '}}')
        for key, value in kwargs.items():
            template = template.replace(f"%%%{key}%%%", str(value))
        return template

    def _log_debug(self, step: str, content: str = "", error: str = None):
        if self.main_app.current_debug_log_path:
            self.main_app._log_debug(step, content, error)

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

    def _send_request(self, user_data: str, callback, extra=None, stage_name: str = None,
                    use_temp: bool = False, show_in_thinking: bool = False,
                    context_data: Dict = None, temperature_override: float = None,
                    debug_inputs: Dict = None):
        """
        Отправляет запрос модели. В режиме отладки сначала выводится сообщение ожидания,
        затем после нажатия кнопки выводятся состояние и входные данные, затем отправка.
        """
        if debug_inputs is None:
            debug_inputs = {}

        if context_data is None:
            context_data = self.stage_data

        model_choice = None
        if self.main_app.use_two_models and stage_name:
            model_choice = self.main_app.stage_model_selection.get(stage_name, "primary")

        temp_override = temperature_override
        if temp_override is None and stage_name and hasattr(self.main_app, 'stage_temperature_config'):
            temp_val = self.main_app.stage_temperature_config.get(stage_name)
            if temp_val is not None:
                temp_override = float(temp_val)

        if self.main_app.stop_generation_flag:
            self._display_system("🛑 Генерация остановлена. Запрос не отправлен.\n")
            return

        # Если режим отладки и этап не из исключённых, показываем сообщение ожидания и ждём
        if self.debug_mode and stage_name not in (None, "stage10_associative_memory", "stage4_summary", "stage11_significant_changes"):
            # Сообщение ожидания с двумя пустыми строками перед ним
            self._display_system(f"\n\n⏸️ Режим отладки: ожидание нажатия 'Следующий шаг' (этап: {stage_name})\n")
            # Логируем промт
            self.main_app.center_panel.log_system_prompt(f"=== ПРОМТ ЭТАПА {stage_name} ===\n{user_data}", stage_name)
            # Сохраняем снимок состояния и входные данные для вывода после нажатия
            state_snapshot = self._get_state_snapshot()
            # Ждём кнопку, передавая сохранённые данные
            self._wait_for_step(lambda _: self._do_send_request(user_data, callback, extra, stage_name, use_temp, show_in_thinking, context_data, model_choice, temp_override),
                                extra=extra, stage_name=stage_name, debug_inputs=debug_inputs, state_snapshot=state_snapshot)
        else:
            # Не отладка или исключённый этап – выводим входные данные (без ожидания) и отправляем
            if self.debug_mode and stage_name:
                # Для исключённых этапов в отладке показываем состояние и входные данные, но без ожидания
                state_snapshot = self._get_state_snapshot()
                self._print_debug_section("Текущее состояние перед отправкой запроса", state_snapshot, blank_lines_before=1, blank_lines_after=1)
                self._print_debug_section(f"Входные данные для этапа {stage_name}", debug_inputs, blank_lines_before=0, blank_lines_after=1)
            elif stage_name and debug_inputs:
                # Обычный режим (без отладки) – только входные данные без пустых строк
                self._print_debug_section(f"Входные данные для этапа {stage_name}", debug_inputs, blank_lines_before=0, blank_lines_after=1)
            self._do_send_request(user_data, callback, extra, stage_name, use_temp, show_in_thinking, context_data, model_choice, temp_override)

    def _do_send_request(self, user_data, callback, extra, stage_name, use_temp, show_in_thinking, context_data, model_choice, temp_override):
        if self.main_app.stop_generation_flag:
            self._display_system("🛑 Генерация остановлена. Запрос не отправлен.\n")
            return
        self.main_app._send_model_request(
            user_content=user_data,
            callback=callback,
            extra=extra,
            stage_name=stage_name,
            use_temp=use_temp,
            show_in_thinking=show_in_thinking,
            context_data=context_data,
            model_choice=model_choice,
            temperature_override=temp_override
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
            last_msg = self.main_app.conversation_history[-1] if self.main_app.conversation_history else None
            if not (last_msg and last_msg["role"] == "assistant" and last_msg["content"] == final_response):
                self.main_app.center_panel.display_message(f"\n{final_response}\n\n", "assistant")
                self.main_app.conversation_history.append({"role": "assistant", "content": final_response})
                self.main_app._finalize_generation_memory_turn()
                self._save_current_session()
            else:
                self.main_app.center_panel.display_message(f"\n{final_response}\n\n", "assistant")

        if hasattr(self.main_app, 'right_panel') and self.main_app.right_panel:
            self.main_app.right_panel.refresh()

        if total_time:
            self._display_system(f"✅ Генерация завершена за {total_time:.2f} секунд.\n")

        self._update_vn_view()

        self.main_app.is_generating = False
        self.main_app.center_panel.set_input_state("normal")
        self.main_app.center_panel.update_translation_button_state()
        self.main_app.current_debug_log_path = None
        self.main_app.display_generation_memory_summary()

        if hasattr(self.main_app, 'vn_frame') and self.main_app.vn_frame and self.main_app.vn_frame.winfo_viewable():
            self.main_app.vn_frame.set_freeze(False)

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

    # --------------------------------------------------------------------------
    # Синхронное получение описаний объектов
    # --------------------------------------------------------------------------
    def _fetch_descriptions_sync(self, obj_ids: List[str]):
        for obj_id in obj_ids:
            obj_id = str(obj_id)
            self._display_system(f"📦 Получение описания для {obj_id}...\n")
            try:
                desc = self._get_object_description_with_local(obj_id)
                obj = self.main_app._get_object_by_id(obj_id)
                if obj and hasattr(obj, 'is_player') and obj.is_player:
                    if "(ИГРОК)" not in desc:
                        desc += " (ИГРОК)"
                self.stage_data["descriptions"][obj_id] = desc
                self._display_system(f"✅ Описание {obj_id} получено.\n")
            except Exception as e:
                self._display_error(f"❌ Ошибка получения описания {obj_id}: {e}\n")
                self.stage_data["descriptions"][obj_id] = f"Ошибка: {e}"
        self._display_system("✅ Все описания объектов получены.\n")

    # --------------------------------------------------------------------------
    # СТАДИЯ 1.1: запрос описаний объектов
    # --------------------------------------------------------------------------
    def _stage1_request_descriptions(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage1_request_descriptions", True):
            self._log_debug("STAGE1_SKIPPED", "Stage1 disabled")
            self._stage1_create_scene()
            return

        self._log_debug(f"=== STAGE1.1: request_descriptions (attempt {retry_count+1}) ===")
        self._display_system(f"🔍 Этап 1.1/11: Определение необходимых объектов (попытка {retry_count+1})...\n")

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
                is_player = char.is_player
                player_tag = ' (ИГРОК)' if is_player else ''
                objects_text.append(f"Персонаж: {cid} - {char.name}{player_tag}{assoc_str}")
        for iid in self.main_app.current_profile.enabled_items:
            item = self.main_app.items.get(iid)
            if item:
                assoc = self.main_app.get_associative_memory_for_object(iid)
                assoc_str = f" ({assoc})" if assoc else ""
                objects_text.append(f"Предмет: {iid} - {item.name}{assoc_str}")
        for sid in self.main_app.current_profile.enabled_scenarios:
            scen = self.main_app.scenarios.get(sid)
            if scen:
                objects_text.append(f"Сценарий: {sid} - {scen.name} (описание: {scen.description[:100]}...)")
        for eid in self.main_app.current_profile.enabled_emotions:
            em = self.main_app.emotions.get(eid)
            if em:
                objects_text.append(f"Эмоция: {eid} - {em.name}")

        available = "\n".join(objects_text) if objects_text else "Нет доступных объектов."

        max_locs = self.main_app.max_locations_per_scene
        max_chars = self.main_app.max_characters_per_scene
        max_items = self.main_app.max_items_per_scene
        max_scenarios = self.main_app.max_scenarios_per_scene

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_request_descriptions")
        if not prompt_template:
            raise FileNotFoundError("Prompt 'stage1_request_descriptions' not found.")
        user_data = self._safe_format(
            prompt_template,
            user_message=self.stage_data['user_message'],
            available_objects=available,
            max_locations=max_locs,
            max_characters=max_chars,
            max_items=max_items,
            max_scenarios=max_scenarios
        )

        extra_context = {
            "available_objects": available,
            "max_locations": max_locs,
            "max_characters": max_chars,
            "max_items": max_items,
            "max_scenarios": max_scenarios,
            "user_message": self.stage_data['user_message']
        }
        full_context = {**self.stage_data, **extra_context}

        debug_inputs = {
            "user_message": self.stage_data['user_message'],
            "available_objects": available,
            "max_locations": max_locs,
            "max_characters": max_chars,
            "max_items": max_items,
            "max_scenarios": max_scenarios
        }

        self._send_request(
            user_data=user_data,
            callback=lambda content, extra: self._after_stage1_request_descriptions(content, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_request_descriptions",
            show_in_thinking=True,
            context_data=full_context,
            debug_inputs=debug_inputs
        )

    def _after_stage1_request_descriptions(self, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_full_response("stage1_request_descriptions", content)

        tool_calls = self._try_parse_tool_calls_from_text(content, expected_func_names=["send_object_info"])
        if len(tool_calls) > 1:
            self._log_debug("WARNING", f"Найдено несколько вызовов send_object_info ({len(tool_calls)}), беру последний")
        send_call = tool_calls[-1] if tool_calls else None

        object_ids = None
        if send_call:
            try:
                args = json.loads(send_call["function"]["arguments"])
                if isinstance(args, list):
                    object_ids = args
                elif "object_ids" in args:
                    object_ids = args["object_ids"]
                elif "ids" in args:
                    object_ids = args["ids"]
                elif len(args) == 1 and isinstance(list(args.values())[0], list):
                    object_ids = list(args.values())[0]
            except Exception as e:
                self._log_debug("ERROR", f"send_object_info parse error: {e}")

        if object_ids is not None and isinstance(object_ids, list) and object_ids:
            objects_display = []
            for oid in object_ids:
                obj = self.main_app._get_object_by_id(oid)
                name = obj.name if obj else oid
                objects_display.append(f"{oid} ({name})")
            display_str = ", ".join(objects_display)
            self._display_system(f"📦 Запрошены объекты: {display_str}\n")
            self._fetch_descriptions_sync(object_ids)

            if self.debug_mode:
                output_items = {
                    "object_ids": object_ids,
                    "descriptions": self.stage_data["descriptions"]
                }
                self._print_debug_section("Выходные данные этапа stage1_request_descriptions", output_items, blank_lines_before=1, blank_lines_after=1)

            self._stage1_create_scene()
            self._save_checkpoint("stage1_request_descriptions")
            return
        else:
            self._display_error("⚠️ send_object_info вызван без корректного списка object_ids.\n")

        limit = self._get_retry_limit("stage1_request_descriptions")
        if retry_count < limit:
            self._display_error(f"⚠️ Модель не вызвала send_object_info. Повтор ({retry_count+1}/{limit})...\n")
            self._stage1_request_descriptions(retry_count+1)
        else:
            self._display_system("⚠️ Модель не запросила объекты. Создаём сцену по умолчанию.\n")
            self._create_default_scene()
            self._save_checkpoint("stage1_request_descriptions")

    def _create_default_scene(self):
        location_id = None
        if self.main_app.current_profile.enabled_locations:
            location_id = self.main_app.current_profile.enabled_locations[0]
        player_id = None
        for cid in self.main_app.current_profile.enabled_characters:
            char = self.main_app.characters.get(cid)
            if char and char.is_player:
                player_id = cid
                break
        character_ids = []
        for cid in self.main_app.current_profile.enabled_characters:
            if cid != player_id:
                character_ids.append(cid)
        if player_id:
            character_ids.insert(0, player_id)
        item_ids = self.main_app.current_profile.enabled_items[:3]
        scenario_ids = self.main_app.current_profile.enabled_scenarios[:self.main_app.max_scenarios_per_scene]

        location_id = str(location_id) if location_id else None
        character_ids = [str(cid) for cid in character_ids]
        item_ids = [str(iid) for iid in item_ids]
        scenario_ids = [str(sid) for sid in scenario_ids]

        self.stage_data["scene_location_id"] = location_id
        self.stage_data["scene_character_ids"] = character_ids
        self.stage_data["scene_item_ids"] = item_ids
        self.stage_data["scene_scenario_ids"] = scenario_ids

        all_ids = []
        if location_id:
            all_ids.append(location_id)
        all_ids.extend(character_ids)
        all_ids.extend(item_ids)
        all_ids.extend(scenario_ids)

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
        if scenario_ids:
            scen_names = []
            for sid in scenario_ids:
                scen = self.main_app.scenarios.get(sid)
                scen_names.append(f"{scen.name} (ID: {sid})" if scen else sid)
            scene_parts.append(f"Сценарии: {', '.join(scen_names)}")
        summary = "\n".join(scene_parts)
        self.stage_data["scene_summary"] = summary
        self._display_system(f"🔄 Сцена создана автоматически:\n{summary}\n")
        if all_ids:
            self._fetch_descriptions_sync(all_ids)
        self._stage1_truth_check()

    # --------------------------------------------------------------------------
    # СТАДИЯ 1.2: создание сцены
    # --------------------------------------------------------------------------
    def _stage1_create_scene(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage1_create_scene", True):
            self._log_debug("STAGE1_CREATE_SCENE_SKIPPED", "Stage1_create_scene disabled")
            self._stage1_truth_check()
            return

        self._log_debug(f"=== STAGE1.2: create_scene (attempt {retry_count+1}) ===")
        self._display_system(f"🎬 Этап 1.2/11: Создание сцены (попытка {retry_count+1})...\n")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items() if isinstance(desc, str)])
        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_create_scene")
        if not prompt_template:
            raise FileNotFoundError("Prompt 'stage1_create_scene' not found.")
        user_data = self._safe_format(
            prompt_template,
            user_message=self.stage_data['user_message'],
            descriptions=descriptions_text
        )

        extra_context = {
            "descriptions": descriptions_text,
            "user_message": self.stage_data['user_message']
        }
        full_context = {**self.stage_data, **extra_context}

        debug_inputs = {
            "user_message": self.stage_data['user_message'],
            "descriptions": descriptions_text
        }

        self._send_request(
            user_data=user_data,
            callback=lambda content, extra: self._after_stage1_create_scene(content, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_create_scene",
            show_in_thinking=True,
            context_data=full_context,
            debug_inputs=debug_inputs
        )

    def _after_stage1_create_scene(self, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_full_response("stage1_create_scene", content)

        scene_narrative = ""
        if content and "confirm_scene(" in content:
            parts = content.split("confirm_scene(", 1)
            scene_narrative = parts[0].strip()
            if scene_narrative:
                self.stage_data["scene_narrative"] = scene_narrative
                self._display_system(f"🎬 Описание сцены:\n{scene_narrative}\n")
            else:
                self._display_system("⚠️ Модель не предоставила текстового описания сцены.\n")

        tool_calls = self._try_parse_tool_calls_from_text(content, expected_func_names=["confirm_scene"])
        if len(tool_calls) > 1:
            self._log_debug("WARNING", f"Найдено несколько вызовов confirm_scene ({len(tool_calls)}), беру последний")
        confirm_call = tool_calls[-1] if tool_calls else None

        if confirm_call:
            try:
                args = json.loads(confirm_call["function"]["arguments"])
                if isinstance(args, list):
                    self._handle_confirm_scene(args)
                    if self.debug_mode:
                        output_items = {
                            "scene_location_id": self.stage_data["scene_location_id"],
                            "scene_character_ids": self.stage_data["scene_character_ids"],
                            "scene_item_ids": self.stage_data["scene_item_ids"],
                            "scene_scenario_ids": self.stage_data["scene_scenario_ids"],
                            "scene_narrative": self.stage_data.get("scene_narrative", "")
                        }
                        self._print_debug_section("Выходные данные этапа stage1_create_scene", output_items, blank_lines_before=1, blank_lines_after=1)
                    self._save_checkpoint("stage1_create_scene")
                    return
            except Exception as e:
                self._log_debug("ERROR", f"confirm_scene parse error: {e}")

        match = re.search(r'\[(l\d+(?:\s*,\s*(?:c\d+|i\d+|s\d+))*)\]', content)
        if match:
            ids_str = match.group(1)
            ids = [id.strip() for id in ids_str.split(',')]
            self._display_system("⚠️ Модель не вызвала confirm_scene, но указала ID. Использую их.\n")
            self._handle_confirm_scene(ids)
            if self.debug_mode:
                output_items = {
                    "scene_location_id": self.stage_data["scene_location_id"],
                    "scene_character_ids": self.stage_data["scene_character_ids"],
                    "scene_item_ids": self.stage_data["scene_item_ids"],
                    "scene_scenario_ids": self.stage_data["scene_scenario_ids"],
                    "scene_narrative": self.stage_data.get("scene_narrative", "")
                }
                self._print_debug_section("Выходные данные этапа stage1_create_scene", output_items, blank_lines_before=1, blank_lines_after=1)
            self._save_checkpoint("stage1_create_scene")
            return

        limit = self._get_retry_limit("stage1_create_scene")
        if retry_count < limit:
            self._display_error(f"⚠️ Модель не вызвала confirm_scene. Повтор ({retry_count+1}/{limit})...\n")
            self._stage1_create_scene(retry_count+1)
        else:
            self._display_system("⚠️ Не удалось получить confirm_scene. Создаём сцену по умолчанию.\n")
            self._create_default_scene()
            self._save_checkpoint("stage1_create_scene")

    def _handle_confirm_scene(self, obj_ids: list):
        location_id = None
        character_ids = []
        item_ids = []
        scenario_ids = []
        for obj_id in obj_ids:
            obj_id = str(obj_id)
            if obj_id.startswith('l'):
                if location_id is None:
                    location_id = obj_id
            elif obj_id.startswith('c'):
                character_ids.append(obj_id)
            elif obj_id.startswith('i'):
                item_ids.append(obj_id)
            elif obj_id.startswith('s'):
                scenario_ids.append(obj_id)

        if location_id is None and self.main_app.current_profile.enabled_locations:
            location_id = self.main_app.current_profile.enabled_locations[0]
            self._display_system(f"⚠️ Локация не указана, беру '{location_id}' по умолчанию.\n")

        player_id = None
        for cid in self.main_app.current_profile.enabled_characters:
            char = self.main_app.characters.get(cid)
            if char and char.is_player:
                player_id = cid
                break
        if player_id and player_id not in character_ids:
            character_ids.insert(0, player_id)
            self._display_system(f"➕ Добавлен игрок {player_id} в сцену.\n")

        self.stage_data["scene_location_id"] = location_id
        self.stage_data["scene_character_ids"] = character_ids
        self.stage_data["scene_item_ids"] = item_ids
        self.stage_data["scene_scenario_ids"] = scenario_ids

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
        if scenario_ids:
            scen_names = []
            for sid in scenario_ids:
                scen = self.main_app.scenarios.get(sid)
                scen_names.append(f"{scen.name} (ID: {sid})" if scen else sid)
            scene_parts.append(f"Сценарии: {', '.join(scen_names)}")
        summary = "\n".join(scene_parts)
        self.stage_data["scene_summary"] = summary
        self._display_system(f"✅ Сцена создана:\n{summary}\n")

        if not self.stage_data.get("scene_narrative"):
            self.stage_data["scene_narrative"] = summary
            self._display_system(f"⚠️ Автоматическое описание сцены (из ID):\n{summary}\n")

        self._stage1_truth_check()

    # --------------------------------------------------------------------------
    # СТАДИЯ 2: проверка правдивости
    # --------------------------------------------------------------------------
    def _stage1_truth_check(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage1_truth_check", True):
            self._log_debug("STAGE2_SKIPPED", "Stage2 (truth_check) disabled")
            self._stage1_player_action()
            return

        self._log_debug(f"=== STAGE2: truth_check (attempt {retry_count+1}) ===")
        self._display_system(f"🔍 Этап 2/11: Проверка правдивости (попытка {retry_count+1})...\n")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_truth_check")
        if not prompt_template:
            raise FileNotFoundError("Prompt 'stage1_truth_check' not found.")
        user_data = self._safe_format(
            prompt_template,
            user_message=self.stage_data['user_message'],
            descriptions=descriptions_text
        )

        extra_context = {
            "descriptions": descriptions_text,
            "user_message": self.stage_data['user_message']
        }
        full_context = {**self.stage_data, **extra_context}

        debug_inputs = {
            "user_message": self.stage_data['user_message'],
            "descriptions": descriptions_text
        }

        self._send_request(
            user_data=user_data,
            callback=lambda content, extra: self._after_stage1_truth_check(content, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_truth_check",
            show_in_thinking=True,
            context_data=full_context,
            debug_inputs=debug_inputs
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
                self._save_checkpoint("stage1_truth_check")
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

            if self.debug_mode:
                output_items = {
                    "truth_violation": violation,
                    "edited_user_message": edited if edited else "(не изменено)"
                }
                self._print_debug_section("Выходные данные этапа stage1_truth_check", output_items, blank_lines_before=1, blank_lines_after=1)

            self._stage1_player_action()
            self._save_checkpoint("stage1_truth_check")

        except Exception as e:
            self._log_debug("ERROR", f"truth_check parse error: {e}")
            limit = self._get_retry_limit("stage1_truth_check")
            if retry_count < limit:
                self._stage1_truth_check(retry_count+1)
            else:
                self.stage_data["truth_violation"] = ""
                self._stage1_player_action()
                self._save_checkpoint("stage1_truth_check")

    # --------------------------------------------------------------------------
    # СТАДИЯ 3: действие игрока
    # --------------------------------------------------------------------------
    def _stage1_player_action(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage1_player_action", True):
            self._stage1_random_event_determine()
            return

        self._log_debug(f"=== STAGE3: player_action (attempt {retry_count+1}) ===")
        self._display_system(f"🎲 Этап 3/11: Действие игрока (попытка {retry_count+1})...\n")

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
        violation_text = self.stage_data.get("truth_violation", "")
        violation_section = f"\nНарушение: {violation_text}\n" if violation_text else ""
        dice_rules = self.main_app.prompt_manager.get_prompt_content("dice_rules")

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_player_action")
        if not prompt_template:
            raise FileNotFoundError("Prompt 'stage1_player_action' not found.")
        user_data = self._safe_format(
            prompt_template,
            user_message=self.stage_data['user_message'],
            descriptions=descriptions_text,
            dice_rules=dice_rules,
            truth_violation=violation_section,
            dice_value=dice_value
        )

        extra_context = {
            "descriptions": descriptions_text,
            "user_message": self.stage_data['user_message'],
            "dice_value": dice_value,
            "dice_rules": dice_rules,
            "truth_violation": violation_section
        }
        full_context = {**self.stage_data, **extra_context}

        debug_inputs = {
            "user_message": self.stage_data['user_message'],
            "descriptions": descriptions_text,
            "dice_value": dice_value,
            "dice_rules": dice_rules,
            "truth_violation": violation_section
        }

        temp_override = 0.7
        self._send_request(
            user_data=user_data,
            callback=lambda content, extra: self._after_stage1_player_action(content, extra),
            extra={"retry_count": retry_count, "expected_dice": dice_value},
            stage_name="stage1_player_action",
            show_in_thinking=True,
            context_data=full_context,
            temperature_override=temp_override,
            debug_inputs=debug_inputs
        )

    def _after_stage1_player_action(self, content, extra):
        retry_count = extra.get("retry_count", 0)
        expected_dice = extra.get("expected_dice")

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
                if self.debug_mode:
                    output_items = {"player_action_desc": self.stage_data["player_action_desc"]}
                    self._print_debug_section("Выходные данные этапа stage1_player_action", output_items, blank_lines_before=1, blank_lines_after=1)
                self._stage1_random_event_determine()
                self._save_checkpoint("stage1_player_action")
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
            self._display_system(f"✍️ Результат: {description}\n")
            if self.debug_mode:
                output_items = {"player_action_desc": self.stage_data["player_action_desc"]}
                self._print_debug_section("Выходные данные этапа stage1_player_action", output_items, blank_lines_before=1, blank_lines_after=1)
            self._stage1_random_event_determine()
            self._save_checkpoint("stage1_player_action")
        except Exception as e:
            self._log_debug("ERROR", f"act parsing error: {e}")
            limit = self._get_retry_limit("stage1_player_action")
            if retry_count < limit:
                self._stage1_player_action(retry_count+1)
            else:
                self.stage_data["player_action_desc"] = "Действие выполнено."
                self._stage1_random_event_determine()
                self._save_checkpoint("stage1_player_action")

    # --------------------------------------------------------------------------
    # СТАДИЯ 4: определение случайного события
    # --------------------------------------------------------------------------
    def _stage1_random_event_determine(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage1_random_event_determine", True):
            self._log_debug("STAGE4_SKIPPED", "Stage4 (random_event_determine) disabled")
            self._stage2_npc_action()
            return

        self._log_debug(f"=== STAGE4: random_event (determine) (attempt {retry_count+1}) ===")
        self._display_system(f"🎲 Этап 4/11: Определение случайного события (попытка {retry_count+1})...\n")

        dice_value = self._pop_dice('d100')
        self.stage_data["event_occurrence_dice"] = dice_value
        self._display_system(f"🎲 Бросок d100: {dice_value}\n")

        event_chance = getattr(self.main_app, 'random_event_chance', 30)

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        player_action = self.stage_data["player_action_desc"]

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_random_event")
        if not prompt_template:
            raise FileNotFoundError("Prompt 'stage1_random_event' not found.")
        user_data = self._safe_format(
            prompt_template,
            player_action=player_action,
            descriptions=descriptions_text,
            dice_value=dice_value,
            event_chance=event_chance
        )

        extra_context = {
            "player_action": player_action,
            "descriptions": descriptions_text,
            "dice_value": dice_value,
            "event_chance": event_chance
        }
        full_context = {**self.stage_data, **extra_context}

        debug_inputs = {
            "player_action": player_action,
            "descriptions": descriptions_text,
            "dice_value": dice_value,
            "event_chance": event_chance
        }

        self._send_request(
            user_data=user_data,
            callback=lambda content, extra: self._after_stage1_random_event_determine(content, extra),
            extra={"retry_count": retry_count, "dice_value": dice_value, "event_chance": event_chance},
            stage_name="stage1_random_event_determine",
            show_in_thinking=True,
            context_data=full_context,
            debug_inputs=debug_inputs
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
                if self.debug_mode:
                    output_items = {"event_occurred": False}
                    self._print_debug_section("Выходные данные этапа stage1_random_event_determine", output_items, blank_lines_before=1, blank_lines_after=1)
                self._stage2_npc_action()
                self._save_checkpoint("stage1_random_event_determine")
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

            if self.debug_mode:
                output_items = {"event_occurred": event_occurred}
                self._print_debug_section("Выходные данные этапа stage1_random_event_determine", output_items, blank_lines_before=1, blank_lines_after=1)

            if event_occurred:
                self._stage1_random_event_request_objects()
            else:
                self._stage2_npc_action()
            self._save_checkpoint("stage1_random_event_determine")
        except Exception as e:
            self._log_debug("ERROR", f"report_random_event parse error: {e}")
            limit = self._get_retry_limit("stage1_random_event_determine")
            if retry_count < limit:
                self._stage1_random_event_determine(retry_count + 1)
            else:
                self.stage_data["event_occurred"] = False
                self._stage2_npc_action()
                self._save_checkpoint("stage1_random_event_determine")

    # --------------------------------------------------------------------------
    # СТАДИЯ 5.1: запрос дополнительных объектов для события
    # --------------------------------------------------------------------------
    def _stage1_random_event_request_objects(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage1_random_event_request_objects", True):
            self._log_debug("STAGE5.1_SKIPPED", "Stage5.1 (request_objects) disabled")
            self._stage1_random_event_details()
            return

        self._log_debug(f"=== STAGE5.1: request objects for event (attempt {retry_count+1}) ===")
        self._display_system(f"📦 Этап 5.1/11: Запрос объектов для события (попытка {retry_count+1})...\n")

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
                is_player = char.is_player
                player_tag = ' (ИГРОК)' if is_player else ''
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
            raise FileNotFoundError("Prompt 'stage1_random_event_request_objects' not found.")
        user_data = self._safe_format(
            prompt_template,
            event_dice=event_dice,
            player_action=player_action,
            descriptions=descriptions_text,
            available_objects=available,
            max_locations=max_locs,
            max_characters=max_chars,
            max_items=max_items
        )

        extra_context = {
            "event_dice": event_dice,
            "player_action": player_action,
            "descriptions": descriptions_text,
            "available_objects": available,
            "max_locations": max_locs,
            "max_characters": max_chars,
            "max_items": max_items
        }
        full_context = {**self.stage_data, **extra_context}

        debug_inputs = {
            "event_dice": event_dice,
            "player_action": player_action,
            "descriptions": descriptions_text,
            "available_objects": available,
            "max_locations": max_locs,
            "max_characters": max_chars,
            "max_items": max_items
        }

        self._send_request(
            user_data=user_data,
            callback=lambda content, extra: self._after_stage1_random_event_request_objects(content, extra),
            extra={"retry_count": retry_count},
            stage_name="stage1_random_event_request_objects",
            show_in_thinking=True,
            context_data=full_context,
            debug_inputs=debug_inputs
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
                    if self.debug_mode:
                        output_items = {
                            "event_additional_ids": object_ids,
                            "updated_descriptions": {oid: self.stage_data["descriptions"].get(oid) for oid in object_ids}
                        }
                        self._print_debug_section("Выходные данные этапа stage1_random_event_request_objects", output_items, blank_lines_before=1, blank_lines_after=1)
                    self._stage1_random_event_details()
                    self._save_checkpoint("stage1_random_event_request_objects")
                    return
                else:
                    self._display_error("⚠️ send_object_info вызван без корректного списка object_ids.\n")
            except Exception as e:
                self._log_debug("ERROR", f"send_object_info parse error: {e}")

        self._display_system("✅ Дополнительные объекты не требуются.\n")
        if self.debug_mode:
            output_items = {"event_additional_ids": []}
            self._print_debug_section("Выходные данные этапа stage1_random_event_request_objects", output_items, blank_lines_before=1, blank_lines_after=1)
        self._stage1_random_event_details()
        self._save_checkpoint("stage1_random_event_request_objects")

    # --------------------------------------------------------------------------
    # СТАДИЯ 5.2: описание события
    # --------------------------------------------------------------------------
    def _stage1_random_event_details(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage1_random_event_details", True):
            self._log_debug("STAGE5.2_SKIPPED", "Stage5.2 (event_details) disabled")
            self._stage2_npc_action()
            return

        self._log_debug(f"=== STAGE5.2: event details (attempt {retry_count+1}) ===")
        self._display_system(f"✨ Этап 5.2/11: Описание события (попытка {retry_count+1})...\n")

        if retry_count == 0:
            quality_dice = self._pop_dice('d20')
            self.stage_data["event_quality_dice"] = quality_dice
        else:
            quality_dice = self.stage_data.get("event_quality_dice", self._pop_dice('d20'))
        self._display_system(f"🎲 Качество события d20: {quality_dice}\n")

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage1_random_event_continue")
        if not prompt_template:
            raise FileNotFoundError("Prompt 'stage1_random_event_continue' not found.")
        user_data = self._safe_format(
            prompt_template,
            player_action=self.stage_data['player_action_desc'],
            descriptions=descriptions_text,
            dice_value=quality_dice
        )

        extra_context = {
            "player_action": self.stage_data['player_action_desc'],
            "descriptions": descriptions_text,
            "dice_value": quality_dice
        }
        full_context = {**self.stage_data, **extra_context}

        debug_inputs = {
            "player_action": self.stage_data['player_action_desc'],
            "descriptions": descriptions_text,
            "dice_value": quality_dice
        }

        self._send_request(
            user_data=user_data,
            callback=lambda content, extra: self._after_stage1_random_event_details(content, extra),
            extra={"retry_count": retry_count, "dice_value": quality_dice},
            stage_name="stage1_random_event_details",
            show_in_thinking=True,
            context_data=full_context,
            debug_inputs=debug_inputs
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
                self._display_system(f"✨ Событие: {description}\n")
                if self.debug_mode:
                    output_items = {"event_desc": description}
                    self._print_debug_section("Выходные данные этапа stage1_random_event_details", output_items, blank_lines_before=1, blank_lines_after=1)
                self._stage2_npc_action()
                self._save_checkpoint("stage1_random_event_details")
                return
            except Exception as e:
                self._log_debug("ERROR", f"event parse error: {e}")

        if content and len(content.strip()) > 5:
            full_desc = content.strip()
            self.stage_data["event_desc"] = full_desc
            self._display_system(f"⚠️ Событие (из текста без вызова):\n{full_desc}\n")
            if self.debug_mode:
                output_items = {"event_desc": full_desc}
                self._print_debug_section("Выходные данные этапа stage1_random_event_details", output_items, blank_lines_before=1, blank_lines_after=1)
            self._stage2_npc_action()
            self._save_checkpoint("stage1_random_event_details")
            return

        limit = self._get_retry_limit("stage1_random_event_details")
        if retry_count < limit:
            self._display_error(f"⚠️ Модель не описала событие. Повтор ({retry_count+1}/{limit})...\n")
            self._stage1_random_event_details(retry_count+1)
        else:
            self.stage_data["event_desc"] = "Произошло что-то неожиданное."
            self._display_system("⚠️ Событие сгенерировано автоматически.\n")
            if self.debug_mode:
                output_items = {"event_desc": self.stage_data["event_desc"]}
                self._print_debug_section("Выходные данные этапа stage1_random_event_details", output_items, blank_lines_before=1, blank_lines_after=1)
            self._stage2_npc_action()
            self._save_checkpoint("stage1_random_event_details")

    # --------------------------------------------------------------------------
    # СТАДИЯ 6: обработка NPC
    # --------------------------------------------------------------------------
    def _stage2_npc_action(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage2_npc_action", True):
            self._stage3_final()
            return

        if retry_count > 50:
            self._display_error("❌ Критическая ошибка: слишком много попыток обработки NPC.\n")
            self._stage3_final()
            return

        self._log_debug(f"=== STAGE6: NPCs (attempt {retry_count+1}) ===")
        self._display_system(f"🎭 Этап 6/11: Обработка NPC (попытка {retry_count+1})...\n")

        all_chars = self.stage_data.get("scene_character_ids", [])
        npc_ids = []
        for cid in all_chars:
            char = self.main_app.characters.get(str(cid))
            if char and not char.is_player:
                npc_ids.append(cid)
            elif char is None:
                npc_ids.append(cid)

        if not npc_ids:
            self._display_system("Нет NPC.\n")
            self._stage3_final()
            return

        if not self.stage_data.get("npc_actions"):
            self.stage_data["npc_actions"] = {}
            self.stage_data["current_npc_index"] = 0

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

        player_id = None
        player_name = "игрок"
        for cid in all_chars:
            char = self.main_app.characters.get(str(cid))
            if char and char.is_player:
                player_id = cid
                player_name = char.name
                break

        descriptions_text = "\n".join([f"{oid}: {desc}" for oid, desc in self.stage_data["descriptions"].items()])
        player_action = self.stage_data.get("user_message", "")
        event_desc = self.stage_data["event_desc"] if self.stage_data["event_occurred"] else "Нет события"

        previous = []
        for cid, act in self.stage_data["npc_actions"].items():
            ch = self.main_app.characters.get(cid)
            if ch:
                previous.append(f"{ch.name}: {act}")
        previous_text = "\n".join(previous) if previous else "Нет"

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage2_npc_action")
        if not prompt_template:
            raise FileNotFoundError("Prompt 'stage2_npc_action' not found.")
        user_data = self._safe_format(
            prompt_template,
            npc_name=npc.name,
            npc_id=npc_id,
            descriptions=descriptions_text,
            player_action=player_action,
            event_description=event_desc,
            previous_actions=previous_text
        )

        warning = f"\n\n**ВАЖНО:** Ты описываешь действие только персонажа {npc.name}. Не описывай действия, мысли или речь игрока {player_name}. Не пиши от лица игрока."
        user_data += warning

        extra_context = {
            "npc_name": npc.name,
            "npc_id": npc_id,
            "descriptions": descriptions_text,
            "player_action": player_action,
            "event_description": event_desc,
            "previous_actions": previous_text
        }
        full_context = {**self.stage_data, **extra_context}

        debug_inputs = {
            "npc_name": npc.name,
            "npc_id": npc_id,
            "descriptions": descriptions_text,
            "player_action": player_action,
            "event_description": event_desc,
            "previous_actions": previous_text
        }

        self._send_request(
            user_data=user_data,
            callback=lambda content, extra: self._after_stage2_npc_action(content, extra),
            extra={"npc_id": npc_id, "npc_name": npc.name, "retry_count": retry_count},
            stage_name="stage2_npc_action",
            show_in_thinking=True,
            context_data=full_context,
            debug_inputs=debug_inputs
        )

    def _after_stage2_npc_action(self, content, extra):
        npc_id = extra["npc_id"]
        npc_name = extra.get("npc_name", "NPC")
        retry_count = extra.get("retry_count", 0)
        self._log_debug(f"stage2_npc_action_{npc_id}", f"Content:\n{content}")

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
            if planned:
                intent = planned
            elif thoughts:
                intent = thoughts
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
        self._display_system(f"✍️ {npc_name}: {intent}\n")
        if self.debug_mode:
            output_items = {f"npc_action_{npc_id}": intent}
            self._print_debug_section(f"Выходные данные этапа stage2_npc_action для {npc_name}", output_items, blank_lines_before=1, blank_lines_after=1)
        self.stage_data["current_npc_index"] += 1
        self._stage2_npc_action(0)
        self._save_checkpoint("stage2_npc_action")

    # --------------------------------------------------------------------------
    # СТАДИЯ 7: финальный рассказ
    # --------------------------------------------------------------------------
    def _stage3_final(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage3_final", True):
            self._log_debug("STAGE7_SKIPPED", "Stage7 (final) disabled")
            self._stage8_history_check()
            return

        self._log_debug(f"=== STAGE7: final (attempt {retry_count+1}) ===")
        self._display_system(f"📖 Этап 7/11: Генерация финального ответа (попытка {retry_count+1})...\n")

        location_id = self.stage_data.get("scene_location_id")
        if location_id:
            loc_obj = self.main_app._get_object_by_id(location_id)
            loc_desc = self.stage_data["descriptions"].get(location_id, "")
            if loc_obj:
                location_full_name = f"{loc_obj.name}: {loc_desc}" if loc_desc else loc_obj.name
            else:
                location_full_name = f"{location_id}: {loc_desc}" if loc_desc else location_id
        else:
            location_full_name = "Неизвестно"

        npc_actions_lines = []
        for cid, action in self.stage_data.get("npc_actions", {}).items():
            char = self.main_app.characters.get(cid)
            name = char.name if char else cid
            npc_actions_lines.append(f"{name}: {action}")
        npc_actions_text = "\n".join(npc_actions_lines) if npc_actions_lines else "Нет активных NPC"

        event_desc = self.stage_data["event_desc"] if self.stage_data.get("event_occurred", False) else ""

        npc_dice_map = self.stage_data.get("npc_dice_map")
        if npc_dice_map is None:
            npc_dice_map = {}
            for cid in self.stage_data.get("scene_character_ids", []):
                char = self.main_app.characters.get(cid)
                if char and not char.is_player:
                    npc_dice_map[cid] = self._pop_dice('d20')
            self.stage_data["npc_dice_map"] = npc_dice_map

        npc_dice_lines = []
        for cid, dice_val in npc_dice_map.items():
            char = self.main_app.characters.get(cid)
            if char:
                npc_dice_lines.append(f"{char.name}: d20={dice_val}")
        dice_summary = "\n".join(npc_dice_lines) if npc_dice_lines else "Нет NPC"

        scenario_ids = self.stage_data.get("scene_scenario_ids", [])
        scenarios_text = ""
        if scenario_ids:
            scen_descs = []
            for sid in scenario_ids:
                scen = self.main_app.scenarios.get(sid)
                if scen:
                    scen_descs.append(f"Сценарий: {scen.name}\n{scen.description}")
            if scen_descs:
                scenarios_text = "Активные сценарии (направления повествования, не обязательны к строгому следованию):\n" + "\n\n".join(scen_descs)

        player_dice = self.stage_data.get("player_action_dice", "?")
        player_action_desc = self.stage_data.get("player_action_desc", "")
        dice_rules = self.main_app.prompt_manager.get_prompt_content("dice_rules")

        dice_val = self.stage_data.get("player_action_dice")
        if dice_val is not None:
            if dice_val == 1:
                verdict = "Критический провал"
            elif 2 <= dice_val <= 4:
                verdict = "Провал"
            elif 5 <= dice_val <= 15:
                verdict = "Успех"
            elif 16 <= dice_val <= 19:
                verdict = "Большой успех"
            elif dice_val == 20:
                verdict = "Критический успех"
            else:
                verdict = "Неизвестно"
        else:
            verdict = "Нет броска"
        self._log_debug("PLAYER_DICE_VERDICT", f"d20={dice_val} -> {verdict}")

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage3_final")
        if not prompt_template:
            raise FileNotFoundError("Prompt 'stage3_final' not found.")

        characters_context = self._get_characters_context_with_presence()

        user_data = self._safe_format(
            prompt_template,
            location_desc=location_full_name,
            event_description=event_desc,
            npcs_actions=npc_actions_text,
            dice_results=dice_summary,
            dice_rules=dice_rules,
            player_dice_value=player_dice,
            player_action_desc=player_action_desc
        )

        scene_narrative = self.stage_data.get("scene_narrative", "")
        if scene_narrative:
            user_data += f"\n\n**Контекст сцены (начало):**\n{scene_narrative}\n"

        if scenarios_text:
            user_data += "\n\n" + scenarios_text

        if not self.stage_data.get("npc_actions") and not self.stage_data.get("event_occurred"):
            user_data += "\n\n**ВАЖНО:** В этой сцене нет активных NPC и не произошло случайного события. Опиши изменение окружения или продвижение времени."

        system_styles = self._get_system_styles()
        if system_styles:
            user_data = system_styles + "\n\n" + user_data

        extra_context = {
            "location_desc": location_full_name,
            "event_description": event_desc,
            "npcs_actions": npc_actions_text,
            "dice_results": dice_summary,
            "characters_context": characters_context,
            "scenarios_text": scenarios_text,
            "dice_rules": dice_rules,
            "player_dice_value": player_dice,
            "player_action_desc": player_action_desc
        }
        full_context = {**self.stage_data, **extra_context}

        debug_inputs = {
            "location_desc": location_full_name,
            "event_description": event_desc,
            "npcs_actions": npc_actions_text,
            "dice_results": dice_summary,
            "player_dice_value": player_dice,
            "player_action_desc": player_action_desc,
            "scenarios_text": scenarios_text[:200] + "..." if len(scenarios_text) > 200 else scenarios_text
        }

        self.main_app.center_panel.start_temp_response()
        self._send_request(
            user_data=user_data,
            callback=lambda content, extra: self._after_stage3_final(content, extra),
            extra={"retry_count": retry_count},
            stage_name="stage3_final",
            use_temp=False,
            show_in_thinking=True,
            context_data=full_context,
            debug_inputs=debug_inputs
        )

    def _strip_function_wrapper(self, text: str) -> str:
        if not text:
            return text
        patterns = [
            r'^\s*check_history\(\s*\[\s*"(.*?)"\s*\]\s*\)\s*$',
            r'^\s*validate_response\(\s*\[\s*"(.*?)"\s*\]\s*\)\s*$',
            r'^\s*check_history\(\s*\[\s*\]\s*\)\s*$',
            r'^\s*validate_response\(\s*\[\s*\]\s*\)\s*$',
        ]
        for pat in patterns:
            match = re.search(pat, text, re.DOTALL)
            if match:
                if match.group(1) is not None:
                    inner = match.group(1)
                    inner = inner.replace('\\n', '\n').replace('\\"', '"')
                    return inner.strip()
                else:
                    return ""
        return text

    def _extract_check_history_content(self, text: str) -> Optional[str]:
        if not text:
            return None
        matches = list(re.finditer(r'check_history\(\s*\[\s*"(.*?)"\s*\]\s*\)', text, re.DOTALL))
        if not matches:
            return None
        last_match = matches[-1]
        inner = last_match.group(1)
        inner = inner.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
        return inner

    def _extract_validate_response_content(self, text: str) -> Optional[str]:
        if not text:
            return None
        matches = list(re.finditer(r'validate_response\(\s*\[\s*"(.*?)"\s*\]\s*\)', text, re.DOTALL))
        if not matches:
            return None
        last_match = matches[-1]
        inner = last_match.group(1)
        inner = inner.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
        return inner

    def _after_stage3_final(self, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_full_response("stage3_final", content)

        final = content.strip() if content else ""
        final = self._strip_function_wrapper(final)
        final = final.replace('\\n', '\n')

        final = re.sub(r'\b(check_history|validate_response|act|report_\w+)\s*\([^)]*\)', '', final, flags=re.DOTALL)
        final = re.sub(r'\n{3,}', '\n\n', final)

        last_assistant_msg = ""
        if self.main_app.conversation_history:
            for msg in reversed(self.main_app.conversation_history):
                if msg["role"] == "assistant":
                    last_assistant_msg = msg["content"]
                    break
        if last_assistant_msg and final.strip() == last_assistant_msg.strip():
            self._display_error("⚠️ Обнаружен повтор предыдущего ответа. Перегенерация...\n")
            limit = self._get_retry_limit("stage3_final")
            if retry_count < limit:
                self._stage3_final(retry_count+1)
                return
            else:
                final = final + " (События не изменились, но момент застыл.)"

        last_user_msg = ""
        if self.main_app.conversation_history:
            for msg in reversed(self.main_app.conversation_history):
                if msg["role"] == "user":
                    last_user_msg = msg["content"]
                    break
        if last_user_msg and final.strip() == last_user_msg.strip():
            self._display_error("⚠️ Обнаружен повтор сообщения пользователя. Перегенерация...\n")
            limit = self._get_retry_limit("stage3_final")
            if retry_count < limit:
                self._stage3_final(retry_count+1)
                return
            else:
                final = final + " (Рассказчик продолжает повествование.)"

        self.stage_data["final_response"] = final
        self.original_final_response = final

        if self.debug_mode:
            output_items = {"final_response": final}
            self._print_debug_section("Выходные данные этапа stage3_final", output_items, blank_lines_before=1, blank_lines_after=1)

        self.main_app.center_panel.clear_temp_response()

        self._stage8_history_check()
        self._save_checkpoint("stage3_final")

    # --------------------------------------------------------------------------
    # СТАДИЯ 8.1: проверка истории
    # --------------------------------------------------------------------------
    def _stage8_history_check(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage8_history_check", True):
            self._log_debug("STAGE8_HISTORY_SKIPPED", "Stage8 (history_check) disabled")
            self._stage11_validation()
            return

        self._log_debug(f"=== STAGE8.1: history_check (attempt {retry_count+1}) ===")
        self._display_system(f"📜 Этап 8.1/11: Проверка истории (попытка {retry_count+1})...\n")

        history = self.main_app.conversation_history
        pairs = []
        for i in range(len(history) - 1):
            if history[i]["role"] == "user" and history[i+1]["role"] == "assistant":
                pairs.append((history[i]["content"], history[i+1]["content"]))

        if pairs and self.stage_data.get("final_response"):
            last_pair = pairs[-1]
            if last_pair[1] == self.stage_data["final_response"]:
                pairs = pairs[:-1]

        max_history = self.main_app.stage_memory_config.get("stage8_history_check", {}).get("max_history", 10)

        if self.main_app.enabled_stages.get("stage11_significant_changes", True):
            flags = self.main_app.significant_changes_flags
            filtered_pairs = []
            for idx, pair in enumerate(pairs):
                if idx < len(flags) and flags[idx]:
                    filtered_pairs.append(pair)
            if not filtered_pairs and pairs:
                filtered_pairs = [pairs[-1]]
            if len(filtered_pairs) > max_history:
                filtered_pairs = filtered_pairs[-max_history:]
            pairs = filtered_pairs
        else:
            if len(pairs) > max_history:
                pairs = pairs[-max_history:]

        old_histories_text = ""
        for idx, (user_msg, asst_msg) in enumerate(pairs):
            old_histories_text += f"История {idx+1}:\nПользователь: {user_msg}\nАссистент: {asst_msg}\n\n"

        if not old_histories_text:
            old_histories_text = "Нет предыдущих историй."

        current_response = self.stage_data.get("final_response", "")
        if not current_response:
            self._stage11_validation()
            return

        prev_significant = "неизвестно"
        if hasattr(self.main_app, 'significant_changes_flags') and self.main_app.significant_changes_flags:
            prev_significant = "да" if self.main_app.significant_changes_flags[-1] else "нет"

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage8_history_check")
        if not prompt_template:
            raise FileNotFoundError("Prompt 'stage8_history_check' not found.")
        user_data = self._safe_format(
            prompt_template,
            assoc_memory=old_histories_text,
            new_histories=f"Новый ответ ассистента:\n{current_response}",
            significant_changes_previous=prev_significant
        )

        extra_context = {
            "old_histories": old_histories_text,
            "current_response": current_response,
            "significant_changes_previous": prev_significant
        }
        full_context = {**self.stage_data, **extra_context}

        debug_inputs = {
            "old_histories": old_histories_text[:500] + "..." if len(old_histories_text) > 500 else old_histories_text,
            "current_response": current_response[:300] + "..." if len(current_response) > 300 else current_response,
            "significant_changes_previous": prev_significant
        }

        self._send_request(
            user_data=user_data,
            callback=lambda content, extra: self._after_stage8_history_check(content, extra, retry_count),
            extra={"retry_count": retry_count},
            stage_name="stage8_history_check",
            use_temp=False,
            show_in_thinking=True,
            context_data=full_context,
            debug_inputs=debug_inputs
        )

    def _after_stage8_history_check(self, content, extra, retry_count):
        self._log_full_response("stage8_history_check", content)
        extracted = self._extract_check_history_content(content)

        if extracted is not None and extracted.strip() in ("", "исправленный текст", "исправленный текст\""):
            self._display_system("⚠️ Модель не предоставила реального исправления. Изменения отклонены.\n")
            if self.debug_mode:
                output_items = {"corrected": "(отклонено)"}
                self._print_debug_section("Выходные данные этапа stage8_history_check", output_items, blank_lines_before=1, blank_lines_after=1)
            self._stage11_validation()
            self._save_checkpoint("stage8_history_check")
            return

        if extracted is not None and extracted.strip() != "":
            corrected = extracted.replace('\\n', '\n')
            corrected = self._strip_function_wrapper(corrected)
            if self._is_valid_narrative_text(corrected) and len(corrected) > 20:
                self.stage_data["final_response"] = corrected
                self._display_system("⚠️ Ответ исправлен по результатам проверки истории.\n")
                if self.debug_mode:
                    output_items = {"final_response_after_history_check": corrected}
                    self._print_debug_section("Выходные данные этапа stage8_history_check", output_items, blank_lines_before=1, blank_lines_after=1)
            else:
                self._display_system("⚠️ Получен некорректный исправленный текст. Изменения отклонены.\n")
        else:
            self._display_system("✅ Проверка истории: всё в порядке.\n")
            if self.debug_mode:
                output_items = {"correction": "no_changes"}
                self._print_debug_section("Выходные данные этапа stage8_history_check", output_items, blank_lines_before=1, blank_lines_after=1)

        self._stage11_validation()
        self._save_checkpoint("stage8_history_check")

    # --------------------------------------------------------------------------
    # СТАДИЯ 8.2: валидация
    # --------------------------------------------------------------------------
    def _stage11_validation(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage11_validation", True):
            self._log_debug("STAGE11_SKIPPED", "Stage11 (validation) disabled")
            self._stage12_emotions()
            return

        self._log_debug(f"=== STAGE11: validation (attempt {retry_count+1}) ===")
        self._display_system(f"✅ Этап 8.2/11: Валидация результата (попытка {retry_count+1})...\n")

        final_response = self.stage_data.get("final_response", "")
        if not final_response:
            self._stage12_emotions()
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

        npc_dice_map = self.stage_data.get("npc_dice_map", {})
        npc_dice_lines = []
        for cid in self.stage_data.get('scene_character_ids', []):
            char = self.main_app.characters.get(cid)
            if char and not char.is_player:
                dice_val = npc_dice_map.get(cid, "?")
                npc_dice_lines.append(f"{char.name}: d20={dice_val}")
        dice_summary_npc = "\n".join(npc_dice_lines)

        dice_rules = self.main_app.prompt_manager.get_prompt_content("dice_rules")
        player_dice = self.stage_data.get("player_action_dice", "?")

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage11_validation")
        if not prompt_template:
            raise FileNotFoundError("Prompt 'stage11_validation' not found.")

        format_args = {
            "scene_location_id": scene_location_id,
            "scene_character_ids": scene_character_ids,
            "scene_item_ids": scene_item_ids,
            "descriptions": descriptions,
            "player_action_desc": player_action_desc,
            "player_action_dice": player_action_dice,
            "event_occurred": event_occurred,
            "event_occurrence_dice": event_occurrence_dice,
            "event_quality_dice": event_quality_dice,
            "event_desc": event_desc,
            "npc_actions": npc_actions,
            "dice_summary_npc": dice_summary_npc,
            "final_response": final_response,
            "dice_rules": dice_rules,
            "player_dice": player_dice
        }
        if "{prev_user_message}" in prompt_template:
            prev_user_msg = ""
            if self.main_app.conversation_history:
                for msg in reversed(self.main_app.conversation_history):
                    if msg["role"] == "user":
                        prev_user_msg = msg["content"]
                        break
            format_args["prev_user_message"] = prev_user_msg

        try:
            user_data = self._safe_format(prompt_template, **format_args)
        except KeyError as e:
            self._log_debug("ERROR", f"Missing key in stage11_validation format: {e}")
            user_data = prompt_template

        extra_context = format_args.copy()
        full_context = {**self.stage_data, **extra_context}

        debug_inputs = {k: (v[:300] + "..." if isinstance(v, str) and len(v) > 300 else v) for k, v in format_args.items()}

        self._send_request(
            user_data=user_data,
            callback=lambda content, extra: self._after_stage11_validation(content, extra),
            extra={"retry_count": retry_count},
            stage_name="stage11_validation",
            use_temp=False,
            show_in_thinking=True,
            context_data=full_context,
            debug_inputs=debug_inputs
        )

    def _after_stage11_validation(self, content, extra):
        retry_count = extra.get("retry_count", 0)
        max_retries = self._get_retry_limit("stage11_validation")
        self._log_full_response("stage11_validation", content)

        extracted = self._extract_validate_response_content(content)
        if extracted is not None:
            if extracted.strip() == "":
                self._display_system("✅ Валидация пройдена, ответ корректен.\n")
                if self.debug_mode:
                    output_items = {"validation_result": "passed"}
                    self._print_debug_section("Выходные данные этапа stage11_validation", output_items, blank_lines_before=1, blank_lines_after=1)
                self._stage12_emotions()
                self._save_checkpoint("stage11_validation")
                return
            else:
                corrected = extracted.replace('\\n', '\n')
                corrected = self._strip_function_wrapper(corrected)

                last_assistant_msg = ""
                if self.main_app.conversation_history:
                    for msg in reversed(self.main_app.conversation_history):
                        if msg["role"] == "assistant":
                            last_assistant_msg = msg["content"]
                            break
                if last_assistant_msg and corrected.strip() == last_assistant_msg.strip():
                    self._display_system("⚠️ Валидатор не исправил повтор. Отклоняем, перегенерация.\n")
                    if retry_count < max_retries:
                        self._stage11_validation(retry_count+1)
                        return
                    else:
                        corrected = "(Рассказчик молчит, ситуация не изменилась.)"

                if self._is_valid_narrative_text(corrected) and len(corrected) > 20:
                    forbidden = [r'ты можешь', r'можешь выбрать', r'ты видишь', r'ты чувствуешь', r'ты лежишь']
                    for p in forbidden:
                        corrected = re.sub(p, '', corrected, flags=re.IGNORECASE)
                    corrected = re.sub(r'\s+', ' ', corrected).strip()
                    self.stage_data["final_response"] = corrected
                    self._display_system("✅ Ответ исправлен по результатам валидации.\n")
                else:
                    self._display_system("⚠️ Валидатор вернул некорректный текст. Изменения отклонены.\n")
                if self.debug_mode:
                    output_items = {"validation_result": "corrected", "final_response": self.stage_data["final_response"]}
                    self._print_debug_section("Выходные данные этапа stage11_validation", output_items, blank_lines_before=1, blank_lines_after=1)
                self._stage12_emotions()
                self._save_checkpoint("stage11_validation")
                return

        cleaned = self._strip_function_wrapper(content)
        if cleaned and cleaned != content and len(cleaned) > 20:
            last_assistant_msg = ""
            if self.main_app.conversation_history:
                for msg in reversed(self.main_app.conversation_history):
                    if msg["role"] == "assistant":
                        last_assistant_msg = msg["content"]
                        break
            if last_assistant_msg and cleaned.strip() == last_assistant_msg.strip():
                self._display_system("⚠️ Очищенный текст повторяет предыдущий ответ. Перегенерация.\n")
                if retry_count < max_retries:
                    self._stage11_validation(retry_count+1)
                    return
            self.stage_data["final_response"] = cleaned
            self._display_system("✅ Ответ очищен от функций.\n")
            if self.debug_mode:
                output_items = {"validation_result": "cleaned", "final_response": cleaned}
                self._print_debug_section("Выходные данные этапа stage11_validation", output_items, blank_lines_before=1, blank_lines_after=1)
            self._stage12_emotions()
            self._save_checkpoint("stage11_validation")
            return

        if retry_count < max_retries:
            self._display_error(f"⚠️ Некорректный формат валидатора. Повтор ({retry_count+1}/{max_retries})...\n")
            self._stage11_validation(retry_count+1)
            return
        else:
            self._display_system("⚠️ Не удалось получить корректный ответ валидатора. Пропускаем.\n")
            if self.debug_mode:
                output_items = {"validation_result": "failed_retries"}
                self._print_debug_section("Выходные данные этапа stage11_validation", output_items, blank_lines_before=1, blank_lines_after=1)
            self._stage12_emotions()
            self._save_checkpoint("stage11_validation")

    # --------------------------------------------------------------------------
    # СТАДИЯ 12: эмоции
    # --------------------------------------------------------------------------
    def _stage12_emotions(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage12_emotions", True):
            self._log_debug("STAGE12_SKIPPED", "Stage12 (emotions) disabled")
            self._stage11_significant_changes()
            return

        self._log_debug(f"=== STAGE12: emotions (attempt {retry_count+1}) ===")
        self._display_system(f"😊 Этап 12/12: Определение эмоций персонажей (попытка {retry_count+1})...\n")

        character_ids = self.stage_data.get("scene_character_ids", [])
        if not character_ids:
            self._display_system("Нет персонажей для определения эмоций.\n")
            self._stage11_significant_changes()
            return

        final_response = self.stage_data.get("final_response", "")
        if not final_response:
            final_response = "Нет финального ответа."

        emotions_list = []
        for eid in self.main_app.current_profile.enabled_emotions:
            em = self.main_app.emotions.get(eid)
            if em:
                emotions_list.append(f'"{em.name}"')
        emotions_text = "[\n" + ",\n".join(emotions_list) + "\n]" if emotions_list else "[]"

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage12_emotions")
        if not prompt_template:
            raise FileNotFoundError("Prompt 'stage12_emotions' not found.")

        self._emotion_queue = character_ids.copy()
        self._emotion_results = {}
        self._emotion_retry_count = retry_count

        self._process_next_emotion()

    def _process_next_emotion(self):
        if not self._emotion_queue:
            self.stage_data["emotion_map"] = self._emotion_results
            self._display_system(f"✅ Эмоции определены: {self._emotion_results}\n")
            if self.debug_mode:
                output_items = {"emotion_map": self._emotion_results}
                self._print_debug_section("Выходные данные этапа stage12_emotions", output_items, blank_lines_before=1, blank_lines_after=1)
            self._update_vn_view()
            delattr(self, '_emotion_queue')
            delattr(self, '_emotion_results')
            delattr(self, '_emotion_retry_count')
            self._stage11_significant_changes()
            self._save_checkpoint("stage12_emotions")
            return

        cid = self._emotion_queue.pop(0)
        char = self.main_app.characters.get(cid)
        if not char:
            self._emotion_results[cid] = "Нейтрально"
            self._process_next_emotion()
            return

        final_response = self.stage_data.get("final_response", "")
        desc = self.stage_data["descriptions"].get(cid, char.description)
        if len(desc) > 300:
            desc = desc[:300] + "..."

        char_text = f"ID: {cid}\nИмя: {char.name}\nОписание: {desc}"

        emotions_list = []
        for eid in self.main_app.current_profile.enabled_emotions:
            em = self.main_app.emotions.get(eid)
            if em:
                emotions_list.append(f'"{em.name}"')
        emotions_text = "[\n" + ",\n".join(emotions_list) + "\n]" if emotions_list else "[]"

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage12_emotions")
        if not prompt_template:
            raise FileNotFoundError("Prompt 'stage12_emotions' not found.")

        user_data = self._safe_format(
            prompt_template,
            final_response=final_response,
            characters=char_text,
            available_emotions=emotions_text
        )

        extra_context = {
            "character_id": cid,
            "character_name": char.name,
            "final_response": final_response,
            "character_desc": desc
        }
        full_context = {**self.stage_data, **extra_context}

        debug_inputs = {
            "character_id": cid,
            "character_name": char.name,
            "final_response": final_response[:300] + "..." if len(final_response) > 300 else final_response,
            "character_desc": desc,
            "available_emotions": emotions_text
        }

        self._send_request(
            user_data=user_data,
            callback=lambda content, extra, cid=cid: self._after_stage12_emotions(content, extra, cid),
            extra={"retry_count": self._emotion_retry_count, "character_id": cid},
            stage_name="stage12_emotions",
            use_temp=False,
            show_in_thinking=True,
            context_data=full_context,
            debug_inputs=debug_inputs
        )

    def _after_stage12_emotions(self, content, extra, character_id):
        retry_count = extra.get("retry_count", 0)
        self._log_full_response(f"stage12_emotions_{character_id}", content)

        tool_calls = self._try_parse_tool_calls_from_text(content, expected_func_names=["report_emotions"])
        emotion = "Нейтрально"

        if tool_calls:
            report_call = tool_calls[-1]
            try:
                args = json.loads(report_call["function"]["arguments"])
                if isinstance(args, list):
                    if len(args) >= 2 and isinstance(args[0], list):
                        if args[0][0] == character_id:
                            emotion = args[0][1]
                        else:
                            emotion = args[0][1] if len(args[0]) > 1 else "Нейтрально"
                    elif len(args) >= 2:
                        if args[0] == character_id:
                            emotion = args[1]
                        else:
                            emotion = args[1] if len(args) > 1 else "Нейтрально"
                elif isinstance(args, dict):
                    if args.get("id") == character_id:
                        emotion = args.get("emotion", "Нейтрально")
                    else:
                        emotion = args.get("emotion", "Нейтрально")
                self._display_system(f"🎭 {character_id}: {emotion}\n")
            except Exception as e:
                self._log_debug("ERROR", f"report_emotions parse error for {character_id}: {e}")
                emotion = "Нейтрально"
        else:
            if "Смущение" in content:
                emotion = "Смущение"
            elif "Плач" in content:
                emotion = "Плач"
            elif "Ярость" in content or "злоба" in content:
                emotion = "Ярость, сильная злоба"
            elif "Ухмылка" in content:
                emotion = "Ухмылка"
            else:
                emotion = "Нейтрально"
            self._display_system(f"🎭 {character_id}: {emotion} (извлечено из текста)\n")

        self._emotion_results[character_id] = emotion
        self._process_next_emotion()

    # --------------------------------------------------------------------------
    # СТАДИЯ 11: значительные изменения
    # --------------------------------------------------------------------------
    def _stage11_significant_changes(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage11_significant_changes", True):
            self._log_debug("STAGE11_SIGNIFICANT_SKIPPED", "Stage11 (significant changes) disabled")
            self._stage4_summary()
            return

        self._log_debug(f"=== STAGE11: significant_changes (attempt {retry_count+1}) ===")
        self._display_system(f"🔍 Этап 11/11: Проверка значительных изменений (попытка {retry_count+1})...\n")

        history = self.main_app.conversation_history
        pairs = []
        for i in range(len(history) - 1):
            if history[i]["role"] == "user" and history[i+1]["role"] == "assistant":
                pairs.append((history[i]["content"], history[i+1]["content"]))

        if len(pairs) < 2:
            self._display_system("Недостаточно истории для проверки значительных изменений.\n")
            self._finalize_significant_changes(False)
            return

        last_user_msg = ""
        if self.main_app.conversation_history and self.main_app.conversation_history[-1]["role"] == "user":
            last_user_msg = self.main_app.conversation_history[-1]["content"]
        else:
            last_user_msg = self.stage_data.get("original_user_message", "")
        curr_pair = (last_user_msg, self.stage_data.get("final_response", ""))

        prev_pair = pairs[-2]

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage11_significant_changes")
        if not prompt_template:
            raise FileNotFoundError("Prompt 'stage11_significant_changes' not found.")

        format_args = {
            "prev_user_message": prev_pair[0],
            "prev_assistant_message": prev_pair[1],
            "curr_user_message": curr_pair[0],
            "curr_assistant_message": curr_pair[1]
        }
        try:
            user_data = self._safe_format(prompt_template, **format_args)
        except KeyError as e:
            self._log_debug("ERROR", f"Missing key in stage11_significant_changes format: {e}")
            user_data = prompt_template
            self._display_error(f"⚠️ Промт stage11_significant_changes требует отсутствующий ключ: {e}\n")

        extra_context = format_args.copy()
        full_context = {**self.stage_data, **extra_context}

        debug_inputs = {k: (v[:300] + "..." if isinstance(v, str) and len(v) > 300 else v) for k, v in format_args.items()}

        self._send_request(
            user_data=user_data,
            callback=lambda content, extra: self._after_stage11_significant_changes(content, extra),
            extra={"retry_count": retry_count},
            stage_name="stage11_significant_changes",
            use_temp=False,
            show_in_thinking=True,
            context_data=full_context,
            debug_inputs=debug_inputs
        )

    def _after_stage11_significant_changes(self, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_full_response("stage11_significant_changes", content)

        significant = False
        tool_calls = self._try_parse_tool_calls_from_text(content, expected_func_names=["report_significant_changes"])
        if tool_calls:
            try:
                args = json.loads(tool_calls[-1]["function"]["arguments"])
                if isinstance(args, list) and len(args) > 0:
                    significant = bool(args[0])
                elif isinstance(args, dict):
                    significant = args.get("significant", False)
            except Exception as e:
                self._log_debug("ERROR", f"Failed to parse report_significant_changes: {e}")
        else:
            self._log_debug("WARNING", "report_significant_changes not called, using fallback")
            content_lower = content.lower()
            if "true" in content_lower or "yes" in content_lower or "да" in content_lower:
                significant = True
            elif "false" in content_lower or "no" in content_lower or "нет" in content_lower:
                significant = False

        if self.debug_mode:
            output_items = {"significant_changes": significant}
            self._print_debug_section("Выходные данные этапа stage11_significant_changes", output_items, blank_lines_before=1, blank_lines_after=1)

        self._finalize_significant_changes(significant)
        self._save_checkpoint("stage11_significant_changes")

    def _finalize_significant_changes(self, significant: bool):
        if not hasattr(self.main_app, 'significant_changes_flags'):
            self.main_app.significant_changes_flags = []
        self.main_app.significant_changes_flags.append(significant)
        self._display_system(f"{'✅' if significant else '❌'} Значительные изменения: {'да' if significant else 'нет'}\n")
        self._stage4_summary()

    # --------------------------------------------------------------------------
    # СТАДИЯ 9: краткая память
    # --------------------------------------------------------------------------
    def _stage4_summary(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage4_summary", True):
            self._log_debug("STAGE9_SKIPPED", "Stage9 (summary) disabled")
            self._stage10_associative_memory()
            return

        self._log_debug(f"=== STAGE9: summary (attempt {retry_count+1}) ===")
        self._display_system(f"📝 Этап 9/11: Краткая память (попытка {retry_count+1})...\n")

        last_user = self.stage_data["original_user_message"]
        last_assistant = self.stage_data.get("final_response", "")
        if not last_assistant and self.main_app.conversation_history:
            for msg in reversed(self.main_app.conversation_history):
                if msg["role"] == "assistant":
                    last_assistant = msg["content"]
                    break

        prompt_template = self.main_app.prompt_manager.get_prompt_content("stage4_summary")
        if not prompt_template:
            raise FileNotFoundError("Prompt 'stage4_summary' not found.")
        user_data = self._safe_format(
            prompt_template,
            last_user_msg=last_user,
            last_assistant_msg=last_assistant
        )

        extra_context = {
            "last_user_msg": last_user,
            "last_assistant_msg": last_assistant
        }
        full_context = {**self.stage_data, **extra_context}

        debug_inputs = {
            "last_user_msg": last_user,
            "last_assistant_msg": last_assistant[:300] + "..." if len(last_assistant) > 300 else last_assistant
        }

        self._send_request(
            user_data=user_data,
            callback=lambda content, extra: self._after_stage4_summary(content, extra),
            extra={"retry_count": retry_count},
            stage_name="stage4_summary",
            use_temp=False,
            show_in_thinking=True,
            context_data=full_context,
            debug_inputs=debug_inputs
        )

    def _after_stage4_summary(self, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_full_response("stage4_summary", content)
        summary = content.strip()
        if summary and len(summary) > 10:
            self.main_app.record_added_summary(summary)
            self._display_system(f"📝 Добавлена запись в краткую память.\n")
            if self.debug_mode:
                output_items = {"summary": summary}
                self._print_debug_section("Выходные данные этапа stage4_summary", output_items, blank_lines_before=1, blank_lines_after=1)
        else:
            self._display_system("⚠️ Не удалось получить краткую память.\n")
        self._stage10_associative_memory()
        self._save_checkpoint("stage4_summary")

    # --------------------------------------------------------------------------
    # СТАДИЯ 10: ассоциативная память
    # --------------------------------------------------------------------------
    def _stage10_associative_memory(self, retry_count=0):
        if not self.main_app.enabled_stages.get("stage10_associative_memory", True) or not self.main_app.enable_associative_memory:
            self._log_debug("STAGE10_SKIPPED", "Stage10 (associative) disabled")
            self._finish_generation()
            return

        self._log_debug(f"=== STAGE10: associative (attempt {retry_count+1}) ===")
        self._display_system(f"🧠 Этап 10/11: Ассоциативная память (попытка {retry_count+1})...\n")

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
            raise FileNotFoundError("Prompt 'stage10_associative_memory' not found.")
        user_data = self._safe_format(
            prompt_template,
            final_response=final,
            objects=objects_text
        )

        extra_context = {
            "final_response": final,
            "objects": objects_text
        }
        full_context = {**self.stage_data, **extra_context}

        debug_inputs = {
            "final_response": final[:300] + "..." if len(final) > 300 else final,
            "objects": objects_text[:500] + "..." if len(objects_text) > 500 else objects_text
        }

        self._send_request(
            user_data=user_data,
            callback=lambda content, extra: self._after_stage10_associative_memory(content, extra),
            extra={"retry_count": retry_count},
            stage_name="stage10_associative_memory",
            use_temp=True,
            show_in_thinking=True,
            context_data=full_context,
            debug_inputs=debug_inputs
        )

    def _after_stage10_associative_memory(self, content, extra):
        retry_count = extra.get("retry_count", 0)
        self._log_full_response("stage10_associative_memory", content)
        if not content or len(content.strip()) < 5:
            limit = self._get_retry_limit("stage10_associative_memory")
            if retry_count < limit:
                self._display_thinking("⚠️ Повтор ассоциативной памяти...\n")
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
        self._display_thinking(f"✅ Память обновлена для {updated} объектов.\n")
        if self.debug_mode:
            output_items = {"updated_objects": updated, "changed_ids": changed_ids}
            self._print_debug_section("Выходные данные этапа stage10_associative_memory", output_items, blank_lines_before=1, blank_lines_after=1)
        self._finish_generation()
        self._save_checkpoint("stage10_associative_memory")

    # --------------------------------------------------------------------------
    # Вспомогательные методы для стилей и валидации
    # --------------------------------------------------------------------------
    def _get_system_styles(self) -> str:
        styles = []
        if hasattr(self.main_app, 'world_style_prompt') and self.main_app.world_style_prompt:
            styles.append(self.main_app.world_style_prompt)
        if hasattr(self.main_app, 'narrator_style_prompt') and self.main_app.narrator_style_prompt:
            styles.append(self.main_app.narrator_style_prompt)
        if hasattr(self.main_app, 'text_style_prompt') and self.main_app.text_style_prompt:
            styles.append(self.main_app.text_style_prompt)
        return "\n\n".join(styles) if styles else ""

    def _is_valid_narrative_text(self, text: str) -> bool:
        if not text or len(text) < 10:
            return False
        forbidden = [
            "как редактор", "я проверю", "приступим",
            "let me check", "i'm going to", "look at the history"
        ]
        lower_text = text.lower()
        if any(phrase in lower_text for phrase in forbidden):
            return False
        return True

    def _get_characters_context_with_presence(self) -> str:
        lines = []
        for cid in self.stage_data.get("scene_character_ids", []):
            char = self.main_app.characters.get(cid)
            if char and not char.is_player:
                desc = self.stage_data["descriptions"].get(cid, "Нет описания")
                if len(desc) > 300:
                    desc = desc[:300] + "..."
                lines.append(f"• {char.name} – {desc}")
        return "\n".join(lines) if lines else "Нет других персонажей."

    def _update_vn_view(self):
        if hasattr(self.main_app, 'vn_frame') and self.main_app.vn_frame and self.main_app.vn_frame.winfo_viewable():
            self.main_app.vn_frame.refresh_from_current_state()

    def restore_scene_from_session(self, session_data: dict):
        scene_keys = [
            "scene_location_id",
            "scene_character_ids",
            "scene_item_ids",
            "scene_scenario_ids",
            "descriptions",
            "scene_summary",
            "emotion_map"
        ]
        for key in scene_keys:
            if key in session_data:
                self.stage_data[key] = session_data[key]
            else:
                self.stage_data[key] = self.stage_data.get(key)

        if hasattr(self.main_app, 'vn_frame') and self.main_app.vn_frame:
            self.main_app.vn_frame.refresh_from_current_state()

    def start_generation(self, user_message: str):
        self.reset()
        self.generation_start_time = time.time()
        self._refill_dice_queues()
        self.stage_data.update({
            "user_message": user_message,
            "original_user_message": user_message,
            "descriptions": {},
            "scene_location_id": None,
            "scene_character_ids": [],
            "scene_item_ids": [],
            "scene_scenario_ids": [],
            "scene_summary": "",
            "scene_narrative": "",
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
            "emotion_map": {},
            "scene_generation_retries": 0,
            "random_event_retries": 0,
            "npc_retry_count": 0
        })
        self._stage1_request_descriptions()