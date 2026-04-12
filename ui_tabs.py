# ui_tabs.py
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
import re
from models import Narrator, Character, Location, Item

# ---------- Вспомогательная функция контекстного меню (копия из основного файла) ----------
def add_context_menu(widget):
    """Добавляет контекстное меню (Вырезать/Копировать/Вставить/Выделить всё) для текстовых виджетов."""
    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label="Вырезать", command=lambda: widget.event_generate("<<Cut>>"))
    menu.add_command(label="Копировать", command=lambda: widget.event_generate("<<Copy>>"))
    menu.add_command(label="Вставить", command=lambda: widget.event_generate("<<Paste>>"))
    menu.add_separator()
    menu.add_command(label="Выделить всё", command=lambda: widget.event_generate("<<SelectAll>>"))

    def show_menu(event):
        try:
            if widget.selection_present():
                menu.entryconfig("Вырезать", state="normal")
                menu.entryconfig("Копировать", state="normal")
            else:
                menu.entryconfig("Вырезать", state="disabled")
                menu.entryconfig("Копировать", state="disabled")
            menu.entryconfig("Вставить", state="normal")
        except:
            pass
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    widget.bind("<Button-3>", show_menu)
    widget.bind("<Control-a>", lambda e: widget.tag_add(tk.SEL, "1.0", tk.END) if hasattr(widget, 'tag_add') else widget.select_range(0, tk.END))
    widget.bind("<Control-A>", lambda e: widget.tag_add(tk.SEL, "1.0", tk.END) if hasattr(widget, 'tag_add') else widget.select_range(0, tk.END))

