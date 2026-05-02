# full_editor.py
import tkinter as tk
from tkinter import ttk, scrolledtext
from ui_utils import add_context_menu
from localization import loc

class FullDescriptionEditor:
    """Полноэкранный редактор полного описания объекта."""
    def __init__(self, parent, title: str, initial_text: str, callback_save):
        """
        parent: родительское окно (обычно self.app)
        title: заголовок окна
        initial_text: текст для редактирования
        callback_save: функция, принимающая новый текст (str) и вызываемая при сохранении
        """
        self.parent = parent
        self.callback_save = callback_save
        self.result_text = None

        # Создаём окно поверх родителя, по размеру главного окна
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.transient(parent)
        self.window.grab_set()

        # Получаем размеры и позицию главного окна
        parent.update_idletasks()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()

        # Устанавливаем размеры чуть меньше, чтобы было видно, что это диалог
        width = int(parent_width * 0.9)
        height = int(parent_height * 0.9)
        x = parent_x + (parent_width - width) // 2
        y = parent_y + (parent_height - height) // 2

        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.window.minsize(600, 400)

        # Основной фрейм
        main_frame = ttk.Frame(self.window, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Текстовое поле с прокруткой
        self.text_editor = scrolledtext.ScrolledText(
            main_frame,
            wrap=tk.WORD,
            font=("TkDefaultFont", 10)
        )
        self.text_editor.pack(fill=tk.BOTH, expand=True)
        self.text_editor.insert(tk.END, initial_text)
        self.text_editor.focus_set()

        # Добавляем контекстное меню и горячие клавиши (копировать/вставить/вырезать)
        add_context_menu(self.text_editor)

        # Нижняя панель с кнопками
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(btn_frame, text=loc.tr("profile_save"), command=self._save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text=loc.tr("vn_cancel"), command=self._cancel).pack(side=tk.RIGHT, padx=5)

        # Обработка закрытия окна
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)

    def _save(self):
        """Сохранить текст и закрыть окно."""
        new_text = self.text_editor.get("1.0", tk.END).rstrip("\n")
        self.callback_save(new_text)
        self.window.destroy()

    def _cancel(self):
        """Закрыть окно без сохранения."""
        self.window.destroy()