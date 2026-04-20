# ui_tabs.py
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog, filedialog
import re
import os
import shutil
from PIL import Image, ImageTk, ImageDraw
from models import Narrator, Character, Location, Item, Event, Scenario, Emotion

# ---------- Вспомогательная функция контекстного меню ----------
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

# ---------- Вспомогательная функция центрирования окна ----------
def center_window(window, parent):
    """Центрирует окно window относительно родительского окна parent."""
    window.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (window.winfo_width() // 2)
    y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (window.winfo_height() // 2)
    window.geometry(f"+{x}+{y}")

# ---------- Редактор для вырезания аватара из спрайта ----------
class AvatarCropEditor(tk.Toplevel):
    """Окно для вырезания квадратной аватарки из спрайта."""
    def __init__(self, parent, sprite_path, callback):
        super().__init__(parent)
        self.title("Вырезать аватар из спрайта")
        self.transient(parent)
        self.grab_set()
        self.callback = callback
        self.sprite_path = sprite_path
        self.original_image = None
        self.photo = None
        self.crop_rect = None
        self.rect_id = None
        self.resize_handles = []
        self.dragging = False
        self.drag_start = None
        self.resize_mode = None
        self.crop_size = 256  # целевой размер аватара в пикселях (квадрат)

        self._load_image()
        self._build_ui()
        self._draw_initial_rect()
        self._bind_events()
        center_window(self, parent)

    def _load_image(self):
        if not self.sprite_path or not os.path.exists(self.sprite_path):
            messagebox.showerror("Ошибка", "Файл спрайта не найден.", parent=self)
            self.destroy()
            return
        try:
            self.original_image = Image.open(self.sprite_path).convert("RGBA")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить изображение:\n{e}", parent=self)
            self.destroy()

    def _build_ui(self):
        # Фрейм для canvas
        self.canvas_frame = ttk.Frame(self)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.canvas = tk.Canvas(self.canvas_frame, bg="gray", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Нижняя панель с кнопками и информацией
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(bottom_frame, text="Размер рамки (пикс. исходного):").pack(side=tk.LEFT, padx=5)
        self.size_var = tk.StringVar(value=str(self.crop_size))
        self.size_spin = ttk.Spinbox(bottom_frame, from_=32, to=512, increment=8, width=6, textvariable=self.size_var)
        self.size_spin.pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="Применить размер", command=self._apply_size).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="Сохранить", command=self._save_crop).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="Отмена", command=self.destroy).pack(side=tk.LEFT, padx=5)

        self.info_label = ttk.Label(bottom_frame, text="")
        self.info_label.pack(side=tk.RIGHT, padx=5)

    def _draw_initial_rect(self):
        if self.original_image is None:
            return
        # Масштабируем изображение под размер canvas
        self._resize_image_to_canvas()
        # Рисуем начальный прямоугольник (в центре, размером crop_size в координатах исходного)
        self._update_rect_from_size()

    def _resize_image_to_canvas(self):
        self.canvas.update_idletasks()
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w < 10 or canvas_h < 10:
            canvas_w, canvas_h = 800, 600
            self.canvas.config(width=canvas_w, height=canvas_h)
        img_w, img_h = self.original_image.size
        scale = min(canvas_w / img_w, canvas_h / img_h, 1.0)
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)
        self.display_image = self.original_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(self.display_image)
        self.canvas.delete("image")
        self.canvas.create_image(canvas_w//2, canvas_h//2, anchor=tk.CENTER, image=self.photo, tags="image")
        self.scale = scale
        self.offset_x = (canvas_w - new_w) // 2
        self.offset_y = (canvas_h - new_h) // 2

    def _update_rect_from_size(self):
        # Рисуем квадрат заданного размера в центре (в координатах исходного изображения)
        if self.original_image is None:
            return
        img_w, img_h = self.original_image.size
        # Размер в пикселях исходного
        size = self.crop_size
        # Ограничиваем размерами изображения
        if size > img_w:
            size = img_w
        if size > img_h:
            size = img_h
        # Центр
        center_x = img_w // 2
        center_y = img_h // 2
        left = center_x - size // 2
        top = center_y - size // 2
        right = left + size
        bottom = top + size
        # Корректируем, чтобы не выходило за границы
        if left < 0:
            left = 0
            right = size
        if right > img_w:
            right = img_w
            left = img_w - size
        if top < 0:
            top = 0
            bottom = size
        if bottom > img_h:
            bottom = img_h
            top = img_h - size
        self.crop_rect = (left, top, right, bottom)
        self._draw_rect()

    def _draw_rect(self):
        if self.rect_id:
            self.canvas.delete(self.rect_id)
            for handle in self.resize_handles:
                self.canvas.delete(handle)
            self.resize_handles.clear()
        # Преобразуем координаты из исходного в экранные
        x1 = self.offset_x + self.crop_rect[0] * self.scale
        y1 = self.offset_y + self.crop_rect[1] * self.scale
        x2 = self.offset_x + self.crop_rect[2] * self.scale
        y2 = self.offset_y + self.crop_rect[3] * self.scale
        self.rect_id = self.canvas.create_rectangle(x1, y1, x2, y2, outline="red", width=2, tags="rect")
        # Рисуем маркеры для изменения размера (по углам)
        handle_size = 8
        for x, y in [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]:
            handle = self.canvas.create_rectangle(x - handle_size//2, y - handle_size//2,
                                                  x + handle_size//2, y + handle_size//2,
                                                  fill="yellow", outline="black", tags="handle")
            self.resize_handles.append(handle)
        self._update_info()

    def _update_info(self):
        w = self.crop_rect[2] - self.crop_rect[0]
        h = self.crop_rect[3] - self.crop_rect[1]
        self.info_label.config(text=f"Выделено: {w}x{h} пикс. (целевой размер {self.crop_size}x{self.crop_size})")

    def _bind_events(self):
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

    def _on_press(self, event):
        # Определяем, попали ли в маркер или внутрь прямоугольника
        x, y = event.x, event.y
        # Проверка маркеров
        for i, handle in enumerate(self.resize_handles):
            coords = self.canvas.coords(handle)
            if coords[0] <= x <= coords[2] and coords[1] <= y <= coords[3]:
                self.resize_mode = i  # 0-левый верх, 1-правый верх, 2-левый низ, 3-правый низ
                self.drag_start = (x, y)
                self.dragging = True
                return
        # Проверка попадания в прямоугольник
        rect_coords = self.canvas.coords(self.rect_id)
        if rect_coords[0] <= x <= rect_coords[2] and rect_coords[1] <= y <= rect_coords[3]:
            self.resize_mode = "move"
            self.drag_start = (x, y)
            self.dragging = True

    def _on_drag(self, event):
        if not self.dragging:
            return
        x, y = event.x, event.y
        dx = x - self.drag_start[0]
        dy = y - self.drag_start[1]
        if self.resize_mode == "move":
            # Перемещение прямоугольника
            new_coords = [self.canvas.coords(self.rect_id)[0] + dx,
                          self.canvas.coords(self.rect_id)[1] + dy,
                          self.canvas.coords(self.rect_id)[2] + dx,
                          self.canvas.coords(self.rect_id)[3] + dy]
            # Преобразуем в координаты исходного изображения
            left = (new_coords[0] - self.offset_x) / self.scale
            top = (new_coords[1] - self.offset_y) / self.scale
            right = (new_coords[2] - self.offset_x) / self.scale
            bottom = (new_coords[3] - self.offset_y) / self.scale
            # Ограничения по границам исходного изображения
            img_w, img_h = self.original_image.size
            width = right - left
            height = bottom - top
            if left < 0:
                left = 0
                right = width
            if right > img_w:
                right = img_w
                left = img_w - width
            if top < 0:
                top = 0
                bottom = height
            if bottom > img_h:
                bottom = img_h
                top = img_h - height
            self.crop_rect = (int(left), int(top), int(right), int(bottom))
            self._draw_rect()
            self.drag_start = (x, y)
        else:
            # Изменение размера через маркеры
            idx = self.resize_mode
            rect_coords = self.canvas.coords(self.rect_id)
            # Преобразуем в координаты исходного
            left = (rect_coords[0] - self.offset_x) / self.scale
            top = (rect_coords[1] - self.offset_y) / self.scale
            right = (rect_coords[2] - self.offset_x) / self.scale
            bottom = (rect_coords[3] - self.offset_y) / self.scale
            # Меняем соответствующий угол
            if idx == 0:  # левый верх
                new_left = left + dx / self.scale
                new_top = top + dy / self.scale
                if new_left < 0:
                    new_left = 0
                if new_top < 0:
                    new_top = 0
                # Сохраняем квадратность? Лучше сохранять соотношение? Для аватара квадрат
                # Делаем так, чтобы новая сторона была равна min(ширина, высота) – но пользователь может сам корректировать
                # Просто позволяем менять, но потом кнопка "Применить размер" выровняет
                self.crop_rect = (int(new_left), int(new_top), int(right), int(bottom))
            elif idx == 1:  # правый верх
                new_right = right + dx / self.scale
                new_top = top + dy / self.scale
                if new_right > self.original_image.size[0]:
                    new_right = self.original_image.size[0]
                if new_top < 0:
                    new_top = 0
                self.crop_rect = (int(left), int(new_top), int(new_right), int(bottom))
            elif idx == 2:  # левый низ
                new_left = left + dx / self.scale
                new_bottom = bottom + dy / self.scale
                if new_left < 0:
                    new_left = 0
                if new_bottom > self.original_image.size[1]:
                    new_bottom = self.original_image.size[1]
                self.crop_rect = (int(new_left), int(top), int(right), int(new_bottom))
            elif idx == 3:  # правый низ
                new_right = right + dx / self.scale
                new_bottom = bottom + dy / self.scale
                if new_right > self.original_image.size[0]:
                    new_right = self.original_image.size[0]
                if new_bottom > self.original_image.size[1]:
                    new_bottom = self.original_image.size[1]
                self.crop_rect = (int(left), int(top), int(new_right), int(new_bottom))
            # После изменения размера перерисовываем
            self._draw_rect()
            self.drag_start = (x, y)

    def _on_release(self, event):
        self.dragging = False
        self.resize_mode = None

    def _apply_size(self):
        # Устанавливаем фиксированный размер квадрата (в пикселях исходного)
        try:
            new_size = int(self.size_var.get())
        except ValueError:
            new_size = self.crop_size
        if new_size < 8:
            new_size = 8
        self.crop_size = new_size
        # Пересчитываем прямоугольник, сохраняя центр
        if self.original_image is None:
            return
        img_w, img_h = self.original_image.size
        center_x = (self.crop_rect[0] + self.crop_rect[2]) // 2
        center_y = (self.crop_rect[1] + self.crop_rect[3]) // 2
        half = self.crop_size // 2
        left = center_x - half
        top = center_y - half
        right = left + self.crop_size
        bottom = top + self.crop_size
        # Коррекция границ
        if left < 0:
            left = 0
            right = self.crop_size
        if right > img_w:
            right = img_w
            left = img_w - self.crop_size
        if top < 0:
            top = 0
            bottom = self.crop_size
        if bottom > img_h:
            bottom = img_h
            top = img_h - self.crop_size
        self.crop_rect = (int(left), int(top), int(right), int(bottom))
        self._draw_rect()

    def _save_crop(self):
        if self.original_image is None:
            return
        left, top, right, bottom = self.crop_rect
        if right <= left or bottom <= top:
            messagebox.showerror("Ошибка", "Выделенная область некорректна.", parent=self)
            return
        cropped = self.original_image.crop((left, top, right, bottom))
        # Приводим к квадрату указанного размера (crop_size)
        target_size = self.crop_size
        cropped = cropped.resize((target_size, target_size), Image.Resampling.LANCZOS)
        # Сохраняем во временный файл
        temp_dir = os.path.join(self.master.app.storage._get_campaign_path(), "temp")
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, f"cropped_avatar_{os.path.basename(self.sprite_path)}.png")
        cropped.save(temp_path, "PNG")
        # Перемещаем в папку кампании
        rel_path = self.master._copy_image_to_campaign(temp_path, "characters/avatars")
        # Удаляем временный файл
        try:
            os.remove(temp_path)
        except:
            pass
        print(f"Cropped saved, rel_path = {rel_path}")
        self.callback(rel_path)
        self.destroy()