# ---------- Вкладка "Профиль" ----------
class ProfileTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        row0 = ttk.Frame(top_frame)
        row0.pack(fill=tk.X, pady=2)
        ttk.Label(row0, text="Профиль:").pack(side=tk.LEFT)
        self.profile_name_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(row0, textvariable=self.profile_name_var, width=20)
        self.profile_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        row1 = ttk.Frame(top_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Button(row1, text="Загрузить", command=self._load_profile).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text="Сохранить", command=self._save_profile).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text="Новый", command=self._new_profile).pack(side=tk.LEFT, padx=2)
        canvas_container = ttk.Frame(self)
        canvas_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.canvas = tk.Canvas(canvas_container, borderwidth=0)
        scrollbar = ttk.Scrollbar(canvas_container, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw", tags=("window",))

        def _on_canvas_configure(event):
            self.canvas.itemconfig(self.canvas_window, width=event.width)
        self.canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.canvas.bind("<MouseWheel>", _on_mousewheel)

        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill=tk.X, padx=5, pady=5)
        self.apply_btn = ttk.Button(bottom_frame, text="Применить", command=self._apply_changes)
        self.apply_btn.pack(pady=5)

        self.narrator_vars = {}
        self.char_vars = {}
        self.loc_vars = {}
        self.item_vars = {}

    def refresh(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        profile = self.app.current_profile
        profiles = self.app.storage.list_profiles()
        self.profile_combo['values'] = profiles
        self.profile_name_var.set(profile.name)

        if self.app.narrators:
            ttk.Label(self.scrollable_frame, text="Рассказчики", font=('Arial', 10, 'bold')).pack(anchor='w', pady=(5,0))
            self.narrator_vars.clear()
            for nid, narr in self.app.narrators.items():
                var = tk.BooleanVar(value=(nid in profile.enabled_narrators))
                self.narrator_vars[nid] = var
                cb = ttk.Checkbutton(self.scrollable_frame, text=narr.name, variable=var, command=self._on_checkbox_change)
                cb.pack(anchor='w', padx=20)

        if self.app.characters:
            ttk.Label(self.scrollable_frame, text="Персонажи", font=('Arial', 10, 'bold')).pack(anchor='w', pady=(10,0))
            self.char_vars.clear()
            for cid, char in self.app.characters.items():
                var = tk.BooleanVar(value=(cid in profile.enabled_characters))
                self.char_vars[cid] = var
                cb = ttk.Checkbutton(self.scrollable_frame, text=f"{char.name} {'(ИГРОК)' if char.is_player else ''}", variable=var, command=self._on_checkbox_change)
                cb.pack(anchor='w', padx=20)

        if self.app.locations:
            ttk.Label(self.scrollable_frame, text="Локации", font=('Arial', 10, 'bold')).pack(anchor='w', pady=(10,0))
            self.loc_vars.clear()
            for lid, loc in self.app.locations.items():
                var = tk.BooleanVar(value=(lid in profile.enabled_locations))
                self.loc_vars[lid] = var
                cb = ttk.Checkbutton(self.scrollable_frame, text=loc.name, variable=var, command=self._on_checkbox_change)
                cb.pack(anchor='w', padx=20)

        if self.app.items:
            ttk.Label(self.scrollable_frame, text="Предметы", font=('Arial', 10, 'bold')).pack(anchor='w', pady=(10,0))
            self.item_vars.clear()
            for iid, item in self.app.items.items():
                var = tk.BooleanVar(value=(iid in profile.enabled_items))
                self.item_vars[iid] = var
                cb = ttk.Checkbutton(self.scrollable_frame, text=item.name, variable=var, command=self._on_checkbox_change)
                cb.pack(anchor='w', padx=20)

        self.scrollable_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_checkbox_change(self):
        pass

    def _apply_changes(self):
        profile = self.app.current_profile
        profile.enabled_narrators = [nid for nid, var in self.narrator_vars.items() if var.get()]
        profile.enabled_characters = [cid for cid, var in self.char_vars.items() if var.get()]
        profile.enabled_locations = [lid for lid, var in self.loc_vars.items() if var.get()]
        profile.enabled_items = [iid for iid, var in self.item_vars.items() if var.get()]
        self.app.update("update_profile", {
            "enabled_narrators": profile.enabled_narrators,
            "enabled_characters": profile.enabled_characters,
            "enabled_locations": profile.enabled_locations,
            "enabled_items": profile.enabled_items
        })
        messagebox.showinfo("Профиль", "Настройки применены.")

    def _load_profile(self):
        name = self.profile_name_var.get()
        if name:
            self.app.update("load_profile", {"name": name})

    def _save_profile(self):
        self.app.update("save_profile")

    def _new_profile(self):
        self.app.update("new_profile")

# ---------- Базовый редактор для объектов (Рассказчики, Персонажи, Локации, Предметы) ----------
class BaseEditorTab(ttk.Frame):
    def __init__(self, parent, app, obj_type: str, obj_class, title: str):
        super().__init__(parent)
        self.app = app
        self.obj_type = obj_type
        self.obj_class = obj_class
        self.title = title
        self.current_obj_id = None
        self.editing_mode = tk.StringVar(value="global")
        self.player_var = tk.BooleanVar(value=False)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        list_frame = ttk.LabelFrame(self, text=f"Список {self.title}")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 0))
        list_container = ttk.Frame(list_frame)
        list_container.pack(fill=tk.BOTH, expand=True)
        self.listbox = tk.Listbox(list_container, height=8)
        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(btn_frame, text="Создать", command=self._create_new).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить", command=self._delete_selected).pack(side=tk.LEFT, padx=5)

        mode_frame = ttk.LabelFrame(self, text="Режим редактирования")
        mode_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Radiobutton(mode_frame, text="Global", variable=self.editing_mode, value="global", command=self._on_mode_change).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(mode_frame, text="Session", variable=self.editing_mode, value="local", command=self._on_mode_change).pack(side=tk.LEFT, padx=5)
        self.reset_local_btn = ttk.Button(mode_frame, text="Сбросить локальное", command=self._reset_local, state=tk.DISABLED)
        self.reset_local_btn.pack(side=tk.RIGHT, padx=5)

        if self.obj_type == "characters":
            player_frame = ttk.Frame(self)
            player_frame.pack(fill=tk.X, padx=5, pady=5)
            self.player_check = ttk.Checkbutton(player_frame, text="Это персонаж игрока (ГГ)", variable=self.player_var, command=self._on_player_flag_change)
            self.player_check.pack(side=tk.LEFT)

        editor_frame = ttk.LabelFrame(self, text="Редактор")
        editor_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Label(editor_frame, text="Название:").pack(anchor='w', padx=5, pady=2)
        self.name_entry = ttk.Entry(editor_frame, width=30)
        self.name_entry.pack(fill=tk.X, padx=5, pady=2)
        add_context_menu(self.name_entry)
        ttk.Label(editor_frame, text="Описание:").pack(anchor='w', padx=5, pady=2)
        self.desc_text = scrolledtext.ScrolledText(editor_frame, height=10, wrap=tk.WORD)
        self.desc_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        add_context_menu(self.desc_text)
        save_btn = ttk.Button(editor_frame, text="Сохранить", command=self._save_current)
        save_btn.pack(pady=5)

    def _get_objects_dict(self):
        if self.obj_type == "narrators":
            return self.app.narrators
        elif self.obj_type == "characters":
            return self.app.characters
        elif self.obj_type == "locations":
            return self.app.locations
        elif self.obj_type == "items":
            return self.app.items
        return {}

    def _extract_num(self, obj_id: str) -> int:
        match = re.search(r'\d+$', obj_id)
        return int(match.group()) if match else 0

    def _populate_list(self):
        self.listbox.delete(0, tk.END)
        objects_dict = self._get_objects_dict()
        sorted_ids = sorted(objects_dict.keys(), key=self._extract_num)
        for obj_id in sorted_ids:
            obj = objects_dict[obj_id]
            text = f"{obj.name} (id:{obj.id})"
            if self.obj_type == "characters" and obj.is_player:
                text += " [ИГРОК]"
            self.listbox.insert(tk.END, text)

    def refresh(self):
        current_selection = self.current_obj_id
        self._populate_list()
        if current_selection and current_selection in self._get_objects_dict():
            self._select_object_by_id(current_selection)
        else:
            self._clear_form()

    def add_object(self, obj_id: str):
        self.refresh()
        self._select_object_by_id(obj_id)

    def update_object(self, obj_id: str):
        if self.current_obj_id == obj_id:
            self._load_current_description()
        self.refresh()

    def remove_object(self, obj_id: str):
        if self.current_obj_id == obj_id:
            self._clear_form()
        self.refresh()

    def _on_mode_change(self):
        if self.current_obj_id:
            self._load_current_description()
            local_exists = self.current_obj_id in self.app.local_descriptions
            self.reset_local_btn.config(state=tk.NORMAL if local_exists else tk.DISABLED)

    def _load_current_description(self):
        if not self.current_obj_id:
            return
        obj = self._get_objects_dict().get(self.current_obj_id)
        if not obj:
            return
        self.name_entry.delete(0, tk.END)
        self.name_entry.insert(0, obj.name)
        self.desc_text.delete(1.0, tk.END)
        if self.editing_mode.get() == "global":
            self.desc_text.insert(1.0, obj.description)
            if self.obj_type == "characters":
                self.player_var.set(obj.is_player)
                self.player_check.config(state=tk.NORMAL)
        else:
            local_desc = self.app.local_descriptions.get(self.current_obj_id, "")
            self.desc_text.insert(1.0, local_desc)
            if self.obj_type == "characters":
                self.player_var.set(obj.is_player)
                self.player_check.config(state=tk.DISABLED)

    def _clear_form(self):
        self.current_obj_id = None
        self.name_entry.delete(0, tk.END)
        self.desc_text.delete(1.0, tk.END)
        if self.obj_type == "characters":
            self.player_var.set(False)
            self.player_check.config(state=tk.NORMAL)
        self.reset_local_btn.config(state=tk.DISABLED)

    def _create_new(self):
        default_name = "Новый объект"
        default_desc = ""
        data = {"name": default_name, "description": default_desc}
        if self.obj_type == "characters":
            data["is_player"] = False
        if self.obj_type == "narrators":
            self.app.update("update_narrator", data)
        elif self.obj_type == "characters":
            self.app.update("create_character", data)
        elif self.obj_type == "locations":
            self.app.update("create_location", data)
        elif self.obj_type == "items":
            self.app.update("create_item", data)

    def _delete_selected(self):
        if not self.current_obj_id:
            return
        obj = self._get_objects_dict().get(self.current_obj_id)
        if not obj:
            return
        if messagebox.askyesno("Удаление", f"Удалить '{obj.name}'?"):
            if self.obj_type == "narrators":
                self.app.update("delete_narrator", {"id": self.current_obj_id})
            elif self.obj_type == "characters":
                self.app.update("delete_character", {"id": self.current_obj_id})
            elif self.obj_type == "locations":
                self.app.update("delete_location", {"id": self.current_obj_id})
            elif self.obj_type == "items":
                self.app.update("delete_item", {"id": self.current_obj_id})

    def _save_current(self):
        name = self.name_entry.get().strip()
        desc = self.desc_text.get(1.0, tk.END).strip()
        if not name:
            messagebox.showwarning("Ошибка", "Введите название")
            return
        if self.editing_mode.get() == "global":
            if not self.current_obj_id:
                data = {"name": name, "description": desc}
                if self.obj_type == "characters":
                    data["is_player"] = self.player_var.get()
                if self.obj_type == "narrators":
                    self.app.update("update_narrator", data)
                elif self.obj_type == "characters":
                    self.app.update("create_character", data)
                elif self.obj_type == "locations":
                    self.app.update("create_location", data)
                elif self.obj_type == "items":
                    self.app.update("create_item", data)
            else:
                data = {"id": self.current_obj_id, "name": name, "description": desc}
                if self.obj_type == "characters":
                    data["is_player"] = self.player_var.get()
                if self.obj_type == "narrators":
                    self.app.update("update_narrator", data)
                elif self.obj_type == "characters":
                    self.app.update("update_character", data)
                elif self.obj_type == "locations":
                    self.app.update("update_location", data)
                elif self.obj_type == "items":
                    self.app.update("update_item", data)
        else:
            if self.current_obj_id:
                self.app.update("set_local_description", {"obj_id": self.current_obj_id, "description": desc})
                self.reset_local_btn.config(state=tk.NORMAL if desc.strip() else tk.DISABLED)

    def _reset_local(self):
        if self.current_obj_id and self.current_obj_id in self.app.local_descriptions:
            if messagebox.askyesno("Сброс", "Удалить локальное описание?"):
                self.app.update("clear_local_description", {"obj_id": self.current_obj_id})
                if self.editing_mode.get() == "local":
                    self.desc_text.delete(1.0, tk.END)
                    self.reset_local_btn.config(state=tk.DISABLED)

    def _on_select(self, event):
        selection = self.listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        objects_dict = self._get_objects_dict()
        sorted_ids = sorted(objects_dict.keys(), key=self._extract_num)
        if idx < len(sorted_ids):
            obj_id = sorted_ids[idx]
            self.current_obj_id = obj_id
            self._load_current_description()
            local_exists = obj_id in self.app.local_descriptions
            self.reset_local_btn.config(state=tk.NORMAL if local_exists else tk.DISABLED)

    def _select_object_by_id(self, obj_id: str):
        objects_dict = self._get_objects_dict()
        if obj_id not in objects_dict:
            return
        self.current_obj_id = obj_id
        self._load_current_description()
        local_exists = obj_id in self.app.local_descriptions
        self.reset_local_btn.config(state=tk.NORMAL if local_exists else tk.DISABLED)
        sorted_ids = sorted(objects_dict.keys(), key=self._extract_num)
        try:
            pos = sorted_ids.index(obj_id)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(pos)
            self.listbox.see(pos)
        except ValueError:
            pass

    def _on_player_flag_change(self):
        if self.editing_mode.get() == "global" and self.current_obj_id:
            obj = self._get_objects_dict().get(self.current_obj_id)
            if obj and obj.is_player != self.player_var.get():
                data = {
                    "id": self.current_obj_id,
                    "name": obj.name,
                    "description": obj.description,
                    "is_player": self.player_var.get()
                }
                self.app.update("update_character", data)

