# left_panel.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

class LeftPanel(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build_ui()
        self.refresh_campaign_list()
        self.refresh_session_list()

    def _build_ui(self):
        # --- Блок кампаний ---
        campaign_frame = ttk.LabelFrame(self, text="Кампании")
        campaign_frame.pack(fill=tk.X, padx=5, pady=5)

        self.campaign_listbox = tk.Listbox(campaign_frame, height=4)
        self.campaign_listbox.pack(fill=tk.X, padx=5, pady=5)
        self.campaign_listbox.bind("<<ListboxSelect>>", self._on_campaign_select)

        campaign_btn_frame = ttk.Frame(campaign_frame)
        campaign_btn_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(campaign_btn_frame, text="Новая", command=self._create_campaign).pack(side=tk.LEFT, padx=2)
        ttk.Button(campaign_btn_frame, text="Переименовать", command=self._rename_campaign).pack(side=tk.LEFT, padx=2)
        ttk.Button(campaign_btn_frame, text="Удалить", command=self._delete_campaign).pack(side=tk.LEFT, padx=2)

        # --- Блок сессий ---
        session_frame = ttk.LabelFrame(self, text="Сессии")
        session_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.session_listbox = tk.Listbox(session_frame, height=10)
        self.session_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.session_listbox.bind("<<ListboxSelect>>", self._on_session_select)
        self.session_listbox.bind("<Double-Button-1>", self._on_session_double_click)

        # Первый ряд кнопок: Новая, Удалить
        session_btn_row1 = ttk.Frame(session_frame)
        session_btn_row1.pack(fill=tk.X, padx=5, pady=(0,2))
        ttk.Button(session_btn_row1, text="Новая", command=lambda: self.app.update("new_session")).pack(side=tk.LEFT, padx=2)
        ttk.Button(session_btn_row1, text="Удалить", command=self._delete_session).pack(side=tk.LEFT, padx=2)

        # Второй ряд кнопок: Переименовать, Редактировать JSON
        session_btn_row2 = ttk.Frame(session_frame)
        session_btn_row2.pack(fill=tk.X, padx=5, pady=(0,5))
        ttk.Button(session_btn_row2, text="Переименовать", command=self._rename_session).pack(side=tk.LEFT, padx=2)
        ttk.Button(session_btn_row2, text="Редактировать JSON", command=lambda: self.app.update("edit_session")).pack(side=tk.LEFT, padx=2)

    # ---------- Методы для кампаний ----------
    def refresh_campaign_list(self):
        """Обновляет список кампаний в левой панели."""
        self.campaign_listbox.delete(0, tk.END)
        campaigns = self.app.storage.list_campaigns()
        for camp in campaigns:
            self.campaign_listbox.insert(tk.END, camp)
        # Подсветить текущую кампанию
        current = self.app.storage.current_campaign
        if current:
            for i, camp in enumerate(campaigns):
                if camp == current:
                    self.campaign_listbox.selection_clear(0, tk.END)
                    self.campaign_listbox.selection_set(i)
                    self.campaign_listbox.see(i)
                    break

    def _on_campaign_select(self, event):
        selection = self.campaign_listbox.curselection()
        if not selection:
            return
        camp_name = self.campaign_listbox.get(selection[0])
        if camp_name != self.app.storage.current_campaign:
            self.app.update("select_campaign", {"name": camp_name})

    def _create_campaign(self):
        name = simpledialog.askstring("Новая кампания", "Введите название кампании:", parent=self)
        if name:
            self.app.update("create_campaign", {"name": name})

    def _rename_campaign(self):
        selection = self.campaign_listbox.curselection()
        if not selection:
            messagebox.showwarning("Переименование", "Выберите кампанию.")
            return
        old_name = self.campaign_listbox.get(selection[0])
        new_name = simpledialog.askstring("Переименовать кампанию", "Новое название:", initialvalue=old_name, parent=self)
        if new_name and new_name != old_name:
            self.app.update("rename_campaign", {"old_name": old_name, "new_name": new_name})

    def _delete_campaign(self):
        selection = self.campaign_listbox.curselection()
        if not selection:
            messagebox.showwarning("Удаление", "Выберите кампанию.")
            return
        camp_name = self.campaign_listbox.get(selection[0])
        if camp_name == "Default":
            messagebox.showwarning("Удаление", "Кампанию 'Default' нельзя удалить.")
            return
        if messagebox.askyesno("Удаление кампании", f"Удалить кампанию '{camp_name}' и ВСЕ её данные? Это действие необратимо."):
            self.app.update("delete_campaign", {"name": camp_name})

    # ---------- Методы для сессий ----------
    def refresh_session_list(self):
        """Обновляет список сессий для текущей кампании."""
        self.session_listbox.delete(0, tk.END)
        sessions = self.app.list_sessions()
        for sid in sessions:
            data = self.app.storage.load_session(sid)
            if data:
                name = data.get("name", "Без имени")
                display = f"{name} ({sid[:8]})"
            else:
                display = f"{sid[:8]} (ошибка)"
            self.session_listbox.insert(tk.END, display)
        # Подсветить текущую сессию
        current = self.app.current_session_id
        if current:
            for i, sid in enumerate(sessions):
                if sid == current:
                    self.session_listbox.selection_clear(0, tk.END)
                    self.session_listbox.selection_set(i)
                    self.session_listbox.see(i)
                    break

    def get_session_name(self, session_id: str) -> str:
        data = self.app.storage.load_session(session_id)
        return data.get("name", "Без имени") if data else "Без имени"

    def _on_session_select(self, event):
        selection = self.session_listbox.curselection()
        if not selection:
            return
        sessions = self.app.list_sessions()
        if selection[0] >= len(sessions):
            return
        session_id = sessions[selection[0]]
        if session_id != self.app.current_session_id:
            self.app.update("load_session", {"session_id": session_id})

    def _on_session_double_click(self, event):
        """Двойной клик для переименования сессии."""
        selection = self.session_listbox.curselection()
        if not selection:
            return
        sessions = self.app.list_sessions()
        if selection[0] >= len(sessions):
            return
        session_id = sessions[selection[0]]
        self._rename_session_by_id(session_id)

    def _delete_session(self):
        selection = self.session_listbox.curselection()
        if not selection:
            messagebox.showwarning("Удаление", "Выберите сессию.")
            return
        sessions = self.app.list_sessions()
        if selection[0] >= len(sessions):
            return
        session_id = sessions[selection[0]]
        self.app.update("delete_session", {"session_id": session_id})

    def _rename_session(self):
        selection = self.session_listbox.curselection()
        if not selection:
            messagebox.showwarning("Переименование", "Выберите сессию.")
            return
        sessions = self.app.list_sessions()
        if selection[0] >= len(sessions):
            return
        session_id = sessions[selection[0]]
        self._rename_session_by_id(session_id)

    def _rename_session_by_id(self, session_id: str):
        data = self.app.storage.load_session(session_id)
        if not data:
            return
        old_name = data.get("name", "Без имени")
        new_name = simpledialog.askstring("Переименовать сессию", "Новое название:", initialvalue=old_name, parent=self)
        if new_name and new_name != old_name:
            self.app.update("rename_session", {"session_id": session_id, "new_name": new_name})