# ---------- Вкладка "Профиль" (с поддержкой событий и сценариев) ----------
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
        self.event_vars = {}
        self.scenario_vars = {}
        self.emotion_vars = {}

    def refresh(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        profile = self.app.current_profile
        profiles = self.app.list_profiles()
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

        if self.app.events:
            ttk.Label(self.scrollable_frame, text="События", font=('Arial', 10, 'bold')).pack(anchor='w', pady=(10,0))
            self.event_vars.clear()
            for eid, ev in self.app.events.items():
                var = tk.BooleanVar(value=(eid in profile.enabled_events))
                self.event_vars[eid] = var
                cb = ttk.Checkbutton(self.scrollable_frame, text=ev.name, variable=var, command=self._on_checkbox_change)
                cb.pack(anchor='w', padx=20)

        if self.app.scenarios:
            ttk.Label(self.scrollable_frame, text="Сценарии", font=('Arial', 10, 'bold')).pack(anchor='w', pady=(10,0))
            self.scenario_vars.clear()
            for sid, sc in self.app.scenarios.items():
                var = tk.BooleanVar(value=(sid in profile.enabled_scenarios))
                self.scenario_vars[sid] = var
                cb = ttk.Checkbutton(self.scrollable_frame, text=sc.name, variable=var, command=self._on_checkbox_change)
                cb.pack(anchor='w', padx=20)

        if self.app.emotions:
            ttk.Label(self.scrollable_frame, text="Эмоции", font=('Arial', 10, 'bold')).pack(anchor='w', pady=(10,0))
            self.emotion_vars.clear()
            for eid, em in self.app.emotions.items():
                var = tk.BooleanVar(value=(eid in profile.enabled_emotions))
                self.emotion_vars[eid] = var
                cb = ttk.Checkbutton(self.scrollable_frame, text=em.name, variable=var, command=self._on_checkbox_change)
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
        profile.enabled_events = [eid for eid, var in self.event_vars.items() if var.get()]
        profile.enabled_scenarios = [sid for sid, var in self.scenario_vars.items() if var.get()]
        profile.enabled_emotions = [eid for eid, var in self.emotion_vars.items() if var.get()]
        self.app.update("update_profile", {
            "enabled_narrators": profile.enabled_narrators,
            "enabled_characters": profile.enabled_characters,
            "enabled_locations": profile.enabled_locations,
            "enabled_items": profile.enabled_items,
            "enabled_events": profile.enabled_events,
            "enabled_scenarios": profile.enabled_scenarios,
            "enabled_emotions": profile.enabled_emotions
        })
        messagebox.showinfo("Профиль", "Настройки применены.")

    def _load_profile(self):
        name = self.profile_name_var.get()
        if name:
            self.app.update("load_profile", {"name": name})

    def _save_profile(self):
        name = self.app.current_profile.name
        if not name or name == "Default":
            new_name = simpledialog.askstring("Сохранить профиль", "Введите имя профиля:", initialvalue=name, parent=self)
            if not new_name:
                return
            self.app.current_profile.name = new_name
        self.app.update("save_profile")

    def _new_profile(self):
        name = simpledialog.askstring("Новый профиль", "Введите имя нового профиля:", parent=self)
        if not name:
            return
        self.app.update("new_profile", {"name": name})

# ---------- Базовый редактор для объектов (с прокруткой) ----------
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
        # Основная разметка вкладки
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ---------- Прокручиваемая область ----------
        main_canvas = tk.Canvas(self, borderwidth=0)
        v_scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=main_canvas.yview)
        main_canvas.configure(yscrollcommand=v_scrollbar.set)

        main_canvas.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")

        scrollable_frame = ttk.Frame(main_canvas)
        main_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", tags=("window",))

        def _on_canvas_configure(event):
            main_canvas.itemconfig("window", width=event.width)
        main_canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            main_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        main_canvas.bind("<MouseWheel>", _on_mousewheel)

        def _update_scrollregion(event=None):
            main_canvas.configure(scrollregion=main_canvas.bbox("all"))
        scrollable_frame.bind("<Configure>", _update_scrollregion)

        # ── Содержимое ──
        list_frame = ttk.LabelFrame(scrollable_frame, text=f"Список {self.title}")
        list_frame.pack(fill=tk.X, padx=5, pady=(5, 0))
        list_container = ttk.Frame(list_frame)
        list_container.pack(fill=tk.BOTH, expand=True)
        self.listbox = tk.Listbox(list_container, height=8)
        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        btn_frame = ttk.Frame(scrollable_frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(btn_frame, text="Создать", command=self._create_new).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить", command=self._delete_selected).pack(side=tk.LEFT, padx=5)

        mode_frame = ttk.LabelFrame(scrollable_frame, text="Режим редактирования")
        mode_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Radiobutton(mode_frame, text="Global", variable=self.editing_mode, value="global", command=self._on_mode_change).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(mode_frame, text="Session", variable=self.editing_mode, value="local", command=self._on_mode_change).pack(side=tk.LEFT, padx=5)
        self.reset_local_btn = ttk.Button(mode_frame, text="Сбросить локальное", command=self._reset_local, state=tk.DISABLED)
        self.reset_local_btn.pack(side=tk.RIGHT, padx=5)

        if self.obj_type == "characters":
            player_frame = ttk.Frame(scrollable_frame)
            player_frame.pack(fill=tk.X, padx=5, pady=5)
            self.player_check = ttk.Checkbutton(player_frame, text="Это персонаж игрока (ГГ)", variable=self.player_var, command=self._on_player_flag_change)
            self.player_check.pack(side=tk.LEFT)

        # ==================== ИЗОБРАЖЕНИЯ ====================

        # Для персонажей
        if self.obj_type == "characters":
            images_frame = ttk.LabelFrame(scrollable_frame, text="Изображения для визуальной новеллы")
            images_frame.pack(fill=tk.X, padx=5, pady=5)

            # Аватар (нейтральный) с кнопкой вырезания
            avatar_row = ttk.Frame(images_frame)
            avatar_row.pack(fill=tk.X, padx=5, pady=2)
            avatar_row.grid_columnconfigure(1, weight=1)

            ttk.Label(avatar_row, text="Аватар (нейтральный):").grid(row=0, column=0, sticky="w", padx=5)
            self.avatar_path_var = tk.StringVar()
            ttk.Entry(avatar_row, textvariable=self.avatar_path_var).grid(row=0, column=1, padx=5, sticky="ew")
            ttk.Button(avatar_row, text="+", width=3, command=self._select_avatar).grid(row=0, column=2, padx=2)
            ttk.Button(avatar_row, text="✗", width=3, command=lambda: self.avatar_path_var.set("")).grid(row=0, column=3, padx=2)
            # Кнопка "Вырезать из спрайта"
            self.crop_avatar_btn = ttk.Button(avatar_row, text="✂️", width=3, command=self._crop_avatar_from_sprite, state=tk.DISABLED)
            self.crop_avatar_btn.grid(row=0, column=4, padx=2)

            self.avatar_preview_label = ttk.Label(avatar_row, text="[Нет]")
            self.avatar_preview_label.grid(row=0, column=5, padx=5)

            # Спрайт (нейтральный)
            sprite_row = ttk.Frame(images_frame)
            sprite_row.pack(fill=tk.X, padx=5, pady=2)
            sprite_row.grid_columnconfigure(1, weight=1)

            ttk.Label(sprite_row, text="Спрайт (нейтральный):").grid(row=0, column=0, sticky="w", padx=5)
            self.sprite_path_var = tk.StringVar()
            ttk.Entry(sprite_row, textvariable=self.sprite_path_var).grid(row=0, column=1, padx=5, sticky="ew")
            ttk.Button(sprite_row, text="+", width=3, command=self._select_sprite).grid(row=0, column=2, padx=2)
            ttk.Button(sprite_row, text="✗", width=3, command=lambda: self.sprite_path_var.set("")).grid(row=0, column=3, padx=2)
            # Привязываем событие изменения спрайта для активации кнопки вырезания
            self.sprite_path_var.trace_add("write", self._on_sprite_path_changed)

            self.sprite_preview_label = ttk.Label(sprite_row, text="[Нет]")
            self.sprite_preview_label.grid(row=0, column=4, padx=5)

            # Привязка эмоций к изображениям
            emotion_frame = ttk.LabelFrame(scrollable_frame, text="Изображения по эмоциям")
            emotion_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

            self.emotion_container = ttk.Frame(emotion_frame)
            self.emotion_container.pack(fill=tk.BOTH, expand=True)

            self.emotion_widgets = {}  # {emotion_id: {"avatar_var": ..., "sprite_var": ..., ...}}

        # Для локаций — возвращаем предпросмотр
        if self.obj_type == "locations":
            bg_frame = ttk.LabelFrame(scrollable_frame, text="Фон для визуальной новеллы")
            bg_frame.pack(fill=tk.X, padx=5, pady=5)

            bg_row = ttk.Frame(bg_frame)
            bg_row.pack(fill=tk.X, padx=5, pady=2)
            bg_row.grid_columnconfigure(1, weight=1)

            ttk.Label(bg_row, text="Фоновое изображение:").grid(row=0, column=0, sticky="w", padx=5)
            self.bg_path_var = tk.StringVar()
            ttk.Entry(bg_row, textvariable=self.bg_path_var).grid(row=0, column=1, padx=5, sticky="ew")

            ttk.Button(bg_row, text="+", width=3, command=self._select_background).grid(row=0, column=2, padx=2)
            ttk.Button(bg_row, text="✗", width=3, command=lambda: self.bg_path_var.set("")).grid(row=0, column=3, padx=2)

            self.bg_preview_label = ttk.Label(bg_row, text="[Нет]")
            self.bg_preview_label.grid(row=0, column=4, padx=5)

        # Для эмоций
        if self.obj_type == "emotions":
            emotion_images_frame = ttk.LabelFrame(scrollable_frame, text="Изображения для эмоции")
            emotion_images_frame.pack(fill=tk.X, padx=5, pady=5)

            # Аватар
            avatar_row = ttk.Frame(emotion_images_frame)
            avatar_row.pack(fill=tk.X, padx=5, pady=2)
            avatar_row.grid_columnconfigure(1, weight=1)

            ttk.Label(avatar_row, text="Аватар (квадрат):").grid(row=0, column=0, sticky="w", padx=5)
            self.em_avatar_path_var = tk.StringVar()
            ttk.Entry(avatar_row, textvariable=self.em_avatar_path_var).grid(row=0, column=1, padx=5, sticky="ew")
            ttk.Button(avatar_row, text="+", width=3, command=self._select_em_avatar).grid(row=0, column=2, padx=2)
            ttk.Button(avatar_row, text="✗", width=3, command=lambda: self.em_avatar_path_var.set("")).grid(row=0, column=3, padx=2)

            self.em_avatar_preview = ttk.Label(avatar_row, text="[Нет]")
            self.em_avatar_preview.grid(row=0, column=4, padx=5)

            # Спрайт
            sprite_row = ttk.Frame(emotion_images_frame)
            sprite_row.pack(fill=tk.X, padx=5, pady=2)
            sprite_row.grid_columnconfigure(1, weight=1)

            ttk.Label(sprite_row, text="Спрайт (полноростовой):").grid(row=0, column=0, sticky="w", padx=5)
            self.em_sprite_path_var = tk.StringVar()
            ttk.Entry(sprite_row, textvariable=self.em_sprite_path_var).grid(row=0, column=1, padx=5, sticky="ew")
            ttk.Button(sprite_row, text="+", width=3, command=self._select_em_sprite).grid(row=0, column=2, padx=2)
            ttk.Button(sprite_row, text="✗", width=3, command=lambda: self.em_sprite_path_var.set("")).grid(row=0, column=3, padx=2)

            self.em_sprite_preview = ttk.Label(sprite_row, text="[Нет]")
            self.em_sprite_preview.grid(row=0, column=4, padx=5)

        # Редактор текста
        editor_frame = ttk.LabelFrame(scrollable_frame, text="Редактор")
        editor_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        ttk.Label(editor_frame, text="Название:").pack(anchor='w', padx=5, pady=2)
        self.name_entry = ttk.Entry(editor_frame)
        self.name_entry.pack(fill=tk.X, padx=5, pady=2)
        add_context_menu(self.name_entry)

        ttk.Label(editor_frame, text="Описание:").pack(anchor='w', padx=5, pady=2)
        self.desc_text = scrolledtext.ScrolledText(editor_frame, height=10, wrap=tk.WORD)
        self.desc_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        add_context_menu(self.desc_text)

        scrollable_frame.update_idletasks()
        main_canvas.configure(scrollregion=main_canvas.bbox("all"))

        # Фиксированная кнопка "Сохранить" внизу (всегда видна)
        bottom_frame = ttk.Frame(self)
        bottom_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=8)
        self.save_btn = ttk.Button(bottom_frame, text="Сохранить", command=self._save_current)
        self.save_btn.pack(pady=2, ipadx=30)

    def _add_tooltip(self, widget, text):
        """Добавляет всплывающую подсказку для виджета."""
        def show(event):
            tooltip = tk.Toplevel(widget)
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            label = ttk.Label(tooltip, text=text, background="#ffffe0", relief="solid", borderwidth=1)
            label.pack()
            widget.tooltip = tooltip
        def hide(event):
            if hasattr(widget, 'tooltip') and widget.tooltip:
                widget.tooltip.destroy()
                widget.tooltip = None
        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)

    # --- Методы для работы с изображениями ---
    def _copy_image_to_campaign(self, source_path: str, target_subdir: str) -> str:
        """Копирует изображение в папку кампании, возвращает относительный путь.
        Всегда выполняет копирование, чтобы файл оказался именно в target_subdir."""
        if not source_path or not os.path.exists(source_path):
            return ""
        campaign_path = self.app.storage._get_campaign_path()
        target_dir = os.path.join(campaign_path, target_subdir)
        os.makedirs(target_dir, exist_ok=True)
        base_name = os.path.basename(source_path)
        target_path = os.path.join(target_dir, base_name)
        # Копируем даже если исходник уже внутри кампании (например, во временной папке)
        shutil.copy2(source_path, target_path)
        rel_path = os.path.relpath(target_path, campaign_path).replace("\\", "/")
        return rel_path
    
    def _delete_image_file(self, rel_path: str):
        """Удаляет файл изображения по относительному пути внутри папки кампании."""
        if not rel_path:
            return
        campaign_path = self.app.storage._get_campaign_path()
        full_path = os.path.join(campaign_path, rel_path)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except Exception as e:
                print(f"Не удалось удалить файл {full_path}: {e}")

    def _select_avatar(self):
        filepath = filedialog.askopenfilename(
            title="Выберите аватар (квадратное изображение)",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp")]
        )
        if filepath:
            rel_path = self._copy_image_to_campaign(filepath, "characters/avatars")
            self.avatar_path_var.set(rel_path)
            self._update_avatar_preview(rel_path)

    def _crop_avatar_from_sprite(self):
        """Открывает редактор для вырезания аватара из текущего спрайта."""
        sprite_path = self.sprite_path_var.get().strip()
        if not sprite_path:
            messagebox.showwarning("Вырезание", "Сначала выберите спрайт.")
            return
        full_sprite_path = self._get_full_path(sprite_path)
        if not os.path.exists(full_sprite_path):
            messagebox.showerror("Ошибка", "Файл спрайта не найден.")
            return
        # Открываем редактор
        def on_cropped(rel_avatar_path):
            print(f"on_cropped received: {rel_avatar_path}")
            self.avatar_path_var.set(rel_avatar_path)
            self._update_avatar_preview(rel_avatar_path)
        editor = AvatarCropEditor(self, full_sprite_path, on_cropped)
        # Передаём ссылку на текущий объект BaseEditorTab
        editor.master = self

    def _on_sprite_path_changed(self, *args):
        """Активирует кнопку вырезания, если спрайт задан."""
        if self.sprite_path_var.get().strip():
            self.crop_avatar_btn.config(state=tk.NORMAL)
        else:
            self.crop_avatar_btn.config(state=tk.DISABLED)

    def _get_full_path(self, rel_path: str) -> str:
        if not rel_path:
            return ""
        campaign_path = self.app.storage._get_campaign_path()
        full = os.path.join(campaign_path, rel_path)
        return full if os.path.exists(full) else ""

    def _update_avatar_preview(self, rel_path: str):
            if not hasattr(self, 'avatar_preview_label'):
                return
            if not rel_path:
                self.avatar_preview_label.config(image="", text="[Нет]")
                if hasattr(self.avatar_preview_label, 'image'):
                    del self.avatar_preview_label.image
                return

            campaign_path = self.app.storage._get_campaign_path()
            full_path = os.path.join(campaign_path, rel_path)
            if not os.path.exists(full_path):
                self.avatar_preview_label.config(image="", text="[Файл не найден]")
                if hasattr(self.avatar_preview_label, 'image'):
                    del self.avatar_preview_label.image
                return

            try:
                img = Image.open(full_path)
                img.thumbnail((50, 50))
                photo = ImageTk.PhotoImage(img)
                self.avatar_preview_label.config(image=photo, text="")
                self.avatar_preview_label.image = photo
            except Exception as e:
                self.avatar_preview_label.config(image="", text=f"[Ошибка: {e}]")
                if hasattr(self.avatar_preview_label, 'image'):
                    del self.avatar_preview_label.image

    def _select_sprite(self):
        filepath = filedialog.askopenfilename(
            title="Выберите полноростовой спрайт",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp")]
        )
        if filepath:
            rel_path = self._copy_image_to_campaign(filepath, "characters/sprites")
            self.sprite_path_var.set(rel_path)
            self._update_sprite_preview(rel_path)

    def _update_sprite_preview(self, rel_path: str):
        if not hasattr(self, 'sprite_preview_label'):
            return
        if not rel_path:
            self.sprite_preview_label.config(image="", text="[Нет]")
            if hasattr(self.sprite_preview_label, 'image'):
                del self.sprite_preview_label.image
            return

        campaign_path = self.app.storage._get_campaign_path()
        full_path = os.path.join(campaign_path, rel_path)
        if not os.path.exists(full_path):
            self.sprite_preview_label.config(image="", text="[Файл не найден]")
            if hasattr(self.sprite_preview_label, 'image'):
                del self.sprite_preview_label.image
            return

        try:
            img = Image.open(full_path)
            img.thumbnail((50, 100))
            photo = ImageTk.PhotoImage(img)
            self.sprite_preview_label.config(image=photo, text="")
            self.sprite_preview_label.image = photo
        except Exception as e:
            self.sprite_preview_label.config(image="", text=f"[Ошибка: {e}]")
            if hasattr(self.sprite_preview_label, 'image'):
                del self.sprite_preview_label.image

    def _select_background(self):
        filepath = filedialog.askopenfilename(
            title="Выберите фоновое изображение для локации",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp")]
        )
        if filepath:
            rel_path = self._copy_image_to_campaign(filepath, "locations/backgrounds")
            self.bg_path_var.set(rel_path)
            self._update_bg_preview(rel_path)

    def _update_bg_preview(self, rel_path: str):
        if not hasattr(self, 'bg_preview_label'):
            return
        if not rel_path:
            self.bg_preview_label.config(image="", text="[Нет]")
            if hasattr(self.bg_preview_label, 'image'):
                del self.bg_preview_label.image
            return

        campaign_path = self.app.storage._get_campaign_path()
        full_path = os.path.join(campaign_path, rel_path)
        if not os.path.exists(full_path):
            self.bg_preview_label.config(image="", text="[Файл не найден]")
            if hasattr(self.bg_preview_label, 'image'):
                del self.bg_preview_label.image
            return

        try:
            img = Image.open(full_path)
            img.thumbnail((100, 60))
            photo = ImageTk.PhotoImage(img)
            self.bg_preview_label.config(image=photo, text="")
            self.bg_preview_label.image = photo
        except Exception as e:
            self.bg_preview_label.config(image="", text=f"[Ошибка: {e}]")
            if hasattr(self.bg_preview_label, 'image'):
                del self.bg_preview_label.image

    # --- Методы для эмоций в персонаже ---
    def _rebuild_emotion_ui(self):
        """Перестраивает интерфейс привязки эмоций к персонажу с предпросмотром и кнопкой вырезания."""
        for widget in self.emotion_container.winfo_children():
            widget.destroy()
        self.emotion_widgets.clear()

        if not hasattr(self.app, 'emotions') or not self.app.emotions:
            ttk.Label(self.emotion_container, text="Нет доступных эмоций. Создайте эмоции во вкладке 'Эмоции'.").pack(pady=5)
            return

        for em_id, em in self.app.emotions.items():
            frame = ttk.LabelFrame(self.emotion_container, text=em.name)
            frame.pack(fill=tk.X, padx=5, pady=5)

            # ---- Аватар ----
            avatar_frame = ttk.Frame(frame)
            avatar_frame.pack(fill=tk.X, padx=5, pady=2)
            avatar_frame.grid_columnconfigure(1, weight=1)

            ttk.Label(avatar_frame, text="Аватар:").grid(row=0, column=0, sticky="w", padx=5)

            avatar_var = tk.StringVar()
            entry_avatar = ttk.Entry(avatar_frame, textvariable=avatar_var)
            entry_avatar.grid(row=0, column=1, padx=5, sticky="ew")

            # Кнопка выбора файла
            btn_avatar = ttk.Button(avatar_frame, text="+", width=3,
                command=lambda eid=em_id, v=avatar_var: self._select_emotion_avatar(eid, v))
            btn_avatar.grid(row=0, column=2, padx=2)

            # Кнопка вырезания из спрайта (ножницы)
            btn_crop = ttk.Button(avatar_frame, text="✂️", width=3,
                command=lambda eid=em_id: self._crop_emotion_avatar(eid))
            btn_crop.grid(row=0, column=3, padx=2)

            # Кнопка очистки
            btn_clear_avatar = ttk.Button(avatar_frame, text="✗", width=3,
                command=lambda v=avatar_var: v.set(""))
            btn_clear_avatar.grid(row=0, column=4, padx=2)

            # Метка предпросмотра аватара
            avatar_preview = ttk.Label(avatar_frame, text="[Нет]", width=10, relief="sunken")
            avatar_preview.grid(row=0, column=5, padx=5)

            # ---- Спрайт ----
            sprite_frame = ttk.Frame(frame)
            sprite_frame.pack(fill=tk.X, padx=5, pady=2)
            sprite_frame.grid_columnconfigure(1, weight=1)

            ttk.Label(sprite_frame, text="Спрайт:").grid(row=0, column=0, sticky="w", padx=5)

            sprite_var = tk.StringVar()
            entry_sprite = ttk.Entry(sprite_frame, textvariable=sprite_var)
            entry_sprite.grid(row=0, column=1, padx=5, sticky="ew")

            btn_sprite = ttk.Button(sprite_frame, text="+", width=3,
                command=lambda eid=em_id, v=sprite_var: self._select_emotion_sprite(eid, v))
            btn_sprite.grid(row=0, column=2, padx=2)

            btn_clear_sprite = ttk.Button(sprite_frame, text="✗", width=3,
                command=lambda v=sprite_var: v.set(""))
            btn_clear_sprite.grid(row=0, column=3, padx=2)

            # Метка предпросмотра спрайта
            sprite_preview = ttk.Label(sprite_frame, text="[Нет]", width=10, relief="sunken")
            sprite_preview.grid(row=0, column=4, padx=5)

            # Сохраняем все виджеты
            self.emotion_widgets[em_id] = {
                "avatar_var": avatar_var,
                "sprite_var": sprite_var,
                "avatar_preview": avatar_preview,
                "sprite_preview": sprite_preview,
                "frame": frame
            }

            # Привязываем обновление предпросмотра при изменении переменных
            avatar_var.trace_add("write", lambda *args, eid=em_id, var=avatar_var: self._update_emotion_avatar_preview(eid, var.get()))
            sprite_var.trace_add("write", lambda *args, eid=em_id, var=sprite_var: self._update_emotion_sprite_preview(eid, var.get()))

    def _crop_emotion_avatar(self, emotion_id: str):
        """Открывает редактор для вырезания аватара эмоции из её спрайта."""
        # Получаем путь к спрайту этой эмоции
        if emotion_id not in self.emotion_widgets:
            messagebox.showerror("Ошибка", "Эмоция не найдена.")
            return
        sprite_path = self.emotion_widgets[emotion_id]["sprite_var"].get().strip()
        if not sprite_path:
            messagebox.showwarning("Вырезание", "Сначала выберите спрайт для этой эмоции.")
            return

        full_sprite_path = self._get_full_path(sprite_path)
        if not os.path.exists(full_sprite_path):
            messagebox.showerror("Ошибка", "Файл спрайта не найден.")
            return

        # Callback после вырезания
        def on_cropped(rel_avatar_path):
            # Устанавливаем полученный аватар в переменную эмоции
            self.emotion_widgets[emotion_id]["avatar_var"].set(rel_avatar_path)
            # Принудительно обновляем предпросмотр
            self._update_emotion_avatar_preview(emotion_id, rel_avatar_path)

        # Открываем редактор
        editor = AvatarCropEditor(self, full_sprite_path, on_cropped)
        editor.master = self  # для доступа к методам копирования

    def _copy_image_to_campaign(self, source_path: str, target_subdir: str) -> str:
        """Копирует изображение в папку кампании, возвращает относительный путь.
        Всегда выполняет копирование, чтобы файл оказался именно в target_subdir."""
        if not source_path or not os.path.exists(source_path):
            return ""
        campaign_path = self.app.storage._get_campaign_path()
        target_dir = os.path.join(campaign_path, target_subdir)
        os.makedirs(target_dir, exist_ok=True)
        base_name = os.path.basename(source_path)
        target_path = os.path.join(target_dir, base_name)
        # Копируем даже если исходник уже внутри кампании (например, во временной папке)
        shutil.copy2(source_path, target_path)
        rel_path = os.path.relpath(target_path, campaign_path).replace("\\", "/")
        return rel_path

    def _select_emotion_avatar(self, emotion_id, var):
        filepath = filedialog.askopenfilename(
            title=f"Выберите аватар для эмоции",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp")]
        )
        if filepath:
            rel_path = self._copy_image_to_campaign(filepath, f"characters/emotions/{emotion_id}")
            var.set(rel_path)

    def _update_emotion_avatar_preview(self, emotion_id: str, rel_path: str):
        """Обновляет миниатюру аватара для указанной эмоции."""
        if emotion_id not in self.emotion_widgets:
            return
        preview_label = self.emotion_widgets[emotion_id]["avatar_preview"]
        if not rel_path:
            preview_label.config(image="", text="[Нет]")
            if hasattr(preview_label, 'image'):
                del preview_label.image
            return

        campaign_path = self.app.storage._get_campaign_path()
        full_path = os.path.join(campaign_path, rel_path)
        if not os.path.exists(full_path):
            preview_label.config(image="", text="[Файл не найден]")
            if hasattr(preview_label, 'image'):
                del preview_label.image
            return

        try:
            img = Image.open(full_path)
            img.thumbnail((50, 50))
            photo = ImageTk.PhotoImage(img)
            preview_label.config(image=photo, text="")
            preview_label.image = photo
        except Exception as e:
            preview_label.config(image="", text=f"[Ошибка: {e}]")
            if hasattr(preview_label, 'image'):
                del preview_label.image

    def _update_emotion_avatar_preview(self, emotion_id: str, rel_path: str):
        """Обновляет миниатюру аватара для указанной эмоции."""
        if emotion_id not in self.emotion_widgets:
            return
        preview_label = self.emotion_widgets[emotion_id]["avatar_preview"]
        if not rel_path:
            preview_label.config(image="", text="[Нет]")
            if hasattr(preview_label, 'image'):
                del preview_label.image
            return

        campaign_path = self.app.storage._get_campaign_path()
        full_path = os.path.join(campaign_path, rel_path)
        if not os.path.exists(full_path):
            preview_label.config(image="", text="[Файл не найден]")
            if hasattr(preview_label, 'image'):
                del preview_label.image
            return

        try:
            img = Image.open(full_path)
            img.thumbnail((50, 50))
            photo = ImageTk.PhotoImage(img)
            preview_label.config(image=photo, text="")
            preview_label.image = photo
        except Exception as e:
            preview_label.config(image="", text=f"[Ошибка: {e}]")
            if hasattr(preview_label, 'image'):
                del preview_label.image

    def _update_emotion_sprite_preview(self, emotion_id: str, rel_path: str):
        """Обновляет миниатюру спрайта для указанной эмоции."""
        if emotion_id not in self.emotion_widgets:
            return
        preview_label = self.emotion_widgets[emotion_id]["sprite_preview"]
        if not rel_path:
            preview_label.config(image="", text="[Нет]")
            if hasattr(preview_label, 'image'):
                del preview_label.image
            return

        campaign_path = self.app.storage._get_campaign_path()
        full_path = os.path.join(campaign_path, rel_path)
        if not os.path.exists(full_path):
            preview_label.config(image="", text="[Файл не найден]")
            if hasattr(preview_label, 'image'):
                del preview_label.image
            return

        try:
            img = Image.open(full_path)
            # Для спрайта можно использовать другой размер, например 50x100
            img.thumbnail((50, 100))
            photo = ImageTk.PhotoImage(img)
            preview_label.config(image=photo, text="")
            preview_label.image = photo
        except Exception as e:
            preview_label.config(image="", text=f"[Ошибка: {e}]")
            if hasattr(preview_label, 'image'):
                del preview_label.image

    def _select_emotion_sprite(self, emotion_id, var):
        filepath = filedialog.askopenfilename(
            title=f"Выберите спрайт для эмоции",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp")]
        )
        if filepath:
            rel_path = self._copy_image_to_campaign(filepath, f"characters/emotions/{emotion_id}")
            var.set(rel_path)

    # --- Методы для эмоций (объектов эмоций) ---
    def _select_em_avatar(self):
        filepath = filedialog.askopenfilename(
            title="Выберите аватар для эмоции",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp")]
        )
        if filepath:
            rel_path = self._copy_image_to_campaign(filepath, "emotions/avatars")
            self.em_avatar_path_var.set(rel_path)
            self._update_em_avatar_preview(rel_path)

    def _update_em_avatar_preview(self, rel_path):
        if not hasattr(self, 'em_avatar_preview'):
            return
        if not rel_path:
            self.em_avatar_preview.config(image="", text="[Нет]")
            if hasattr(self.em_avatar_preview, 'image'):
                del self.em_avatar_preview.image
            return
        campaign_path = self.app.storage._get_campaign_path()
        full_path = os.path.join(campaign_path, rel_path)
        if not os.path.exists(full_path):
            self.em_avatar_preview.config(image="", text="[Файл не найден]")
            return
        try:
            img = Image.open(full_path)
            img.thumbnail((50, 50))
            photo = ImageTk.PhotoImage(img)
            self.em_avatar_preview.config(image=photo, text="")
            self.em_avatar_preview.image = photo
        except Exception as e:
            self.em_avatar_preview.config(image="", text=f"[Ошибка: {e}]")

    def _select_em_sprite(self):
        filepath = filedialog.askopenfilename(
            title="Выберите спрайт для эмоции",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp")]
        )
        if filepath:
            rel_path = self._copy_image_to_campaign(filepath, "emotions/sprites")
            self.em_sprite_path_var.set(rel_path)
            self._update_em_sprite_preview(rel_path)

    def _update_em_sprite_preview(self, rel_path):
        if not hasattr(self, 'em_sprite_preview'):
            return
        if not rel_path:
            self.em_sprite_preview.config(image="", text="[Нет]")
            if hasattr(self.em_sprite_preview, 'image'):
                del self.em_sprite_preview.image
            return
        campaign_path = self.app.storage._get_campaign_path()
        full_path = os.path.join(campaign_path, rel_path)
        if not os.path.exists(full_path):
            self.em_sprite_preview.config(image="", text="[Файл не найден]")
            return
        try:
            img = Image.open(full_path)
            img.thumbnail((50, 100))
            photo = ImageTk.PhotoImage(img)
            self.em_sprite_preview.config(image=photo, text="")
            self.em_sprite_preview.image = photo
        except Exception as e:
            self.em_sprite_preview.config(image="", text=f"[Ошибка: {e}]")

    # --- Остальные методы ---
    def _get_objects_dict(self):
        if self.obj_type == "narrators":
            return self.app.narrators
        elif self.obj_type == "characters":
            return self.app.characters
        elif self.obj_type == "locations":
            return self.app.locations
        elif self.obj_type == "items":
            return self.app.items
        elif self.obj_type == "events":
            return self.app.events
        elif self.obj_type == "scenarios":
            return self.app.scenarios
        elif self.obj_type == "emotions":
            return self.app.emotions
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
                avatar = getattr(obj, 'avatar_image', '')
                sprite = getattr(obj, 'sprite_image', '')
                self.avatar_path_var.set(avatar)
                self.sprite_path_var.set(sprite)
                self._update_avatar_preview(avatar)
                self._update_sprite_preview(sprite)

                # Загрузка привязок эмоций
                emotion_images = getattr(obj, 'emotion_images', {})
                # Перестраиваем UI эмоций
                self._rebuild_emotion_ui()
                for em_id, paths in emotion_images.items():
                    if em_id in self.emotion_widgets:
                        av_path = paths.get("avatar", "")
                        sp_path = paths.get("sprite", "")
                        self.emotion_widgets[em_id]["avatar_var"].set(av_path)
                        self.emotion_widgets[em_id]["sprite_var"].set(sp_path)
                        # Принудительно обновляем предпросмотр (на случай, если trace не сработал)
                        self._update_emotion_avatar_preview(em_id, av_path)
                        self._update_emotion_sprite_preview(em_id, sp_path)

            if self.obj_type == "locations":
                bg = getattr(obj, 'background_image', '')
                self.bg_path_var.set(bg)
                self._update_bg_preview(bg)

            if self.obj_type == "emotions":
                avatar = getattr(obj, 'avatar_image', '')
                sprite = getattr(obj, 'sprite_image', '')
                self.em_avatar_path_var.set(avatar)
                self.em_sprite_path_var.set(sprite)
                self._update_em_avatar_preview(avatar)
                self._update_em_sprite_preview(sprite)
        else:
            local_desc = self.app.local_descriptions.get(self.current_obj_id, "")
            self.desc_text.insert(1.0, local_desc)

            if self.obj_type == "characters":
                self.player_var.set(obj.is_player)
                self.player_check.config(state=tk.DISABLED)
                avatar = getattr(obj, 'avatar_image', '')
                sprite = getattr(obj, 'sprite_image', '')
                self.avatar_path_var.set(avatar)
                self.sprite_path_var.set(sprite)
                self._update_avatar_preview(avatar)
                self._update_sprite_preview(sprite)

            if self.obj_type == "locations":
                bg = getattr(obj, 'background_image', '')
                self.bg_path_var.set(bg)
                self._update_bg_preview(bg)

        local_exists = self.current_obj_id in self.app.local_descriptions
        self.reset_local_btn.config(state=tk.NORMAL if local_exists else tk.DISABLED)

    def _clear_form(self):
        self.current_obj_id = None
        self.name_entry.delete(0, tk.END)
        self.desc_text.delete(1.0, tk.END)

        if self.obj_type == "characters":
            self.player_var.set(False)
            if hasattr(self, 'player_check'):
                self.player_check.config(state=tk.NORMAL)
            if hasattr(self, 'avatar_path_var'):
                self.avatar_path_var.set("")
            if hasattr(self, 'sprite_path_var'):
                self.sprite_path_var.set("")
            if hasattr(self, 'avatar_preview_label'):
                self.avatar_preview_label.config(image="", text="[Нет]")
                if hasattr(self.avatar_preview_label, 'image'):
                    del self.avatar_preview_label.image
            if hasattr(self, 'sprite_preview_label'):
                self.sprite_preview_label.config(image="", text="[Нет]")
                if hasattr(self.sprite_preview_label, 'image'):
                    del self.sprite_preview_label.image
            # Очистка эмоций
            for em_id, widgets in self.emotion_widgets.items():
                widgets["avatar_var"].set("")
                widgets["sprite_var"].set("")

        if self.obj_type == "locations":
            if hasattr(self, 'bg_path_var'):
                self.bg_path_var.set("")
            if hasattr(self, 'bg_preview_label'):
                self.bg_preview_label.config(image="", text="[Нет]")
                if hasattr(self.bg_preview_label, 'image'):
                    del self.bg_preview_label.image

        if self.obj_type == "emotions":
            if hasattr(self, 'em_avatar_path_var'):
                self.em_avatar_path_var.set("")
            if hasattr(self, 'em_sprite_path_var'):
                self.em_sprite_path_var.set("")
            if hasattr(self, 'em_avatar_preview'):
                self.em_avatar_preview.config(image="", text="[Нет]")
            if hasattr(self, 'em_sprite_preview'):
                self.em_sprite_preview.config(image="", text="[Нет]")

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
        elif self.obj_type == "events":
            self.app.update("create_event", data)
        elif self.obj_type == "scenarios":
            self.app.update("create_scenario", data)
        elif self.obj_type == "emotions":
            self.app.update("create_emotion", data)

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
            elif self.obj_type == "events":
                self.app.update("delete_event", {"id": self.current_obj_id})
            elif self.obj_type == "scenarios":
                self.app.update("delete_scenario", {"id": self.current_obj_id})
            elif self.obj_type == "emotions":
                self.app.update("delete_emotion", {"id": self.current_obj_id})

    def _save_current(self):
        name = self.name_entry.get().strip()
        desc = self.desc_text.get(1.0, tk.END).strip()
        if not name:
            messagebox.showwarning("Ошибка", "Введите название")
            return
        if self.editing_mode.get() == "global":
            if not self.current_obj_id:
                # Создание нового объекта
                data = {"name": name, "description": desc}
                if self.obj_type == "characters":
                    data["is_player"] = self.player_var.get()
                    data["avatar_image"] = self.avatar_path_var.get().strip()
                    data["sprite_image"] = self.sprite_path_var.get().strip()
                    # Собираем emotion_images
                    emotion_images = {}
                    for em_id, widgets in self.emotion_widgets.items():
                        av = widgets["avatar_var"].get().strip()
                        sp = widgets["sprite_var"].get().strip()
                        if av or sp:
                            emotion_images[em_id] = {"avatar": av, "sprite": sp}
                    data["emotion_images"] = emotion_images
                if self.obj_type == "locations":
                    data["background_image"] = self.bg_path_var.get().strip()
                if self.obj_type == "emotions":
                    data["avatar_image"] = self.em_avatar_path_var.get().strip()
                    data["sprite_image"] = self.em_sprite_path_var.get().strip()
                if self.obj_type == "narrators":
                    self.app.update("update_narrator", data)
                elif self.obj_type == "characters":
                    self.app.update("create_character", data)
                elif self.obj_type == "locations":
                    self.app.update("create_location", data)
                elif self.obj_type == "items":
                    self.app.update("create_item", data)
                elif self.obj_type == "events":
                    self.app.update("create_event", data)
                elif self.obj_type == "scenarios":
                    self.app.update("create_scenario", data)
                elif self.obj_type == "emotions":
                    self.app.update("create_emotion", data)
            else:
                # Обновление существующего объекта – удаляем старые файлы, если пути изменились
                obj = self._get_objects_dict().get(self.current_obj_id)
                if obj:
                    if self.obj_type == "characters":
                        old_avatar = getattr(obj, 'avatar_image', '')
                        new_avatar = self.avatar_path_var.get().strip()
                        if old_avatar and old_avatar != new_avatar:
                            self._delete_image_file(old_avatar)
                        old_sprite = getattr(obj, 'sprite_image', '')
                        new_sprite = self.sprite_path_var.get().strip()
                        if old_sprite and old_sprite != new_sprite:
                            self._delete_image_file(old_sprite)
                    if self.obj_type == "locations":
                        old_bg = getattr(obj, 'background_image', '')
                        new_bg = self.bg_path_var.get().strip()
                        if old_bg and old_bg != new_bg:
                            self._delete_image_file(old_bg)
                    if self.obj_type == "emotions":
                        old_avatar = getattr(obj, 'avatar_image', '')
                        new_avatar = self.em_avatar_path_var.get().strip()
                        if old_avatar and old_avatar != new_avatar:
                            self._delete_image_file(old_avatar)
                        old_sprite = getattr(obj, 'sprite_image', '')
                        new_sprite = self.em_sprite_path_var.get().strip()
                        if old_sprite and old_sprite != new_sprite:
                            self._delete_image_file(old_sprite)
                data = {"id": self.current_obj_id, "name": name, "description": desc}
                if self.obj_type == "characters":
                    data["is_player"] = self.player_var.get()
                    data["avatar_image"] = self.avatar_path_var.get().strip()
                    data["sprite_image"] = self.sprite_path_var.get().strip()
                    emotion_images = {}
                    for em_id, widgets in self.emotion_widgets.items():
                        av = widgets["avatar_var"].get().strip()
                        sp = widgets["sprite_var"].get().strip()
                        if av or sp:
                            emotion_images[em_id] = {"avatar": av, "sprite": sp}
                    data["emotion_images"] = emotion_images
                if self.obj_type == "locations":
                    data["background_image"] = self.bg_path_var.get().strip()
                if self.obj_type == "emotions":
                    data["avatar_image"] = self.em_avatar_path_var.get().strip()
                    data["sprite_image"] = self.em_sprite_path_var.get().strip()
                if self.obj_type == "narrators":
                    self.app.update("update_narrator", data)
                elif self.obj_type == "characters":
                    self.app.update("update_character", data)
                elif self.obj_type == "locations":
                    self.app.update("update_location", data)
                elif self.obj_type == "items":
                    self.app.update("update_item", data)
                elif self.obj_type == "events":
                    self.app.update("update_event", data)
                elif self.obj_type == "scenarios":
                    self.app.update("update_scenario", data)
                elif self.obj_type == "emotions":
                    self.app.update("update_emotion", data)
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
                    "is_player": self.player_var.get(),
                    "avatar_image": getattr(obj, 'avatar_image', ''),
                    "sprite_image": getattr(obj, 'sprite_image', ''),
                    "emotion_images": getattr(obj, 'emotion_images', {})
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
        name = simpledialog.askstring("Новый промт", "Введите имя нового промта (без префикса 'translator_'):", parent=self)
        if name:
            if name.startswith("translator_"):
                messagebox.showwarning("Недопустимое имя", "Имя не должно начинаться с 'translator_'.")
                return
            self.app.update("create_prompt", {"name": name})

    def _delete_selected(self):
        if not self.current_prompt_name:
            return
        if self.current_prompt_name in self.app.prompt_manager.REQUIRED_PROMPTS:
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
        name = simpledialog.askstring("Новый промт переводчика", "Введите имя нового промта (без префикса 'translator_'):", parent=self)
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