# ---------- Вкладка "Системные промты" ----------
class SystemPromptsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.current_prompt_name = None
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        top_frame = ttk.LabelFrame(self, text="Список системных промтов")
        top_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.listbox = tk.Listbox(top_frame, height=8)
        scrollbar = ttk.Scrollbar(top_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        btn_frame = ttk.Frame(top_frame)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Создать", command=self._create_new).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить", command=self._delete_selected).pack(side=tk.LEFT, padx=5)

        editor_frame = ttk.LabelFrame(self, text="Редактор промта")
        editor_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.name_label = ttk.Label(editor_frame, text="Название:")
        self.name_label.pack(anchor='w', padx=5, pady=2)
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(editor_frame, textvariable=self.name_var, state='readonly')
        self.name_entry.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(editor_frame, text="Содержимое:").pack(anchor='w', padx=5, pady=2)
        self.text_editor = scrolledtext.ScrolledText(editor_frame, wrap=tk.WORD, height=12)
        self.text_editor.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        add_context_menu(self.text_editor)
        btn_frame2 = ttk.Frame(editor_frame)
        btn_frame2.pack(fill=tk.X, pady=5)
        self.save_btn = ttk.Button(btn_frame2, text="Сохранить", command=self._save_current)
        self.save_btn.pack(side=tk.RIGHT, padx=5)
        self.save_btn.config(state=tk.DISABLED)

    def refresh(self):
        self.listbox.delete(0, tk.END)
        prompts = self.app.prompt_manager.list_prompts()
        for name in sorted(prompts):
            if not name.startswith("translator_"):
                self.listbox.insert(tk.END, name)
        self._clear_editor()

    def add_prompt(self, name: str):
        if name.startswith("translator_"):
            return
        self.refresh()
        for i in range(self.listbox.size()):
            if self.listbox.get(i) == name:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(i)
                self.listbox.see(i)
                self._on_select(None)
                break

    def update_prompt(self, name: str):
        if name.startswith("translator_"):
            return
        if self.current_prompt_name == name:
            content = self.app.prompt_manager.get_prompt_content(name)
            self.text_editor.delete(1.0, tk.END)
            self.text_editor.insert(1.0, content)

    def remove_prompt(self, name: str):
        if name.startswith("translator_"):
            return
        self.refresh()
        if self.current_prompt_name == name:
            self._clear_editor()

    def _on_select(self, event):
        selection = self.listbox.curselection()
        if not selection:
            return
        name = self.listbox.get(selection[0])
        self.current_prompt_name = name
        content = self.app.prompt_manager.get_prompt_content(name)
        self.name_var.set(name)
        self.text_editor.delete(1.0, tk.END)
        self.text_editor.insert(1.0, content)
        self.save_btn.config(state=tk.NORMAL)

    def _save_current(self):
        if not self.current_prompt_name:
            return
        new_content = self.text_editor.get(1.0, tk.END).strip()
        self.app.update("update_prompt", {"name": self.current_prompt_name, "content": new_content})
        messagebox.showinfo("Сохранено", f"Промт '{self.current_prompt_name}' сохранён.")

    def _clear_editor(self):
        self.current_prompt_name = None
        self.name_var.set("")
        self.text_editor.delete(1.0, tk.END)
        self.save_btn.config(state=tk.DISABLED)

    def _create_new(self):
        name = simpledialog.askstring("Новый промт", "Введите имя нового промта (без префикса 'translator_'):")
        if name:
            if name.startswith("translator_"):
                messagebox.showwarning("Недопустимое имя", "Имя не должно начинаться с 'translator_'.")
                return
            self.app.update("create_prompt", {"name": name})

    def _delete_selected(self):
        if not self.current_prompt_name:
            return
        if self.current_prompt_name in self.app.prompt_manager.default_prompts:
            messagebox.showwarning("Удаление", "Нельзя удалить стандартный промт.")
            return
        self.app.update("delete_prompt", {"name": self.current_prompt_name})

