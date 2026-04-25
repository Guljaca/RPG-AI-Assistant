# localization.py
import json
import os
from typing import Dict, Any, Optional

class Localization:
    """Класс для управления локализацией интерфейса и системных сообщений."""
    
    _instance: Optional['Localization'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._current_language: str = "ru"
        self._strings: Dict[str, str] = {}
        self._localization_dir: str = "localization"
        self._load_language(self._current_language)
    
    def _load_language(self, lang_code: str) -> None:
        """Загружает файл локализации для указанного языка."""
        filepath = os.path.join(self._localization_dir, f"{lang_code}.json")
        if not os.path.exists(filepath):
            # fallback на русский
            filepath = os.path.join(self._localization_dir, "ru.json")
            if not os.path.exists(filepath):
                raise FileNotFoundError(f"Localization file not found: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            self._strings = json.load(f)
        self._current_language = lang_code
    
    def set_language(self, lang_code: str) -> None:
        """Устанавливает язык интерфейса."""
        if lang_code != self._current_language:
            self._load_language(lang_code)
    
    def get_language(self) -> str:
        """Возвращает текущий код языка."""
        return self._current_language
    
    def tr(self, key: str, **kwargs) -> str:
        """
        Возвращает переведённую строку по ключу с подстановкой параметров.
        Пример: tr("settings_title") -> "Настройки"
                tr("messages_stage1_1", attempt=1) -> "🔍 Этап 1.1/11: ... (попытка 1)..."
        """
        text = self._strings.get(key, key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except KeyError:
                # если в тексте нет ожидаемого ключа или он не подставлен, оставляем как есть
                pass
        return text
    
    def get_all_strings(self) -> Dict[str, str]:
        """Возвращает копию всех строк локализации."""
        return self._strings.copy()


# Глобальный экземпляр для удобного импорта
loc = Localization()