# ---------- Вкладка "Этапы" ----------
class StagePromptsTab(ttk.Frame):
    STAGE_MAPPING = [
        ("1.1 Запрос описаний объектов", "stage1_request_descriptions"),
        ("1.2 Создание сцены", "stage1_create_scene"),
        ("2. Проверка правдивости", "stage1_truth_check"),
        ("3. Действие игрока (d20)", "stage1_player_action"),
        ("4. Определение случайного события (d100)", "stage1_random_event_determine"),
        ("5.1 Запрос объектов для события", "stage1_random_event_request_objects"),
        ("5.2 Описание события (d20)", "stage1_random_event_details"),
        ("6. Обработка NPC", "stage2_npc_action"),
        ("7. Финальный рассказ", "stage3_final"),
        ("8.1 Проверка истории", "stage8_history_check"),
        ("8.2 Валидация результата", "stage11_validation"),
        ("12. Определение эмоций персонажей", "stage12_emotions"),
        ("11. Проверка значительных изменений", "stage11_significant_changes"),
        ("9. Краткая память", "stage4_summary"),
        ("10. Ассоциативная память", "stage10_associative_memory"),
    ]

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.current_stage = None
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
        for display_name, _ in self.STAGE_MAPPING:
            self.stage_listbox.insert(tk.END, display_name)
        self.stage_listbox.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        stage_scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.stage_listbox.yview)
        stage_scrollbar.grid(row=0, column=1, sticky="ns", pady=5)
        self.stage_listbox.configure(yscrollcommand=stage_scrollbar.set)
        self.stage_listbox.bind("<<ListboxSelect>>", self._on_stage_select)

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
        center_window(dialog, self.app)

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

        narrators = self.app.narrators
        if not narrators:
            messagebox.showinfo("Нет рассказчиков", "В базе нет ни одного рассказчика.")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Выберите рассказчиков")
        dialog.geometry("500x400")
        dialog.transient(self)
        center_window(dialog, self.app)

        frame = ttk.Frame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(frame, text="Доступные рассказчики (можно выбрать несколько):").pack(anchor='w')
        listbox = tk.Listbox(frame, selectmode=tk.MULTIPLE, height=15)
        listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        scrollbar = ttk.Scrollbar(listbox, orient=tk.VERTICAL, command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        sorted_narrators = sorted(narrators.values(), key=lambda n: n.name)
        for narr in sorted_narrators:
            listbox.insert(tk.END, f"{narr.name} (id:{narr.id})")

        def add_selected():
            selected_indices = listbox.curselection()
            if not selected_indices:
                messagebox.showwarning("Выбор", "Не выбран ни один рассказчик.")
                return
            current = self.app.stage_prompts_config.get(self.current_stage, [])
            sel_prompt = self.prompts_listbox.curselection()
            insert_idx = sel_prompt[0] if sel_prompt else len(current)

            added = 0
            for idx in selected_indices:
                item = listbox.get(idx)
                match = re.search(r'\(id:([^)]+)\)', item)
                if match:
                    narr_id = match.group(1)
                    entry = f"narrator:{narr_id}"
                    if entry not in current:
                        current.insert(insert_idx + added, entry)
                        added += 1
            if added:
                self.app.stage_prompts_config[self.current_stage] = current
                self._refresh_prompts_list()
                self.app.save_stage_prompts_config()
                messagebox.showinfo("Добавление", f"Добавлено {added} рассказчиков.")
            else:
                messagebox.showinfo("Добавление", "Выбранные рассказчики уже присутствуют в этапе.")
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Добавить выбранных", command=add_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

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
        current = self.app.stage_prompts_config.get(self.current_stage, [])
        if "history:auto" in current:
            messagebox.showinfo("История", "История уже добавлена для этого этапа.")
            return
        sel = self.prompts_listbox.curselection()
        insert_idx = sel[0] if sel else len(current)
        current.insert(insert_idx, "history:auto")
        self.app.stage_prompts_config[self.current_stage] = current
        self._refresh_prompts_list()
        if sel:
            self.prompts_listbox.selection_set(insert_idx)
        self.app.save_stage_prompts_config()
        messagebox.showinfo("История", "Метка истории добавлена. Количество сообщений, кратких резюме и записей ассоциативной памяти будут взяты из глобальных настроек.")

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
            elif entry == "history:auto":
                display = "📜 История (из глобальных настроек)"
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

# ---------- Вкладка "История" ----------
class HistoryTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.tree = None
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("num", "user_msg", "assistant_msg", "importance"),
            show="headings"
        )
        self.tree.heading("num", text="№")
        self.tree.heading("user_msg", text="Сообщение пользователя")
        self.tree.heading("assistant_msg", text="Ответ ассистента")
        self.tree.heading("importance", text="Важность")

        self.tree.column("num", width=50, anchor="center")
        self.tree.column("user_msg", width=300)
        self.tree.column("assistant_msg", width=300)
        self.tree.column("importance", width=100, anchor="center")

        v_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=v_scroll.set)
        h_scroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(xscrollcommand=h_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        def _on_mousewheel(event):
            self.tree.yview_scroll(int(-1*(event.delta/120)), "units")
        self.tree.bind("<MouseWheel>", _on_mousewheel)
        self.tree.bind("<Button-4>", lambda e: self.tree.yview_scroll(-1, "units"))
        self.tree.bind("<Button-5>", lambda e: self.tree.yview_scroll(1, "units"))

        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<ButtonRelease-1>", self._on_click_importance)

        info_frame = ttk.LabelFrame(self, text="Справка")
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(info_frame, text="• Двойной клик по строке → просмотр полной пары.\n"
                                   "• Клик по ячейке «Важность» переключает флаг (True/False).\n"
                                   "• Изменения сохраняются автоматически и влияют на фильтрацию истории в стадии 8.1.",
                 justify=tk.LEFT).pack(padx=5, pady=5)

    def _get_pairs_and_flags(self):
        """Возвращает список пар (user, assistant) и список флагов значительных изменений."""
        history = self.app.conversation_history
        pairs = []
        i = 0
        while i < len(history) - 1:
            if history[i]['role'] == 'user' and history[i+1]['role'] == 'assistant':
                pairs.append((history[i]['content'], history[i+1]['content']))
                i += 2
            else:
                i += 1

        flags = self.app.significant_changes_flags[:]
        if len(flags) > len(pairs):
            flags = flags[:len(pairs)]
        elif len(flags) < len(pairs):
            flags += [False] * (len(pairs) - len(flags))

        if len(self.app.significant_changes_flags) != len(flags):
            self.app.significant_changes_flags = flags
            self.app._save_current_session_safe()

        return pairs, flags

    def refresh(self):
        if not self.tree:
            return
        for row in self.tree.get_children():
            self.tree.delete(row)
        pairs, flags = self._get_pairs_and_flags()
        for idx, ((user_msg, asst_msg), flag) in enumerate(zip(pairs, flags), start=1):
            user_short = user_msg[:80] + "..." if len(user_msg) > 80 else user_msg
            asst_short = asst_msg[:80] + "..." if len(asst_msg) > 80 else asst_msg
            flag_str = "True" if flag else "False"
            self.tree.insert("", tk.END, iid=str(idx), values=(idx, user_short, asst_short, flag_str))

    def _on_click_importance(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        column = self.tree.identify_column(event.x)
        if column != "#4":
            return
        item = self.tree.identify_row(event.y)
        if not item:
            return
        # Получаем индекс из iid (сохраняем как строку)
        idx = int(item) - 1
        pairs, flags = self._get_pairs_and_flags()
        if idx < 0 or idx >= len(flags):
            return
        new_flag = not flags[idx]
        if idx < len(self.app.significant_changes_flags):
            self.app.significant_changes_flags[idx] = new_flag
        else:
            while len(self.app.significant_changes_flags) <= idx:
                self.app.significant_changes_flags.append(False)
            self.app.significant_changes_flags[idx] = new_flag
        self.app._save_current_session_safe()
        self.refresh()
        self.app.center_panel.display_system_message(f"Важность пары #{idx+1} изменена на {new_flag}.\n")

    def _on_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        idx = int(item) - 1
        pairs, flags = self._get_pairs_and_flags()
        if idx < 0 or idx >= len(pairs):
            return
        user_msg, asst_msg = pairs[idx]
        flag = flags[idx]

        win = tk.Toplevel(self)
        win.title(f"Редактирование пары #{idx+1}")
        win.geometry("700x500")
        win.transient(self)
        win.grab_set()
        center_window(win, self.app)

        ttk.Label(win, text="Сообщение пользователя:", font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', padx=10, pady=(10,0))
        user_text = scrolledtext.ScrolledText(win, wrap=tk.WORD, height=8)
        user_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        user_text.insert(tk.END, user_msg)
        user_text.config(state=tk.DISABLED)

        ttk.Label(win, text="Ответ ассистента:", font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', padx=10)
        asst_text = scrolledtext.ScrolledText(win, wrap=tk.WORD, height=8)
        asst_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        asst_text.insert(tk.END, asst_msg)
        asst_text.config(state=tk.DISABLED)

        flag_var = tk.BooleanVar(value=flag)
        flag_cb = ttk.Checkbutton(win, text="Важная пара (значительные изменения)", variable=flag_var)
        flag_cb.pack(anchor='w', padx=10, pady=5)

        def save_flag():
            new_flag = flag_var.get()
            if idx < len(self.app.significant_changes_flags):
                self.app.significant_changes_flags[idx] = new_flag
            else:
                while len(self.app.significant_changes_flags) <= idx:
                    self.app.significant_changes_flags.append(False)
                self.app.significant_changes_flags[idx] = new_flag
            self.app._save_current_session_safe()
            self.refresh()
            win.destroy()
            self.app.center_panel.display_system_message(f"Важность пары #{idx+1} изменена на {new_flag}.\n")

        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="Сохранить", command=save_flag).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Отмена", command=win.destroy).pack(side=tk.LEFT, padx=10)