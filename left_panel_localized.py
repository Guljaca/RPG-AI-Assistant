# left_panel_localized.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from localization import loc


class LeftPanel(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._loading = False
        self._pending_campaign = None
        self._pending_session = None
        self._build_ui()
        self.refresh_campaign_list()
        self.refresh_session_list()

    def _build_ui(self):
        # --- Блок кампаний ---
        campaign_frame = ttk.LabelFrame(self, text=loc.tr("left_campaigns"))
        campaign_frame.pack(fill=tk.X, padx=5, pady=5)

        self.campaign_listbox = tk.Listbox(campaign_frame, height=4, exportselection=False)
        self.campaign_listbox.pack(fill=tk.X, padx=5, pady=5)
        self.campaign_listbox.bind("<<ListboxSelect>>", self._on_campaign_select)

        campaign_btn_frame = ttk.Frame(campaign_frame)
        campaign_btn_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(campaign_btn_frame, text=loc.tr("left_new_campaign"), command=self._create_campaign).pack(side=tk.LEFT, padx=2)
        ttk.Button(campaign_btn_frame, text=loc.tr("left_rename_campaign"), command=self._rename_campaign).pack(side=tk.LEFT, padx=2)
        ttk.Button(campaign_btn_frame, text=loc.tr("left_delete_campaign"), command=self._delete_campaign).pack(side=tk.LEFT, padx=2)

        # --- Блок сессий ---
        session_frame = ttk.LabelFrame(self, text=loc.tr("left_sessions"))
        session_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.session_listbox = tk.Listbox(session_frame, height=10, exportselection=False)
        self.session_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.session_listbox.bind("<<ListboxSelect>>", self._on_session_select)
        self.session_listbox.bind("<Double-Button-1>", self._on_session_double_click)

        session_btn_row1 = ttk.Frame(session_frame)
        session_btn_row1.pack(fill=tk.X, padx=5, pady=(0,2))
        ttk.Button(session_btn_row1, text=loc.tr("left_new_session"), command=lambda: self._safe_update("new_session")).pack(side=tk.LEFT, padx=2)
        ttk.Button(session_btn_row1, text=loc.tr("left_delete_session"), command=self._delete_session).pack(side=tk.LEFT, padx=2)

        session_btn_row2 = ttk.Frame(session_frame)
        session_btn_row2.pack(fill=tk.X, padx=5, pady=(0,5))
        ttk.Button(session_btn_row2, text=loc.tr("left_rename_session"), command=self._rename_session).pack(side=tk.LEFT, padx=2)
        ttk.Button(session_btn_row2, text=loc.tr("left_edit_json"), command=lambda: self._safe_update("edit_session")).pack(side=tk.LEFT, padx=2)

    def _safe_update(self, event_type, data=None):
        """Безопасный вызов update, игнорирующий события во время загрузки"""
        if self._loading:
            return
        self.app.update(event_type, data)

    def refresh_language(self):
        self.campaign_listbox.master.config(text=loc.tr("left_campaigns"))
        self.session_listbox.master.config(text=loc.tr("left_sessions"))
        for child in self.winfo_children():
            if isinstance(child, ttk.LabelFrame):
                for sub in child.winfo_children():
                    if isinstance(sub, ttk.Frame):
                        for btn in sub.winfo_children():
                            if isinstance(btn, ttk.Button):
                                txt = btn.cget("text")
                                if txt in ("Новая", "New"):
                                    btn.config(text=loc.tr("left_new_campaign"))
                                elif txt in ("Переименовать", "Rename"):
                                    btn.config(text=loc.tr("left_rename_campaign"))
                                elif txt in ("Удалить", "Delete"):
                                    btn.config(text=loc.tr("left_delete_campaign"))
                                elif txt in ("Новая сессия", "New session"):
                                    btn.config(text=loc.tr("left_new_session"))
                                elif txt in ("Удалить сессию", "Delete session"):
                                    btn.config(text=loc.tr("left_delete_session"))
                                elif txt in ("Переименовать сессию", "Rename session"):
                                    btn.config(text=loc.tr("left_rename_session"))
                                elif txt in ("Редактировать JSON", "Edit JSON"):
                                    btn.config(text=loc.tr("left_edit_json"))

    def refresh_campaign_list(self):
        if self._loading:
            return
        # Сохраняем текущее выделение, чтобы восстановить после обновления
        old_selection = self.campaign_listbox.curselection()
        self.campaign_listbox.delete(0, tk.END)
        campaigns = self.app.storage.list_campaigns()
        for camp in campaigns:
            self.campaign_listbox.insert(tk.END, camp)
        current = self.app.storage.current_campaign
        if current:
            for i, camp in enumerate(campaigns):
                if camp == current:
                    self.campaign_listbox.selection_clear(0, tk.END)
                    self.campaign_listbox.selection_set(i)
                    self.campaign_listbox.see(i)
                    break
        elif old_selection:
            # Если текущей кампании нет, пытаемся восстановить выделение
            idx = old_selection[0]
            if idx < self.campaign_listbox.size():
                self.campaign_listbox.selection_set(idx)
                self.campaign_listbox.see(idx)

    def refresh_session_list(self):
        if self._loading:
            return
        old_selection = self.session_listbox.curselection()
        self.session_listbox.delete(0, tk.END)
        sessions = self.app.list_sessions()
        for sid in sessions:
            data = self.app.storage.load_session(sid)
            if data:
                name = data.get("name", loc.tr("left_new_session"))
                display = f"{name} ({sid[:8]})"
            else:
                display = f"{sid[:8]} ({loc.tr('error_invalid_name')})"
            self.session_listbox.insert(tk.END, display)
        current = self.app.current_session_id
        if current:
            for i, sid in enumerate(sessions):
                if sid == current:
                    self.session_listbox.selection_clear(0, tk.END)
                    self.session_listbox.selection_set(i)
                    self.session_listbox.see(i)
                    break
        elif old_selection:
            idx = old_selection[0]
            if idx < self.session_listbox.size():
                self.session_listbox.selection_set(idx)
                self.session_listbox.see(idx)

    def get_session_name(self, session_id: str) -> str:
        data = self.app.storage.load_session(session_id)
        return data.get("name", loc.tr("left_new_session")) if data else loc.tr("left_new_session")

    def _on_campaign_select(self, event):
        if self._loading:
            return
        selection = self.campaign_listbox.curselection()
        if not selection:
            return
        camp_name = self.campaign_listbox.get(selection[0])
        if camp_name == self.app.storage.current_campaign:
            return
        # Сохраняем отложенное действие
        self._pending_campaign = camp_name
        self._pending_session = None
        self._start_loading()

    def _start_loading(self):
        if self._loading:
            return
        self._loading = True
        # Отключаем привязки событий, чтобы предотвратить новые выборы
        self.campaign_listbox.unbind("<<ListboxSelect>>")
        self.session_listbox.unbind("<<ListboxSelect>>")
        # Запускаем процесс применения отложенного действия
        self.after(50, self._apply_pending)

    def _apply_pending(self):
        if self._pending_campaign is not None:
            camp = self._pending_campaign
            self._pending_campaign = None
            if camp != self.app.storage.current_campaign:
                self.app.update("select_campaign", {"name": camp})
        elif self._pending_session is not None:
            sess = self._pending_session
            self._pending_session = None
            if sess != self.app.current_session_id:
                self.app.update("load_session", {"session_id": sess})
        # После применения ждём завершения через callback от app
        # Флаг _loading будет сброшен после того, как app вызовет refresh_ui или явно уведомит
        # В MainApp после загрузки кампании/сессии вызывается _refresh_all_ui, который обновит панели
        # Поэтому здесь не сбрасываем _loading, а сделаем сброс через after с задержкой (запасной вариант)
        self.after(3000, self._reset_loading)  # защита от зависания

    def _reset_loading(self):
        if self._loading:
            self._loading = False
            self.campaign_listbox.bind("<<ListboxSelect>>", self._on_campaign_select)
            self.session_listbox.bind("<<ListboxSelect>>", self._on_session_select)
            self.refresh_campaign_list()
            self.refresh_session_list()

    def _on_session_select(self, event):
        if self._loading:
            return
        selection = self.session_listbox.curselection()
        if not selection:
            return
        sessions = self.app.list_sessions()
        if selection[0] >= len(sessions):
            return
        session_id = sessions[selection[0]]
        if session_id == self.app.current_session_id:
            return
        self._pending_session = session_id
        self._pending_campaign = None
        self._start_loading()

    def _create_campaign(self):
        name = simpledialog.askstring(loc.tr("left_new_campaign"), loc.tr("left_new_campaign"), parent=self)
        if name:
            self._safe_update("create_campaign", {"name": name})

    def _rename_campaign(self):
        selection = self.campaign_listbox.curselection()
        if not selection:
            messagebox.showwarning(loc.tr("left_rename_campaign"), loc.tr("error_invalid_name"))
            return
        old_name = self.campaign_listbox.get(selection[0])
        new_name = simpledialog.askstring(loc.tr("left_rename_campaign"), loc.tr("left_rename_campaign"), initialvalue=old_name, parent=self)
        if new_name and new_name != old_name:
            self._safe_update("rename_campaign", {"old_name": old_name, "new_name": new_name})

    def _delete_campaign(self):
        selection = self.campaign_listbox.curselection()
        if not selection:
            messagebox.showwarning(loc.tr("left_delete_campaign"), loc.tr("error_invalid_name"))
            return
        camp_name = self.campaign_listbox.get(selection[0])
        if camp_name == "Default":
            messagebox.showwarning(loc.tr("left_delete_campaign"), loc.tr("error_campaign_delete_default"))
            return
        if messagebox.askyesno(loc.tr("left_delete_campaign"), loc.tr("confirm_delete_campaign", name=camp_name)):
            self._safe_update("delete_campaign", {"name": camp_name})

    def _on_session_double_click(self, event):
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
            messagebox.showwarning(loc.tr("left_delete_session"), loc.tr("error_invalid_name"))
            return
        sessions = self.app.list_sessions()
        if selection[0] >= len(sessions):
            return
        session_id = sessions[selection[0]]
        self._safe_update("delete_session", {"session_id": session_id})

    def _rename_session(self):
        selection = self.session_listbox.curselection()
        if not selection:
            messagebox.showwarning(loc.tr("left_rename_session"), loc.tr("error_invalid_name"))
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
        old_name = data.get("name", loc.tr("left_new_session"))
        new_name = simpledialog.askstring(loc.tr("left_rename_session"), loc.tr("left_rename_session"), initialvalue=old_name, parent=self)
        if new_name and new_name != old_name:
            self._safe_update("rename_session", {"session_id": session_id, "new_name": new_name})