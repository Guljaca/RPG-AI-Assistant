import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog   # добавлен simpledialog


class LeftPanel(ttk.Frame):
    def __init__(self, parent, app):          # добавлен параметр app
        super().__init__(parent)
        self.app = app                         # сохранение ссылки на главное приложение
        self.session_ids = []                  # список ID сессий
        self._build_ui()
        self.refresh_session_list()

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
            name = self.get_session_name(sid)
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