# ---------- Вкладка "Промты переводчика" ----------
class TranslatorPromptsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.current_prompt_name = None
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        top_frame = ttk.LabelFrame(self, text="Список промтов переводчика")
        top_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.listbox = tk.Listbox(top_frame, height=8)
        scrollbar = ttk.Scrollbar(top_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        btn_frame = ttk.Frame(top_frame)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Создать", command=self._create_new).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить", command=self._delete_selected).pack(side=tk.LEFT, padx=5)

        editor_frame = ttk.LabelFrame(self, text="Редактор промта переводчика")
        editor_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.name_label = ttk.Label(editor_frame, text="Название:")
        self.name_label.pack(anchor='w', padx=5, pady=2)
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(editor_frame, textvariable=self.name_var, state='readonly')
        self.name_entry.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(editor_frame, text="Содержимое:").pack(anchor='w', padx=5, pady=2)
        self.text_editor = scrolledtext.ScrolledText(editor_frame, wrap=tk.WORD, height=12)
        self.text_editor.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        add_context_menu(self.text_editor)
        btn_frame2 = ttk.Frame(editor_frame)
        btn_frame2.pack(fill=tk.X, pady=5)
        self.save_btn = ttk.Button(btn_frame2, text="Сохранить", command=self._save_current)
        self.save_btn.pack(side=tk.RIGHT, padx=5)
        self.save_btn.config(state=tk.DISABLED)

    def refresh(self):
        self.listbox.delete(0, tk.END)
        prompts = self.app.prompt_manager.list_prompts()
        for name in sorted(prompts):
            if name.startswith("translator_"):
                display_name = name[len("translator_"):] if name != "translator_system" else name
                self.listbox.insert(tk.END, display_name)
        self._clear_editor()

    def add_prompt(self, name: str):
        if not name.startswith("translator_"):
            return
        self.refresh()
        display_name = name[len("translator_"):] if name != "translator_system" else name
        for i in range(self.listbox.size()):
            if self.listbox.get(i) == display_name:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(i)
                self.listbox.see(i)
                self._on_select(None)
                break

    def update_prompt(self, name: str):
        if not name.startswith("translator_"):
            return
        if self.current_prompt_name == name:
            content = self.app.prompt_manager.get_prompt_content(name)
            self.text_editor.delete(1.0, tk.END)
            self.text_editor.insert(1.0, content)

    def remove_prompt(self, name: str):
        if not name.startswith("translator_"):
            return
        self.refresh()
        if self.current_prompt_name == name:
            self._clear_editor()

    def _on_select(self, event):
        selection = self.listbox.curselection()
        if not selection:
            return
        display_name = self.listbox.get(selection[0])
        if display_name == "translator_system":
            full_name = "translator_system"
        else:
            full_name = f"translator_{display_name}"
        self.current_prompt_name = full_name
        content = self.app.prompt_manager.get_prompt_content(full_name)
        self.name_var.set(display_name)
        self.text_editor.delete(1.0, tk.END)
        self.text_editor.insert(1.0, content)
        self.save_btn.config(state=tk.NORMAL)

    def _save_current(self):
        if not self.current_prompt_name:
            return
        new_content = self.text_editor.get(1.0, tk.END).strip()
        self.app.update("update_prompt", {"name": self.current_prompt_name, "content": new_content})
        messagebox.showinfo("Сохранено", f"Промт переводчика '{self.current_prompt_name}' сохранён.")

    def _clear_editor(self):
        self.current_prompt_name = None
        self.name_var.set("")
        self.text_editor.delete(1.0, tk.END)
        self.save_btn.config(state=tk.DISABLED)

    def _create_new(self):
        name = simpledialog.askstring("Новый промт переводчика", "Введите имя нового промта (без префикса 'translator_'):")
        if name:
            if name.startswith("translator_"):
                messagebox.showwarning("Недопустимое имя", "Имя не должно начинаться с 'translator_'.")
                return
            full_name = f"translator_{name}"
            self.app.update("create_prompt", {"name": full_name})

    def _delete_selected(self):
        if not self.current_prompt_name:
            return
        if self.current_prompt_name == "translator_system":
            messagebox.showwarning("Удаление", "Нельзя удалить стандартный промт переводчика.")
            return
        self.app.update("delete_prompt", {"name": self.current_prompt_name})

