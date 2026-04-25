# left_panel_localized.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from localization import loc


class LeftPanel(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build_ui()
        self.refresh_campaign_list()
        self.refresh_session_list()

    def _build_ui(self):
        # --- Блок кампаний ---
        campaign_frame = ttk.LabelFrame(self, text=loc.tr("left_campaigns"))
        campaign_frame.pack(fill=tk.X, padx=5, pady=5)

        self.campaign_listbox = tk.Listbox(campaign_frame, height=4)
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

        self.session_listbox = tk.Listbox(session_frame, height=10)
        self.session_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.session_listbox.bind("<<ListboxSelect>>", self._on_session_select)
        self.session_listbox.bind("<Double-Button-1>", self._on_session_double_click)

        session_btn_row1 = ttk.Frame(session_frame)
        session_btn_row1.pack(fill=tk.X, padx=5, pady=(0,2))
        ttk.Button(session_btn_row1, text=loc.tr("left_new_session"), command=lambda: self.app.update("new_session")).pack(side=tk.LEFT, padx=2)
        ttk.Button(session_btn_row1, text=loc.tr("left_delete_session"), command=self._delete_session).pack(side=tk.LEFT, padx=2)

        session_btn_row2 = ttk.Frame(session_frame)
        session_btn_row2.pack(fill=tk.X, padx=5, pady=(0,5))
        ttk.Button(session_btn_row2, text=loc.tr("left_rename_session"), command=self._rename_session).pack(side=tk.LEFT, padx=2)
        ttk.Button(session_btn_row2, text=loc.tr("left_edit_json"), command=lambda: self.app.update("edit_session")).pack(side=tk.LEFT, padx=2)

    def refresh_language(self):
        """Обновляет тексты после смены языка."""
        self.campaign_listbox.master.config(text=loc.tr("left_campaigns"))
        self.session_listbox.master.config(text=loc.tr("left_sessions"))
        # Кнопки пересоздавать не будем, просто обновим текст у существующих
        for widget in self.winfo_children():
            if isinstance(widget, ttk.LabelFrame):
                if widget.cget("text") in (loc.tr("left_campaigns"), loc.tr("left_sessions")):
                    continue
        # Проще перестроить UI, но для простоты обновим тексты кнопок вручную
        # Найдём кнопки в campaign_btn_frame и session_btn_frame
        for child in self.winfo_children():
            if isinstance(child, ttk.LabelFrame):
                for sub in child.winfo_children():
                    if isinstance(sub, ttk.Frame):
                        for btn in sub.winfo_children():
                            if isinstance(btn, ttk.Button):
                                txt = btn.cget("text")
                                if txt == "Новая" or txt == "New":
                                    btn.config(text=loc.tr("left_new_campaign"))
                                elif txt == "Переименовать" or txt == "Rename":
                                    btn.config(text=loc.tr("left_rename_campaign"))
                                elif txt == "Удалить" or txt == "Delete":
                                    btn.config(text=loc.tr("left_delete_campaign"))
                                elif txt == "Новая" or txt == "New" and btn in session_btn_row1.winfo_children():
                                    btn.config(text=loc.tr("left_new_session"))
                                elif txt == "Удалить" or txt == "Delete" and btn in session_btn_row1.winfo_children():
                                    btn.config(text=loc.tr("left_delete_session"))
                                elif txt == "Переименовать" or txt == "Rename" and btn in session_btn_row2.winfo_children():
                                    btn.config(text=loc.tr("left_rename_session"))
                                elif txt == "Редактировать JSON" or txt == "Edit JSON":
                                    btn.config(text=loc.tr("left_edit_json"))

    def refresh_campaign_list(self):
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

    def _on_campaign_select(self, event):
        selection = self.campaign_listbox.curselection()
        if not selection:
            return
        camp_name = self.campaign_listbox.get(selection[0])
        if camp_name != self.app.storage.current_campaign:
            self.app.update("select_campaign", {"name": camp_name})

    def _create_campaign(self):
        name = simpledialog.askstring(loc.tr("left_new_campaign"), loc.tr("left_new_campaign"), parent=self)
        if name:
            self.app.update("create_campaign", {"name": name})

    def _rename_campaign(self):
        selection = self.campaign_listbox.curselection()
        if not selection:
            messagebox.showwarning(loc.tr("left_rename_campaign"), loc.tr("error_invalid_name"))
            return
        old_name = self.campaign_listbox.get(selection[0])
        new_name = simpledialog.askstring(loc.tr("left_rename_campaign"), loc.tr("left_rename_campaign"), initialvalue=old_name, parent=self)
        if new_name and new_name != old_name:
            self.app.update("rename_campaign", {"old_name": old_name, "new_name": new_name})

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
            self.app.update("delete_campaign", {"name": camp_name})

    def refresh_session_list(self):
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

    def get_session_name(self, session_id: str) -> str:
        data = self.app.storage.load_session(session_id)
        return data.get("name", loc.tr("left_new_session")) if data else loc.tr("left_new_session")

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
        self.app.update("delete_session", {"session_id": session_id})

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
            self.app.update("rename_session", {"session_id": session_id, "new_name": new_name})