# center_panel_localized.py
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from ui_utils import add_context_menu
from typing import List, Dict
from localization import loc


class CenterPanel(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.thinking_visible = tk.BooleanVar(value=True)
        self.system_info_visible = tk.BooleanVar(value=False)
        self.last_full_prompt = ""
        self._sending = False
        self.stage_names = app.stage_names
        self.prompts_by_stage = {}
        self.current_selected_stage = None

        self._build_ui()
        self._configure_tags()
        self._configure_tags_for_info()

    def refresh_language(self):
        """Обновляет тексты кнопок и заголовков после смены языка."""
        self.thinking_frame.config(text=loc.tr("center_thinking"))
        self.info_frame.config(text=loc.tr("center_info_prompt"))
        self.toggle_info_btn.config(text=loc.tr("center_collapse") if self.system_info_visible.get() else loc.tr("center_expand"))
        self.toggle_think_btn.config(text=loc.tr("center_collapse") if self.thinking_visible.get() else loc.tr("center_expand"))
        self.open_window_btn.config(text=loc.tr("center_open_window"))
        self.send_btn.config(text=loc.tr("center_send"))
        self.stop_btn.config(text=loc.tr("center_stop"))
        self.start_btn.config(text=loc.tr("center_start_game"))
        self.clear_btn.config(text=loc.tr("center_clear"))
        self.regenerate_btn.config(text=loc.tr("center_regenerate"))
        self.regenerate_translation_btn.config(text=loc.tr("center_regenerate_translation"))
        self.delete_last_btn.config(text=loc.tr("center_delete_last"))
        self.debug_check.config(text=loc.tr("center_debug_mode"))
        self.step_btn.config(text=loc.tr("center_step"))
        self.regenerate_step_btn.config(text=loc.tr("center_regenerate_step"))
        # Дополнительно заголовок инфо-панели
        self._update_stage_combobox()

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=0, minsize=0)
        self.grid_rowconfigure(1, weight=0, minsize=0)
        self.grid_rowconfigure(2, weight=1, minsize=50)
        self.grid_rowconfigure(3, weight=0, minsize=120)
        self.grid_columnconfigure(0, weight=1)

        self.info_frame = ttk.LabelFrame(self, text=loc.tr("center_info_prompt"))
        self.info_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 0))
        info_header = ttk.Frame(self.info_frame)
        info_header.pack(fill=tk.X, padx=2, pady=2)
        self.stage_combo = ttk.Combobox(info_header, state="readonly", width=20)
        self.stage_combo.pack(side=tk.LEFT, padx=(10, 5))
        self.stage_combo.bind("<<ComboboxSelected>>", self._on_stage_select)
        self.toggle_info_btn = ttk.Button(info_header, text=loc.tr("center_collapse"), command=self._toggle_system_info)
        self.toggle_info_btn.pack(side=tk.LEFT)
        self.open_window_btn = ttk.Button(info_header, text=loc.tr("center_open_window"), command=self._open_prompt_window)
        self.open_window_btn.pack(side=tk.LEFT, padx=5)
        ttk.Label(info_header, text=loc.tr("center_info_prompt")).pack(side=tk.LEFT)
        self.info_text = scrolledtext.ScrolledText(self.info_frame, wrap=tk.WORD, font=("Arial", 9), height=4, state=tk.DISABLED)
        self.info_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        add_context_menu(self.info_text)

        self.thinking_frame = ttk.LabelFrame(self, text=loc.tr("center_thinking"))
        self.thinking_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=(5, 0))
        think_header = ttk.Frame(self.thinking_frame)
        think_header.pack(fill=tk.X, padx=2, pady=2)
        self.toggle_think_btn = ttk.Button(think_header, text=loc.tr("center_collapse"), command=self._toggle_thinking)
        self.toggle_think_btn.pack(side=tk.LEFT)
        self.thinking_text = scrolledtext.ScrolledText(self.thinking_frame, wrap=tk.WORD, font=("Arial", 10), height=6, state=tk.DISABLED)
        self.thinking_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        add_context_menu(self.thinking_text)

        self.chat_frame = ttk.Frame(self)
        self.chat_frame.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        self.chat_frame.grid_rowconfigure(1, weight=1)
        self.chat_frame.grid_columnconfigure(0, weight=1)

        token_status_frame = ttk.Frame(self.chat_frame)
        token_status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        ttk.Label(token_status_frame, text=loc.tr("center_tokens_system")).pack(side=tk.LEFT)
        self.token_count_var = tk.StringVar(value="0")
        token_label = ttk.Label(token_status_frame, textvariable=self.token_count_var, font=("Arial", 10, "bold"))
        token_label.pack(side=tk.LEFT, padx=(5,0))
        ttk.Label(token_status_frame, text=loc.tr("center_tokens_total")).pack(side=tk.LEFT, padx=(10,0))
        self.total_token_var = tk.StringVar(value="0")
        total_token_label = ttk.Label(token_status_frame, textvariable=self.total_token_var, font=("Arial", 10, "bold"))
        total_token_label.pack(side=tk.LEFT, padx=(5,0))

        self.chat_display = scrolledtext.ScrolledText(self.chat_frame, wrap=tk.WORD, font=("Arial", 11), state=tk.DISABLED)
        self.chat_display.grid(row=1, column=0, sticky="nsew")
        add_context_menu(self.chat_display)

        self.input_container = ttk.Frame(self)
        self.input_container.grid(row=3, column=0, sticky="ew", padx=5, pady=5)
        self.input_text = tk.Text(self.input_container, height=3, font=("Arial", 11))
        self.input_text.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        add_context_menu(self.input_text)

        # --- Ряд 1: Основные кнопки ---
        btn_frame_top = ttk.Frame(self.input_container)
        btn_frame_top.pack(fill=tk.X, pady=2)

        self.send_btn = ttk.Button(btn_frame_top, text=loc.tr("center_send"), command=self._send_message)
        self.send_btn.pack(side=tk.LEFT, padx=2)
        self.stop_btn = ttk.Button(btn_frame_top, text=loc.tr("center_stop"), command=lambda: self.app.update("stop_generation"))
        self.stop_btn.pack(side=tk.LEFT, padx=2)
        self.start_btn = ttk.Button(btn_frame_top, text=loc.tr("center_start_game"), command=lambda: self.app.update("start_game"))
        self.start_btn.pack(side=tk.LEFT, padx=2)
        self.clear_btn = ttk.Button(btn_frame_top, text=loc.tr("center_clear"), command=lambda: self.app.update("clear_chat"))
        self.clear_btn.pack(side=tk.LEFT, padx=2)

        # --- Ряд 2: Кнопки управления ответами и переводом ---
        btn_frame_mid = ttk.Frame(self.input_container)
        btn_frame_mid.pack(fill=tk.X, pady=2)

        self.regenerate_btn = ttk.Button(btn_frame_mid, text=loc.tr("center_regenerate"), command=self._regenerate_last)
        self.regenerate_btn.pack(side=tk.LEFT, padx=2)
        self.regenerate_translation_btn = ttk.Button(btn_frame_mid, text=loc.tr("center_regenerate_translation"), command=self._regenerate_translation)
        self.regenerate_translation_btn.pack(side=tk.LEFT, padx=2)
        self.delete_last_btn = ttk.Button(btn_frame_mid, text=loc.tr("center_delete_last"), command=self._delete_last_user_message)
        self.delete_last_btn.pack(side=tk.LEFT, padx=2)

        # --- Ряд 3: Кнопки отладки и пошагового выполнения ---
        btn_frame_debug = ttk.Frame(self.input_container)
        btn_frame_debug.pack(fill=tk.X, pady=2)

        self.debug_mode = tk.BooleanVar(value=False)
        self.debug_check = ttk.Checkbutton(btn_frame_debug, text=loc.tr("center_debug_mode"), variable=self.debug_mode,
                                           command=self._toggle_debug_mode)
        self.debug_check.pack(side=tk.LEFT, padx=2)

        self.step_btn = ttk.Button(btn_frame_debug, text=loc.tr("center_step"), command=self._step_continue, state=tk.DISABLED)
        self.step_btn.pack(side=tk.LEFT, padx=2)

        self.regenerate_step_btn = ttk.Button(btn_frame_debug, text=loc.tr("center_regenerate_step"), command=self._regenerate_last_step, state=tk.DISABLED)
        self.regenerate_step_btn.pack(side=tk.LEFT, padx=2)

        self.input_text.bind("<Control-Return>", lambda e: self._send_message())

        self.temp_response_start = None

    def _toggle_debug_mode(self):
        self.app.update("set_debug_mode", {"enabled": self.debug_mode.get()})
        if self.debug_mode.get():
            self.regenerate_step_btn.config(state=tk.NORMAL)
        else:
            self.step_btn.config(state=tk.DISABLED)
            self.regenerate_step_btn.config(state=tk.DISABLED)

    def set_step_button_state(self, enabled: bool):
        if self.debug_mode.get():
            self.step_btn.config(state=tk.NORMAL if enabled else tk.DISABLED)
        else:
            self.step_btn.config(state=tk.DISABLED)

    def _step_continue(self):
        self.app.update("step_continue")

    def _regenerate_last_step(self):
        if self.app.is_generating:
            messagebox.showwarning(loc.tr("center_regenerate_step"), loc.tr("error_stop_first"))
            return
        if not self.debug_mode.get():
            messagebox.showinfo(loc.tr("center_debug_mode"), loc.tr("error_debug_mode_off"))
            return
        self.app.update("regenerate_last_step")

    def update_token_count(self, token_str: str, total_str: str = None):
        self.token_count_var.set(token_str)
        if total_str is not None:
            self.total_token_var.set(total_str)

    def update_total_tokens(self, total_str: str):
        self.total_token_var.set(total_str)

    def _configure_tags(self):
        self.chat_display.tag_config("user", foreground="blue")
        self.chat_display.tag_config("assistant", foreground="green")
        self.chat_display.tag_config("system", foreground="gray", font=("Arial", 10, "italic"))
        self.chat_display.tag_config("error", foreground="red")
        self.thinking_text.tag_config("thinking", foreground="purple", font=("Arial", 10, "italic"))
        self.chat_display.tag_config("component_header", foreground="darkorange", font=("Arial", 10, "bold"))
        self.chat_display.tag_config("component_item", foreground="navy")
        self.chat_display.tag_config("translation", foreground="darkgreen", font=("Arial", 11, "italic"))
        self.chat_display.tag_config("temp", foreground="orange", font=("Arial", 10, "italic"))

    def _toggle_thinking(self):
        if self.thinking_visible.get():
            self.thinking_text.pack_forget()
            self.toggle_think_btn.config(text=loc.tr("center_expand"))
            self.thinking_visible.set(False)
            self.grid_rowconfigure(1, minsize=0, weight=0)
        else:
            self.thinking_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            self.toggle_think_btn.config(text=loc.tr("center_collapse"))
            self.thinking_visible.set(True)
            self.grid_rowconfigure(1, minsize=100, weight=0)
        self.update_idletasks()

    def _toggle_system_info(self):
        if self.system_info_visible.get():
            self.info_text.pack_forget()
            self.toggle_info_btn.config(text=loc.tr("center_expand"))
            self.system_info_visible.set(False)
            self.grid_rowconfigure(0, minsize=0, weight=0)
        else:
            self.info_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            self.toggle_info_btn.config(text=loc.tr("center_collapse"))
            self.system_info_visible.set(True)
            self.grid_rowconfigure(0, minsize=120, weight=0)
        self.update_idletasks()

    def _open_prompt_window(self):
        if not self.last_full_prompt:
            messagebox.showinfo(loc.tr("center_info_prompt"), loc.tr("error_no_last_message"))
            return
        win = tk.Toplevel(self)
        win.title(loc.tr("center_info_prompt"))
        win.geometry("800x600")
        text_area = scrolledtext.ScrolledText(win, wrap=tk.WORD, font=("Courier", 10))
        text_area.pack(fill=tk.BOTH, expand=True)
        text_area.insert(tk.END, self.last_full_prompt)
        text_area.config(state=tk.DISABLED)
        add_context_menu(text_area)

    def log_system_prompt(self, prompt: str, stage_name: str = None):
        if stage_name:
            self.prompts_by_stage[stage_name] = prompt
            self._update_stage_combobox()
            if self.current_selected_stage == stage_name:
                self._display_prompt(prompt)
        else:
            self.prompts_by_stage["other"] = prompt
            if self.current_selected_stage == "other":
                self._display_prompt(prompt)

    def _update_stage_combobox(self):
        stages = list(self.prompts_by_stage.keys())
        if not stages:
            return
        if "other" not in stages and "other" in self.prompts_by_stage:
            stages.append("other")
        self.stage_combo['values'] = stages
        if self.current_selected_stage not in stages:
            self.current_selected_stage = stages[0] if stages else None
            if self.current_selected_stage:
                self.stage_combo.set(self.current_selected_stage)
                self._display_prompt(self.prompts_by_stage[self.current_selected_stage])

    def _display_prompt(self, prompt: str):
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)

        lines = prompt.split('\n')
        for line in lines:
            if line.startswith("==="):
                self.info_text.insert(tk.END, line + "\n", "header")
            elif line.startswith("[") and "]" in line and ":" in line:
                role_part = line.split("]", 1)[1].strip().split(":", 1)[0].lower()
                if role_part == "system":
                    tag = "system_role"
                elif role_part == "user":
                    tag = "user_role"
                elif role_part == "assistant":
                    tag = "assistant_role"
                else:
                    tag = "default"
                self.info_text.insert(tk.END, line + "\n", tag)
            else:
                self.info_text.insert(tk.END, line + "\n", "content")
        self.info_text.config(state=tk.DISABLED)
        self.last_full_prompt = prompt
        self.info_text.see("1.0")

    def _on_stage_select(self, event=None):
        selected = self.stage_combo.get()
        if selected and selected in self.prompts_by_stage:
            self.current_selected_stage = selected
            self._display_prompt(self.prompts_by_stage[selected])

    def _configure_tags_for_info(self):
        self.info_text.tag_config("header", foreground="darkblue", font=("Arial", 10, "bold"))
        self.info_text.tag_config("system_role", foreground="green", font=("Arial", 9, "bold"))
        self.info_text.tag_config("user_role", foreground="blue", font=("Arial", 9, "bold"))
        self.info_text.tag_config("assistant_role", foreground="purple", font=("Arial", 9, "bold"))
        self.info_text.tag_config("content", foreground="black", font=("Arial", 9))

    def display_components(self, components: List[Dict]):
        self.display_message("\n📦 **Состав отправленного промта:**\n", "system")
        for comp in components:
            comp_type = comp.get("type", "")
            name = comp.get("name", "")
            items = comp.get("items", [])
            header = f"  • {comp_type}"
            if name:
                header += f" — {name}"
            self.display_message(header + "\n", "component_header")
            for item in items:
                self.display_message(f"      - {item}\n", "component_item")
        self.display_message("\n", "system")

    def set_input_state(self, state):
        self.input_text.config(state=state)
        if state == tk.NORMAL:
            self.send_btn.config(state=tk.NORMAL)
            self.regenerate_btn.config(state=tk.NORMAL)
            self.delete_last_btn.config(state=tk.NORMAL)
            self._sending = False
        else:
            self.send_btn.config(state=tk.DISABLED)
            self.regenerate_btn.config(state=tk.DISABLED)
            self.delete_last_btn.config(state=tk.DISABLED)

    def start_new_response(self, clear_thinking=True):
        if clear_thinking:
            self.thinking_text.config(state=tk.NORMAL)
            self.thinking_text.delete(1.0, tk.END)
            self.thinking_text.config(state=tk.DISABLED)
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, loc.tr("center_assistant_prefix"), "assistant")
        self.current_response_start = self.chat_display.index(tk.INSERT)
        self.chat_display.config(state=tk.DISABLED)

    def get_current_response_start(self):
        return getattr(self, 'current_response_start', None)

    def start_translation_response(self):
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, loc.tr("center_assistant_translation_prefix"), "assistant")
        self.current_response_start = self.chat_display.index(tk.INSERT)
        self.chat_display.config(state=tk.DISABLED)

    def start_translation_stream(self, response_start):
        self.translation_start_pos = response_start
        self.chat_display.config(state=tk.NORMAL)
        end_pos = self.chat_display.index(tk.END)
        self.chat_display.delete(response_start, end_pos)
        self.chat_display.insert(tk.END, loc.tr("center_assistant_translation_prefix"), "assistant")
        self.current_translation_start = self.chat_display.index(tk.INSERT)
        self.chat_display.config(state=tk.DISABLED)

    def append_translation_stream(self, text: str):
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, text, "translation")
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)
        self.update_idletasks()

    def finalize_translation(self, full_translation: str, response_start):
        self.chat_display.config(state=tk.NORMAL)
        if hasattr(self, 'current_translation_start'):
            self.chat_display.delete(self.current_translation_start, tk.END)
            self.chat_display.insert(self.current_translation_start, full_translation, "translation")
        self.chat_display.insert(tk.END, "\n\n")
        self.chat_display.config(state=tk.DISABLED)
        self.update_idletasks()

    def append_thinking(self, text: str):
        self.thinking_text.config(state=tk.NORMAL)
        self.thinking_text.insert(tk.END, text, "thinking")
        self.thinking_text.see(tk.END)
        self.thinking_text.config(state=tk.DISABLED)
        self.update_idletasks()

    def append_response(self, text: str):
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, text)
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)
        self.update_idletasks()

    def remove_last_response(self):
        if hasattr(self, 'current_response_start') and self.current_response_start:
            self.chat_display.config(state=tk.NORMAL)
            end_pos = self.chat_display.index(tk.END)
            self.chat_display.delete(self.current_response_start, end_pos)
            self.chat_display.config(state=tk.DISABLED)

    def finalize_response(self, translation_pending=False):
        if not translation_pending:
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.insert(tk.END, "\n\n")
            self.chat_display.see(tk.END)
            self.chat_display.config(state=tk.DISABLED)
            self.update_idletasks()

    def display_message(self, text: str, tag=None):
        self.chat_display.config(state=tk.NORMAL)
        if tag:
            self.chat_display.insert(tk.END, text, tag)
        else:
            self.chat_display.insert(tk.END, text)
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)
        self.update_idletasks()

    def display_system_message(self, text: str):
        self.display_message(text, "system")

    def clear_chat(self):
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.delete(1.0, tk.END)
        self.chat_display.config(state=tk.DISABLED)
        self.thinking_text.config(state=tk.NORMAL)
        self.thinking_text.delete(1.0, tk.END)
        self.thinking_text.config(state=tk.DISABLED)
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        self.info_text.config(state=tk.DISABLED)
        self.last_full_prompt = ""
        self.prompts_by_stage.clear()
        self.current_selected_stage = None
        self._update_stage_combobox()
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        self.info_text.config(state=tk.DISABLED)
        self.last_full_prompt = ""

    def update_translation_button_state(self):
        if self.app.enable_assistant_translation and self.app.use_two_models and self.app.last_original_response is not None:
            self.regenerate_translation_btn.config(state=tk.NORMAL)
        else:
            self.regenerate_translation_btn.config(state=tk.DISABLED)

    def start_temp_response(self):
        self.chat_display.config(state=tk.NORMAL)
        self.clear_temp_response()
        self.chat_display.insert(tk.END, loc.tr("center_temp_output"), "temp")
        self.temp_start_index = self.chat_display.index(tk.INSERT)
        self.chat_display.config(state=tk.DISABLED)
        self.update_idletasks()

    def append_temp_content(self, text: str):
        if self.temp_start_index:
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.insert(tk.END, text, "temp")
            self.chat_display.see(tk.END)
            self.chat_display.config(state=tk.DISABLED)
            self.update_idletasks()

    def clear_temp_response(self):
        self.chat_display.config(state=tk.NORMAL)
        ranges = list(self.chat_display.tag_ranges("temp"))
        for i in range(0, len(ranges), 2):
            start = ranges[i]
            end = ranges[i+1]
            self.chat_display.delete(start, end)
        self.chat_display.tag_delete("temp")
        self.temp_start_index = None
        self.chat_display.config(state=tk.DISABLED)
        self.update_idletasks()

    def _send_message(self):
        if self.app.is_generating:
            messagebox.showwarning(loc.tr("center_send"), loc.tr("error_generation_in_progress"))
            return
        if self._sending:
            return
        message = self.input_text.get("1.0", tk.END).strip()
        if message:
            self._sending = True
            self.input_text.delete("1.0", tk.END)
            self.display_message(f"{loc.tr('center_user_prefix')}{message}\n", "user")
            self.send_btn.config(state=tk.DISABLED)
            self.app.update("send_message", {"message": message})

    def _regenerate_last(self):
        if self.app.is_generating:
            messagebox.showwarning(loc.tr("center_regenerate"), loc.tr("error_generation_in_progress"))
            return
        if not self.app.last_user_message:
            messagebox.showinfo(loc.tr("center_regenerate"), loc.tr("error_no_last_message"))
            return
        self.app.update("regenerate_last_response")

    def _regenerate_translation(self):
        if self.app.is_generating:
            messagebox.showwarning(loc.tr("center_regenerate_translation"), loc.tr("error_generation_in_progress"))
            return
        self.app.update("regenerate_translation")

    def _delete_last_user_message(self):
        if self.app.is_generating:
            messagebox.showwarning(loc.tr("center_delete_last"), loc.tr("error_stop_first"))
            return
        self.app.update("delete_last_user_message")