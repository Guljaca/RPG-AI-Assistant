# prompt_manager.py (модифицированная версия с поддержкой локализации)
import os
import json
import sys
from typing import List, Optional
from localization import loc


class PromptManager:
    """Управляет системными промтами с учётом выбранного языка интерфейса."""
    
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
        "stage10_associative_memory",
        "dice_rules",
        "stage1_random_event_continue",
        "translator_system",
        "stage1_create_scene",
        "stage1_random_event_request_objects",
        "stage11_validation",
        "stage11_significant_changes",
        "stage12_emotions",
        "stage8_history_check"
    ]

    def __init__(self, prompts_base_dir: str = "System_Prompts"):
        self.prompts_base_dir = prompts_base_dir
        self._current_language = "ru"
        self._ensure_dir()
        self._check_required_prompts()

    def _get_prompts_dir(self) -> str:
        """Возвращает путь к папке промтов для текущего языка."""
        return os.path.join(self.prompts_base_dir, self._current_language)

    def _ensure_dir(self) -> None:
        """Создаёт папку для текущего языка, если её нет."""
        os.makedirs(self._get_prompts_dir(), exist_ok=True)

    def _check_required_prompts(self) -> None:
        """Проверяет наличие всех обязательных промтов для текущего языка."""
        missing = []
        for name in self.REQUIRED_PROMPTS:
            filepath = os.path.join(self._get_prompts_dir(), f"{name}.json")
            if not os.path.exists(filepath):
                missing.append(name)
        if missing:
            from tkinter import messagebox
            messagebox.showerror(
                loc.tr("error_prompt_initialization"),
                loc.tr("error_missing_prompts", prompts="\n".join(missing))
            )
            sys.exit(1)

    def set_language(self, lang_code: str) -> None:
        """Устанавливает язык промтов и перезагружает проверку."""
        if lang_code != self._current_language:
            self._current_language = lang_code
            self._ensure_dir()
            self._check_required_prompts()

    def get_language(self) -> str:
        """Возвращает текущий язык промтов."""
        return self._current_language

    def load_prompt(self, name: str) -> str:
        """Загружает промт из файла для текущего языка."""
        filepath = os.path.join(self._get_prompts_dir(), f"{name}.json")
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Prompt '{name}' not found in '{self._get_prompts_dir()}'")
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("content", "")

    def save_prompt(self, name: str, content: str) -> None:
        """Сохраняет промт в файл для текущего языка."""
        filepath = os.path.join(self._get_prompts_dir(), f"{name}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({"name": name, "content": content}, f, ensure_ascii=False, indent=2)

    def list_prompts(self) -> List[str]:
        """Возвращает список имён промтов для текущего языка."""
        prompts_dir = self._get_prompts_dir()
        if not os.path.exists(prompts_dir):
            return []
        prompts = []
        for f in os.listdir(prompts_dir):
            if f.endswith(".json"):
                prompts.append(f[:-5])
        return prompts

    def get_prompt_content(self, name: str) -> str:
        """Удобный метод для получения содержимого промта."""
        return self.load_prompt(name)

    def create_prompt(self, name: str, content: str = "") -> bool:
        """Создаёт новый промт для текущего языка."""
        if not name:
            return False
        filepath = os.path.join(self._get_prompts_dir(), f"{name}.json")
        if os.path.exists(filepath):
            return False
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({"name": name, "content": content}, f, ensure_ascii=False, indent=2)
        return True

    def delete_prompt(self, name: str) -> bool:
        """Удаляет промт для текущего языка."""
        if name in self.REQUIRED_PROMPTS:
            return False
        filepath = os.path.join(self._get_prompts_dir(), f"{name}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False
    
    def get_prompt_dir_for_lang(self, lang_code: str) -> str:
        """Возвращает путь к папке промтов для указанного языка (без переключения)."""
        return os.path.join(self.prompts_base_dir, lang_code)
    
    def copy_prompts_from_lang(self, source_lang: str, target_lang: str) -> None:
        """Копирует все промты из одного языка в другой (создаёт папку)."""
        source_dir = self.get_prompt_dir_for_lang(source_lang)
        target_dir = self.get_prompt_dir_for_lang(target_lang)
        if not os.path.exists(source_dir):
            return
        os.makedirs(target_dir, exist_ok=True)
        for fname in os.listdir(source_dir):
            if fname.endswith(".json"):
                src = os.path.join(source_dir, fname)
                dst = os.path.join(target_dir, fname)
                if not os.path.exists(dst):
                    import shutil
                    shutil.copy2(src, dst)