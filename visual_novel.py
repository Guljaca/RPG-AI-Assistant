# visual_novel.py
import tkinter as tk
from tkinter import ttk, scrolledtext
from PIL import Image, ImageTk
import os
import queue
from typing import List, Dict

class VisualNovelFrame(ttk.Frame):
    """
    Фрейм режима визуальной новеллы.
    Спрайты стоят на "полу", аватарки и вывод сообщений работают.
    Поддерживает эмоции персонажей: для каждого персонажа определяется эмоция,
    и если у персонажа есть соответствующее изображение (avatar_image или sprite_image)
    для данной эмоции (из словаря emotion_images), то используется оно,
    иначе – нейтральное изображение персонажа (avatar_image, sprite_image).
    Если нейтрального нет – ничего не отображается.
    """
    
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.debug_mode = False
        self._freeze = False                     # заморозка обновлений во время генерации
        self._monitor_after_id = None            # идентификатор after для мониторинга
        
        self._sprite_photos = []
        self._avatar_photos = []
        self._last_left_count = 0
        self._last_right_count = 0
        
        self.update_queue = queue.Queue()
        self._process_queue()
        
        self._build_ui()
        self._bind_to_app()
        self.after(100, self.refresh_from_current_state)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        
        # Запускаем мониторинг состояния генерации (раз в 200 мс)
        self._start_monitor()

    def _start_monitor(self):
        """Запускает периодическую проверку флага is_generating для разморозки."""
        if self._monitor_after_id:
            self.after_cancel(self._monitor_after_id)
        self._monitor_after_id = self.after(200, self._monitor_generation)

    def _monitor_generation(self):
        """Если генерация завершилась, а мы заморожены – размораживаем и обновляем."""
        if self._freeze and not self.app.is_generating:
            self.set_freeze(False)   # разморозка вызовет refresh
        # Запускаем следующий цикл
        self._monitor_after_id = self.after(200, self._monitor_generation)

    def set_freeze(self, freeze: bool):
        """Устанавливает режим заморозки обновлений."""
        if self._freeze == freeze:
            return
        self._freeze = freeze
        if not freeze:
            # Разморозка – принудительно обновляем отображение по текущим данным
            self.refresh_from_current_state()
    
    def _build_ui(self):
        # Холст для фона и спрайтов
        self.canvas = tk.Canvas(self, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Нижняя панель (диалог + ввод)
        self.bottom_frame = tk.Frame(self, bg="black")

        # Диалоговое окно
        self.dialog_text = scrolledtext.ScrolledText(
            self.bottom_frame, wrap=tk.WORD, font=("Arial", 12),
            height=6, bg="#1e1e1e", fg="#e0e0e0", relief=tk.FLAT, borderwidth=0
        )
        self.dialog_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))
        self.dialog_text.config(state=tk.DISABLED)

        # Поле ввода
        input_frame = tk.Frame(self.bottom_frame, bg="black")
        input_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.user_input = tk.Text(input_frame, height=3, font=("Arial", 11),
                                  bg="#2c2c2c", fg="white", relief=tk.FLAT)
        self.user_input.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        self.send_btn = ttk.Button(input_frame, text="Отправить", command=self._send_message)
        self.send_btn.pack(side=tk.RIGHT)

        # Кнопки управления
        btn_frame = tk.Frame(self.bottom_frame, bg="black")
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self.back_btn = ttk.Button(btn_frame, text="Обычный режим", command=self._switch_to_normal)
        self.back_btn.pack(side=tk.RIGHT, padx=2)
        
        self.debug_btn = ttk.Button(btn_frame, text="Отладка", command=self._toggle_debug)
        self.debug_btn.pack(side=tk.RIGHT, padx=2)
        
        self.regenerate_btn = ttk.Button(btn_frame, text="Перегенерировать", command=self._regenerate_last)
        self.regenerate_btn.pack(side=tk.RIGHT, padx=2)
        
        # НОВАЯ КНОПКА СТОП
        self.stop_btn = ttk.Button(btn_frame, text="Стоп", command=self._stop_generation, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.RIGHT, padx=2)

        # Размещаем нижнюю панель точно внизу
        self.bottom_frame.place(relx=0, rely=1.0, anchor="sw", relwidth=1.0)

        # Привязки ввода
        self.user_input.bind("<Control-Return>", lambda e: self._send_message())
        self.user_input.bind("<Return>", lambda e: self._send_message() if not e.state & 0x1 else None)

    def _send_message(self):
        if self.app.is_generating:
            self.append_dialog("⚠️ Модель уже генерирует ответ. Дождитесь или нажмите «Стоп».\n")
            return
        message = self.user_input.get("1.0", tk.END).strip()
        if not message:
            return
        self.user_input.delete("1.0", tk.END)
        self.append_dialog(f"Вы: {message}\n")
        self.app.center_panel.display_message(f"Вы: {message}\n", "user")
        self.app.update("send_message", {"message": message})

    def _regenerate_last(self):
        """Вызывает перегенерацию последнего ответа ассистента."""
        if self.app.is_generating:
            self.append_dialog("⚠️ Модель уже генерирует ответ.\n")
            return
        if not self.app.last_user_message:
            self.append_dialog("ℹ️ Нет последнего сообщения пользователя для перегенерации.\n")
            return
        self.append_dialog("🔄 Перегенерация последнего ответа...\n")
        self.app.update("regenerate_last_response")

    def _stop_generation(self):
        """Останавливает текущую генерацию."""
        if self.app.is_generating:
            self.app.update("stop_generation")
            self.append_dialog("⏹️ Остановка генерации...\n")
            self._set_buttons_state(generating=False)
        else:
            self.append_dialog("ℹ️ Генерация не выполняется.\n")

    def _set_buttons_state(self, generating: bool):
        """Обновляет состояние кнопок в зависимости от того, идёт ли генерация."""
        if generating:
            self.send_btn.config(state=tk.DISABLED)
            self.regenerate_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
        else:
            self.send_btn.config(state=tk.NORMAL)
            self.regenerate_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)

    def _switch_to_normal(self):
        self.app._toggle_display_mode()

    def _toggle_debug(self):
        self.debug_mode = not self.debug_mode
        if self.debug_mode:
            self.debug_btn.config(text="Отладка (вкл)")
        else:
            self.debug_btn.config(text="Отладка")
        self.refresh_from_current_state()

    def on_canvas_configure(self, event=None):
        self.after(10, self.refresh_from_current_state)

    # ====================== Очередь обновлений ======================
    def _process_queue(self):
        try:
            while True:
                func, args, kwargs = self.update_queue.get_nowait()
                func(*args, **kwargs)
        except queue.Empty:
            pass
        self.after(50, self._process_queue)

    def append_dialog(self, text: str):
        self.update_queue.put((self._append_dialog_impl, (text,), {}))

    def _append_dialog_impl(self, text: str):
        self.dialog_text.config(state=tk.NORMAL)
        self.dialog_text.insert(tk.END, text)
        self.dialog_text.see(tk.END)
        self.dialog_text.config(state=tk.DISABLED)

    def clear_dialog(self):
        self.update_queue.put((self._clear_dialog_impl, (), {}))

    def _clear_dialog_impl(self):
        self.dialog_text.config(state=tk.NORMAL)
        self.dialog_text.delete(1.0, tk.END)
        self.dialog_text.config(state=tk.DISABLED)

    def refresh_from_current_state(self):
        self.update_queue.put((self._refresh_impl, (), {}))

    def _refresh_impl(self):
        if self._freeze:
            return   # во время генерации не обновляем картинки
        sp = self.app.stage_processor
        if sp is None:
            return
        scene_data = sp.stage_data if sp else {}
            
        # Фон
        location_id = scene_data.get("scene_location_id")
        if location_id:
            location = self.app.locations.get(location_id)
            if location and hasattr(location, 'background_image') and location.background_image:
                bg_path = self._get_full_path(location.background_image)
                self._set_background(bg_path)
            else:
                self._set_background(None)
        else:
            self._set_background(None)

        # Спрайты (до 3 штук) с учётом эмоций
        character_ids = scene_data.get("scene_character_ids", [])
        emotion_map = scene_data.get("emotion_map", {})
        sprite_characters = []  # (cid, char, emotion_name)
        for cid in character_ids[:3]:
            char = self.app.characters.get(cid)
            if char:
                emotion = emotion_map.get(cid)
                sprite_image_path = self._get_sprite_for_character(char, emotion)
                if sprite_image_path:
                    sprite_characters.append((cid, char, emotion, sprite_image_path))
        self._set_sprites(sprite_characters)

        # Аватарки (левая и правая стороны) с учётом эмоций
        player_id = self.app.current_profile.player_character_id
        other_npcs = [cid for cid in character_ids if cid != player_id]
        left_avatars = []   # (cid, char, emotion, avatar_path)
        right_avatars = []
        
        # Игрок слева (если есть)
        if player_id:
            player_char = self.app.characters.get(player_id)
            if player_char:
                emotion = emotion_map.get(player_id)
                avatar_path = self._get_avatar_for_character(player_char, emotion)
                if avatar_path:
                    left_avatars.append(('player', player_char, emotion, avatar_path))
        
        # Другие NPC: первые два слева, следующие три справа
        for i, cid in enumerate(other_npcs[:2]):
            char = self.app.characters.get(cid)
            if char:
                emotion = emotion_map.get(cid)
                avatar_path = self._get_avatar_for_character(char, emotion)
                if avatar_path:
                    left_avatars.append((cid, char, emotion, avatar_path))
        
        for cid in other_npcs[2:5]:
            char = self.app.characters.get(cid)
            if char:
                emotion = emotion_map.get(cid)
                avatar_path = self._get_avatar_for_character(char, emotion)
                if avatar_path:
                    right_avatars.append((cid, char, emotion, avatar_path))
        
        self._set_avatars(left_avatars, right_avatars)

        if self.debug_mode:
            self._draw_debug_rects()

    # ====================== Вспомогательные методы для получения изображений по эмоциям ======================
    def _get_avatar_for_character(self, char, emotion_name: str = None) -> str:
        """Возвращает путь к аватару для персонажа с учётом эмоции.
        Приоритет: emotion_images[emotion_name]["avatar"] -> char.avatar_image -> "".
        """
        if not char:
            return ""
        
        # Если указана эмоция и у персонажа есть привязки эмоций
        if emotion_name:
            emotion_images = getattr(char, 'emotion_images', {})
            # Ищем по имени эмоции (сравниваем названия, а не ID)
            for em_id, paths in emotion_images.items():
                em_obj = self.app.emotions.get(em_id)
                if em_obj and em_obj.name == emotion_name:
                    avatar_path = paths.get("avatar", "")
                    if avatar_path:
                        full_path = self._get_full_path(avatar_path)
                        if full_path:
                            return full_path
            # Если не нашли, пробуем искать по ID (на случай если передали ID)
            if emotion_name in emotion_images:
                avatar_path = emotion_images[emotion_name].get("avatar", "")
                if avatar_path:
                    full_path = self._get_full_path(avatar_path)
                    if full_path:
                        return full_path
        
        # Нейтральное/дефолтное изображение
        default_avatar = getattr(char, 'avatar_image', '')
        if default_avatar:
            full_path = self._get_full_path(default_avatar)
            if full_path:
                return full_path
        return ""

    def _get_sprite_for_character(self, char, emotion_name: str = None) -> str:
        """Возвращает путь к спрайту для персонажа с учётом эмоции.
        Приоритет: emotion_images[emotion_name]["sprite"] -> char.sprite_image -> "".
        """
        if not char:
            return ""
        
        if emotion_name:
            emotion_images = getattr(char, 'emotion_images', {})
            for em_id, paths in emotion_images.items():
                em_obj = self.app.emotions.get(em_id)
                if em_obj and em_obj.name == emotion_name:
                    sprite_path = paths.get("sprite", "")
                    if sprite_path:
                        full_path = self._get_full_path(sprite_path)
                        if full_path:
                            return full_path
            if emotion_name in emotion_images:
                sprite_path = emotion_images[emotion_name].get("sprite", "")
                if sprite_path:
                    full_path = self._get_full_path(sprite_path)
                    if full_path:
                        return full_path
        
        default_sprite = getattr(char, 'sprite_image', '')
        if default_sprite:
            full_path = self._get_full_path(default_sprite)
            if full_path:
                return full_path
        return ""

    # ====================== Фон ======================
    def _set_background(self, image_path: str = None):
        self.canvas.delete("background")
        if image_path and os.path.exists(image_path):
            try:
                img = Image.open(image_path)
                canvas_w = self.canvas.winfo_width() or 1280
                canvas_h = self.canvas.winfo_height() or 720
                img_ratio = img.width / img.height
                canvas_ratio = canvas_w / canvas_h
                if img_ratio > canvas_ratio:
                    new_w = canvas_w
                    new_h = int(canvas_w / img_ratio)
                else:
                    new_h = canvas_h
                    new_w = int(canvas_h * img_ratio)
                img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                self.current_background_photo = ImageTk.PhotoImage(img_resized)
                x = (canvas_w - new_w) // 2
                y = (canvas_h - new_h) // 2
                self.canvas.create_image(x, y, anchor=tk.NW, image=self.current_background_photo, tags="background")
            except Exception as e:
                print(f"Background error: {e}")
                self.canvas.create_rectangle(0, 0, self.canvas.winfo_width(), self.canvas.winfo_height(), fill="black", tags="background")
        else:
            self.canvas.create_rectangle(0, 0, self.canvas.winfo_width(), self.canvas.winfo_height(), fill="black", tags="background")

    # ====================== СПРАЙТЫ ======================
    def _set_sprites(self, characters: List[tuple]):
        """characters: список (cid, char, emotion_name, image_path)"""
        self.canvas.delete("sprite")
        self._sprite_photos.clear()
        if not characters:
            return

        self.update_idletasks()
        canvas_w = self.canvas.winfo_width() or 1280
        bottom_y = self.bottom_frame.winfo_y()

        max_sprite_h = int(bottom_y * 0.78)

        count = len(characters)
        if count == 1:
            positions = [0.5]
        elif count == 2:
            positions = [0.33, 0.67]
        else:
            positions = [0.25, 0.5, 0.75]

        for idx, (cid, char, emotion_name, img_path) in enumerate(characters):
            if not img_path or not os.path.exists(img_path):
                continue
            try:
                img = Image.open(img_path)
                ratio = img.width / img.height

                h = max_sprite_h
                w = int(h * ratio)
                if w > canvas_w * 0.29:
                    w = int(canvas_w * 0.29)
                    h = int(w / ratio)

                resized = img.resize((w, h), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(resized)
                self._sprite_photos.append(photo)

                x = int((canvas_w - w) * positions[idx])
                y = bottom_y - h  # убран отступ -12

                self.canvas.create_image(x, y, anchor=tk.NW, image=photo, tags="sprite")
                if self.debug_mode:
                    # Рисуем границу спрайта
                    self.canvas.create_rectangle(x, y, x+w, y+h, outline="yellow", width=1, dash=(2,2), tags="debug_sprite")
                    self.canvas.create_text(x+5, y+5, text=f"{char.name}\n{emotion_name or 'нейтр'}", anchor=tk.NW, fill="yellow", font=("Arial", 8), tags="debug_sprite")
            except Exception as e:
                print(f"Sprite error {getattr(char, 'name', cid)}: {e}")

    # ====================== АВАТАРКИ ======================
    def _set_avatars(self, left_avatars: List[tuple], right_avatars: List[tuple]):
        """Каждый элемент: (cid, char, emotion_name, image_path)"""
        self.canvas.delete("avatar_left")
        self.canvas.delete("avatar_right")
        self._avatar_photos.clear()

        self.update_idletasks()
        canvas_w = self.canvas.winfo_width() or 1280
        bottom_y = self.bottom_frame.winfo_y()
        available_h = bottom_y

        MAX_AVATAR_SIZE = 140

        # Левая сторона (снизу вверх)
        left_rev = list(reversed(left_avatars))
        left_count = len(left_rev)
        self._last_left_count = left_count
        if left_count > 0:
            size = max(min(available_h // left_count, MAX_AVATAR_SIZE), 60)
            for i, (cid, char, emotion_name, img_path) in enumerate(left_rev):
                y = bottom_y - (i + 1) * size
                self._place_avatar(img_path, char, emotion_name, 8, y, size, "avatar_left")

        # Правая сторона (снизу вверх)
        right_rev = list(reversed(right_avatars))
        right_count = len(right_rev)
        self._last_right_count = right_count
        if right_count > 0:
            size = max(min(available_h // right_count, MAX_AVATAR_SIZE), 60)
            for i, (cid, char, emotion_name, img_path) in enumerate(right_rev):
                y = bottom_y - (i + 1) * size
                x = canvas_w - 8 - size
                self._place_avatar(img_path, char, emotion_name, x, y, size, "avatar_right")

    def _place_avatar(self, img_path, char, emotion_name, x, y, size, tag):
        if not img_path or not os.path.exists(img_path):
            return
        try:
            img = Image.open(img_path)
            img.thumbnail((size, size), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._avatar_photos.append(photo)
            img_w, img_h = img.size
            off_x = (size - img_w) // 2
            off_y = (size - img_h) // 2
            self.canvas.create_image(x + off_x, y + off_y, anchor=tk.NW, image=photo, tags=tag)
            if self.debug_mode:
                self.canvas.create_rectangle(x, y, x+size, y+size, outline="cyan", width=1, dash=(2,2), tags="debug_avatar")
                text = char.name if char else ""
                if emotion_name:
                    text += f"\n({emotion_name})"
                self.canvas.create_text(x+5, y+5, text=text, anchor=tk.NW, fill="cyan", font=("Arial", 8), tags="debug_avatar")
        except Exception as e:
            print(f"Avatar error {getattr(char, 'name', '')}: {e}")

    # ====================== Отладка ======================
    def _draw_debug_rects(self):
        self._clear_debug_rects()
        canvas_w = self.canvas.winfo_width() or 1280
        bottom_y = self.bottom_frame.winfo_y()
        max_sprite_h = int(bottom_y * 0.78)

        # Спрайты
        positions = [0.25, 0.5, 0.75]
        for i, px in enumerate(positions):
            left = int(canvas_w * px - 75)
            right = left + 150
            top = bottom_y - max_sprite_h
            self.canvas.create_rectangle(left, top, right, bottom_y,
                                         outline="yellow", width=2, dash=(4,4), tags="debug_rect")
            self.canvas.create_text((left+right)//2, top+10, text=f"Спрайт {i+1}",
                                    fill="yellow", font=("Arial", 9), tags="debug_rect")

        available_h = bottom_y
        MAX_AVATAR_SIZE = 140

        # Левые аватарки
        left_count = getattr(self, '_last_left_count', 0)
        if left_count > 0:
            size = max(min(available_h // left_count, MAX_AVATAR_SIZE), 60)
            for i in range(left_count):
                y = bottom_y - (i + 1) * size
                self.canvas.create_rectangle(8, y, 8 + size, y + size,
                                             outline="cyan", width=2, dash=(4,4), tags="debug_rect")
                label = "Игрок" if i == left_count-1 else f"Лев.{left_count-1-i}"
                self.canvas.create_text(8 + size//2, y + size//2, text=label,
                                        fill="cyan", font=("Arial", 8), tags="debug_rect")

        # Правые аватарки
        right_count = getattr(self, '_last_right_count', 0)
        if right_count > 0:
            size = max(min(available_h // right_count, MAX_AVATAR_SIZE), 60)
            for i in range(right_count):
                y = bottom_y - (i + 1) * size
                x = canvas_w - 8 - size
                self.canvas.create_rectangle(x, y, x + size, y + size,
                                             outline="cyan", width=2, dash=(4,4), tags="debug_rect")
                self.canvas.create_text(x + size//2, y + size//2, text=f"Прав.{i}",
                                        fill="cyan", font=("Arial", 8), tags="debug_rect")

    def _clear_debug_rects(self):
        self.canvas.delete("debug_rect")
        self.canvas.delete("debug_sprite")
        self.canvas.delete("debug_avatar")

    def _get_full_path(self, rel_path: str) -> str:
        if not rel_path:
            return ""
        campaign_path = self.app.storage._get_campaign_path()
        full = os.path.join(campaign_path, rel_path)
        return full if os.path.exists(full) else ""

    # ====================== Привязка к основному приложению ======================
    def _bind_to_app(self):
        self.original_display_message = self.app.center_panel.display_message
        self.original_display_system = self.app.center_panel.display_system_message
        self.original_set_input_state = self.app.center_panel.set_input_state
        self.original_is_generating = self.app.is_generating

        def wrapped_display_message(text, tag=None):
            if tag == "assistant":
                self.append_dialog(text)
            elif tag == "system" and ("Этап" in text or "✅" in text or "⚠️" in text):
                self.append_dialog(text)
            self.original_display_message(text, tag)

        def wrapped_display_system(text):
            if "Этап" in text or "✅" in text or "⚠️" in text:
                self.append_dialog(text)
            self.original_display_system(text)

        def wrapped_set_input_state(state):
            self.original_set_input_state(state)
            if state == "normal":
                self._set_buttons_state(generating=False)
            else:
                self._set_buttons_state(generating=True)

        self.app.center_panel.display_message = wrapped_display_message
        self.app.center_panel.display_system_message = wrapped_display_system
        self.app.center_panel.set_input_state = wrapped_set_input_state

        if hasattr(self.app, 'stage_processor'):
            self.original_finish = self.app.stage_processor._finish_generation
            def new_finish():
                self.refresh_from_current_state()
                self.original_finish()
                self._set_buttons_state(generating=False)
            self.app.stage_processor._finish_generation = new_finish

    def cleanup(self):
        if self._monitor_after_id:
            self.after_cancel(self._monitor_after_id)
        if hasattr(self, 'original_display_message'):
            self.app.center_panel.display_message = self.original_display_message
        if hasattr(self, 'original_display_system'):
            self.app.center_panel.display_system_message = self.original_display_system
        if hasattr(self, 'original_set_input_state'):
            self.app.center_panel.set_input_state = self.original_set_input_state
        if hasattr(self, 'original_finish'):
            self.app.stage_processor._finish_generation = self.original_finish