# ---------- Вкладка "Этапы" (порядок системных сообщений) ----------
# ---------- Вкладка "Этапы" (с русскими названиями и тултипами) ----------
class StagePromptsTab(ttk.Frame):
    # Соответствие: отображаемое имя → техническое имя (ключ в конфиге)
    STAGE_MAPPING = [
        ("0. Сообщение игрока", "stage0_user_message"),
        ("1. Запрос описаний", "stage1_request_descriptions"),
        ("2. Валидация сцены", "stage1_validate_scene"),
        ("3. Проверка правдивости", "stage1_truth_check"),
        ("4. Действие игрока (d20)", "stage1_player_action"),
        ("5. Случайное событие (d100)", "stage1_random_event"),
        ("5.1. Запрос объектов для события", "stage1_random_event_continue"),
        ("5.2. Проверка события", "stage1_validate_random_event"),
        ("7. Планы NPC", "stage2_npc_action"),
        ("8. Финальный рассказ", "stage3_final"),
        ("9. Краткая выжимка", "stage4_summary"),
    ]

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.current_stage = None          # хранит техническое имя выбранного этапа
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        info_frame = ttk.LabelFrame(self, text="Важно: порядок системных сообщений")
        info_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        info_text = (
            "Сообщения передаются модели в том порядке, в котором они перечислены (сверху вниз).\n"
            "Модель лучше запоминает последние сообщения, поэтому самые важные инструкции\n"
            "рекомендуется размещать в КОНЦЕ списка (нижняя часть).\n"
            "Используйте кнопки «Вверх» / «Вниз» для изменения приоритета."
        )
        ttk.Label(info_frame, text=info_text, wraplength=700, justify=tk.LEFT).pack(padx=5, pady=5)

        main_row = ttk.Frame(self)
        main_row.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        main_row.grid_columnconfigure(0, weight=1)
        main_row.grid_columnconfigure(1, weight=3)

        left_frame = ttk.LabelFrame(main_row, text="Этапы (наведите для полного имени)")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        left_frame.grid_rowconfigure(0, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        self.stage_listbox = tk.Listbox(left_frame, height=12, font=("Arial", 10))
        # Вставляем отображаемые имена
        for display_name, _ in self.STAGE_MAPPING:
            self.stage_listbox.insert(tk.END, display_name)
        self.stage_listbox.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        stage_scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.stage_listbox.yview)
        stage_scrollbar.grid(row=0, column=1, sticky="ns", pady=5)
        self.stage_listbox.configure(yscrollcommand=stage_scrollbar.set)
        self.stage_listbox.bind("<<ListboxSelect>>", self._on_stage_select)

        # --- Tooltip для списка этапов ---
        self._setup_tooltips()

        right_frame = ttk.LabelFrame(main_row, text="Системные промты для выбранного этапа (порядок важен)")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        list_container = ttk.Frame(right_frame)
        list_container.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        list_container.grid_rowconfigure(0, weight=1)
        list_container.grid_columnconfigure(0, weight=1)

        self.prompts_listbox = tk.Listbox(list_container, height=10, font=("Arial", 10))
        self.prompts_listbox.grid(row=0, column=0, sticky="nsew")
        prompts_scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.prompts_listbox.yview)
        prompts_scrollbar.grid(row=0, column=1, sticky="ns")
        self.prompts_listbox.configure(yscrollcommand=prompts_scrollbar.set)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        ttk.Button(btn_frame, text="➕ Добавить системный промт", command=self._add_prompt).grid(row=0, column=0, padx=3, pady=2, sticky="ew")
        ttk.Button(btn_frame, text="📚 Добавить рассказчиков", command=self._add_narrators).grid(row=0, column=1, padx=3, pady=2, sticky="ew")
        ttk.Button(btn_frame, text="❌ Удалить выбранный", command=self._remove_prompt).grid(row=1, column=0, padx=3, pady=2, sticky="ew")
        ttk.Button(btn_frame, text="🗑️ Удалить всех рассказчиков", command=self._remove_all_narrators).grid(row=1, column=1, padx=3, pady=2, sticky="ew")
        ttk.Button(btn_frame, text="⬆️ Вверх", command=lambda: self._move_prompt(-1)).grid(row=2, column=0, padx=3, pady=2, sticky="ew")
        ttk.Button(btn_frame, text="⬇️ Вниз", command=lambda: self._move_prompt(1)).grid(row=2, column=1, padx=3, pady=2, sticky="ew")
        ttk.Button(btn_frame, text="📜 Добавить историю чата", command=self._add_history).grid(row=3, column=0, padx=3, pady=2, sticky="ew")
        ttk.Button(btn_frame, text="💾 Сохранить", command=self._save_config).grid(row=3, column=1, padx=3, pady=2, sticky="ew")

    def _setup_tooltips(self):
        """Добавляет всплывающие подсказки для списка этапов."""
        self.tooltip_window = None
        self.tooltip_item = None

        def show_tooltip(event):
            idx = self.stage_listbox.nearest(event.y)
            if idx < 0 or idx >= len(self.STAGE_MAPPING):
                return
            bbox = self.stage_listbox.bbox(idx)
            if not bbox or not (bbox[1] <= event.y <= bbox[1] + bbox[3]):
                self.hide_tooltip()
                return
            if self.tooltip_item == idx:
                return
            self.hide_tooltip()
            self.tooltip_item = idx
            tech_name = self.STAGE_MAPPING[idx][1]
            x = event.x_root + 15
            y = event.y_root + 10
            self.tooltip_window = tk.Toplevel(self.stage_listbox)
            self.tooltip_window.wm_overrideredirect(True)
            self.tooltip_window.wm_geometry(f"+{x}+{y}")
            label = tk.Label(self.tooltip_window, text=tech_name, background="#ffffe0", relief=tk.SOLID, borderwidth=1, font=("Arial", 9))
            label.pack()

        def hide_tooltip(event=None):
            if self.tooltip_window:
                self.tooltip_window.destroy()
                self.tooltip_window = None
            self.tooltip_item = None

        self.stage_listbox.bind("<Motion>", show_tooltip)
        self.stage_listbox.bind("<Leave>", hide_tooltip)

    def hide_tooltip(self):
        if hasattr(self, 'tooltip_window') and self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None
        self.tooltip_item = None

    def _on_stage_select(self, event):
        selection = self.stage_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        # По индексу получаем техническое имя
        self.current_stage = self.STAGE_MAPPING[idx][1]
        self._refresh_prompts_list()

    def _add_prompt(self):
        if not self.current_stage:
            messagebox.showwarning("Ошибка", "Сначала выберите этап")
            return
        all_prompts = self.app.prompt_manager.list_prompts()
        all_prompts = [p for p in all_prompts if not p.startswith("translator_")]
        if not all_prompts:
            messagebox.showinfo("Нет промтов", "Сначала создайте хотя бы один системный промт во вкладке 'Системные промты'.")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Выберите системный промт")
        dialog.geometry("400x300")
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text="Доступные промты:").pack(pady=5)
        listbox = tk.Listbox(dialog, height=15)
        listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        for p in all_prompts:
            listbox.insert(tk.END, p)

        def on_select():
            sel = listbox.curselection()
            if sel:
                selected = listbox.get(sel[0])
                current = self.app.stage_prompts_config.get(self.current_stage, [])
                if selected not in current:
                    current.append(selected)
                    self.app.stage_prompts_config[self.current_stage] = current
                    self._refresh_prompts_list()
                    self.app.save_stage_prompts_config()
                dialog.destroy()

        ttk.Button(dialog, text="Выбрать", command=on_select).pack(pady=5)
        ttk.Button(dialog, text="Отмена", command=dialog.destroy).pack(pady=2)
        listbox.bind("<Double-Button-1>", lambda e: on_select())

    def _add_narrators(self):
        if not self.current_stage:
            messagebox.showwarning("Ошибка", "Сначала выберите этап")
            return
        enabled_narrators = self.app.current_profile.enabled_narrators
        if not enabled_narrators:
            messagebox.showinfo("Нет рассказчиков", "В текущем профиле не выбран ни один рассказчик.")
            return

        current = self.app.stage_prompts_config.get(self.current_stage, [])
        sel = self.prompts_listbox.curselection()
        insert_idx = sel[0] if sel else len(current)

        new_entries = [f"narrator:{nid}" for nid in enabled_narrators if nid in self.app.narrators]
        if not new_entries:
            messagebox.showinfo("Нет рассказчиков", "Выбранные рассказчики не найдены в базе.")
            return

        for i, entry in enumerate(new_entries):
            current.insert(insert_idx + i, entry)

        self.app.stage_prompts_config[self.current_stage] = current
        self._refresh_prompts_list()
        if new_entries:
            self.prompts_listbox.selection_set(insert_idx)
            self.prompts_listbox.see(insert_idx)
        self.app.save_stage_prompts_config()
        messagebox.showinfo("Рассказчики добавлены", f"Добавлено {len(new_entries)} рассказчиков.")

    def _remove_all_narrators(self):
        if not self.current_stage:
            return
        current = self.app.stage_prompts_config.get(self.current_stage, [])
        new_list = [entry for entry in current if not entry.startswith("narrator:")]
        if len(new_list) == len(current):
            messagebox.showinfo("Нет рассказчиков", "В текущем этапе нет рассказчиков.")
            return
        self.app.stage_prompts_config[self.current_stage] = new_list
        self._refresh_prompts_list()
        self.app.save_stage_prompts_config()
        messagebox.showinfo("Удаление", "Все рассказчики удалены из текущего этапа.")

    def _remove_prompt(self):
        selection = self.prompts_listbox.curselection()
        if not selection or not self.current_stage:
            return
        idx = selection[0]
        current = self.app.stage_prompts_config.get(self.current_stage, [])
        if idx < len(current):
            del current[idx]
            self.app.stage_prompts_config[self.current_stage] = current
            self._refresh_prompts_list()
            self.app.save_stage_prompts_config()

    def _move_prompt(self, delta):
        selection = self.prompts_listbox.curselection()
        if not selection or not self.current_stage:
            return
        idx = selection[0]
        current = self.app.stage_prompts_config.get(self.current_stage, [])
        new_idx = idx + delta
        if 0 <= new_idx < len(current):
            item = current.pop(idx)
            current.insert(new_idx, item)
            self.app.stage_prompts_config[self.current_stage] = current
            self._refresh_prompts_list()
            self.prompts_listbox.selection_set(new_idx)
            self.app.save_stage_prompts_config()

    def _save_config(self):
        self.app.save_stage_prompts_config()
        messagebox.showinfo("Сохранено", "Конфигурация этапов сохранена.")

    def refresh(self):
        self._refresh_prompts_list()

    def _add_history(self):
        if not self.current_stage:
            messagebox.showwarning("Ошибка", "Сначала выберите этап")
            return

        # Диалог выбора количества сообщений
        dialog = tk.Toplevel(self)
        dialog.title("Добавить историю чата")
        dialog.geometry("320x150")
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text="Сколько последних сообщений добавить?\n(0 = не добавлять, 1-50 = число сообщений)").pack(pady=10)
        spin = ttk.Spinbox(dialog, from_=0, to=50, width=10)
        spin.set("5")
        spin.pack(pady=5)

        def on_ok():
            try:
                count = int(spin.get())
            except:
                count = 0
            if count < 0:
                count = 0
            entry = f"history:{count}"
            current = self.app.stage_prompts_config.get(self.current_stage, [])
            sel = self.prompts_listbox.curselection()
            idx = sel[0] if sel else len(current)
            current.insert(idx, entry)
            self.app.stage_prompts_config[self.current_stage] = current
            self._refresh_prompts_list()
            if sel:
                self.prompts_listbox.selection_set(idx)
            self.app.save_stage_prompts_config()
            dialog.destroy()

        ttk.Button(dialog, text="ОК", command=on_ok).pack(pady=10)
        dialog.bind("<Return>", lambda e: on_ok())

    def _refresh_prompts_list(self):
        self.prompts_listbox.delete(0, tk.END)
        if not self.current_stage:
            return
        prompts = self.app.stage_prompts_config.get(self.current_stage, [])
        for entry in prompts:
            if entry.startswith("narrator:"):
                narr_id = entry[9:]
                narr = self.app.narrators.get(narr_id)
                display = f"📖 {narr.name if narr else narr_id}"
            elif entry.startswith("history:"):
                parts = entry.split(":", 1)
                count = parts[1] if len(parts) > 1 else "0"
                if count == "0":
                    display = "📜 История (отключена)"
                else:
                    display = f"📜 История ({count} последних сообщ.)"
            else:
                display = f"💬 {entry}"
            self.prompts_listbox.insert(tk.END, display)

    def cleanup_inactive_narrators(self):
        active_narrator_ids = set(self.app.current_profile.enabled_narrators) & set(self.app.narrators.keys())
        changed = False
        for display, tech in self.STAGE_MAPPING:
            config = self.app.stage_prompts_config.get(tech, [])
            new_config = []
            for entry in config:
                if entry.startswith("narrator:"):
                    narr_id = entry[9:]
                    if narr_id in active_narrator_ids:
                        new_config.append(entry)
                    else:
                        changed = True
                else:
                    new_config.append(entry)
            if new_config != config:
                self.app.stage_prompts_config[tech] = new_config
        if changed:
            self.app.save_stage_prompts_config()
            if self.current_stage:
                self._refresh_prompts_list()