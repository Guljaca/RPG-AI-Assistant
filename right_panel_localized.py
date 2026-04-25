# right_panel_localized.py
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
from ui_tabs_localized import ProfileTab, BaseEditorTab, SystemPromptsTab, TranslatorPromptsTab, StagePromptsTab, HistoryTab
from models import Narrator, Character, Location, Item, Event, Scenario, Emotion
from localization import loc

class RightPanel(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.tab_frames = {}
        self.current_tab = None
        self._build_ui()
        self._create_tabs()
        self.show_tab("profile")

    def _build_ui(self):
        self.button_container = ttk.Frame(self)
        self.button_container.pack(fill=tk.X, padx=5, pady=5)
        row1 = ttk.Frame(self.button_container)
        row1.pack(fill=tk.X, pady=2)
        row2 = ttk.Frame(self.button_container)
        row2.pack(fill=tk.X, pady=2)
        row3 = ttk.Frame(self.button_container)
        row3.pack(fill=tk.X, pady=2)
        row4 = ttk.Frame(self.button_container)
        row4.pack(fill=tk.X, pady=2)
        row5 = ttk.Frame(self.button_container)
        row5.pack(fill=tk.X, pady=2)

        buttons = [
            ("profile", loc.tr("profile_tab"), row1),
            ("narrators", loc.tr("profile_narrators"), row1),
            ("characters", loc.tr("profile_characters"), row1),
            ("locations", loc.tr("profile_locations"), row2),
            ("items", loc.tr("profile_items"), row2),
            ("events", loc.tr("profile_events"), row2),
            ("scenarios", loc.tr("profile_scenarios"), row3),
            ("emotions", loc.tr("profile_emotions"), row3),
            ("prompts", loc.tr("prompts_tab_system"), row3),
            ("translator_prompts", loc.tr("prompts_tab_translator"), row4),
            ("stage_prompts", loc.tr("stage_tab"), row4),
            ("history", loc.tr("history_tab"), row5)
        ]

        self.tab_buttons = {}
        for tab_name, text, parent_row in buttons:
            btn = ttk.Button(parent_row, text=text, command=lambda n=tab_name: self.show_tab(n))
            btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
            self.tab_buttons[tab_name] = btn

        self.content_frame = ttk.Frame(self)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _create_tabs(self):
        self.tab_frames["profile"] = ProfileTab(self.content_frame, self.app)
        self.tab_frames["narrators"] = BaseEditorTab(self.content_frame, self.app, "narrators", Narrator, loc.tr("profile_narrators"))
        self.tab_frames["characters"] = BaseEditorTab(self.content_frame, self.app, "characters", Character, loc.tr("profile_characters"))
        self.tab_frames["locations"] = BaseEditorTab(self.content_frame, self.app, "locations", Location, loc.tr("profile_locations"))
        self.tab_frames["items"] = BaseEditorTab(self.content_frame, self.app, "items", Item, loc.tr("profile_items"))
        self.tab_frames["events"] = BaseEditorTab(self.content_frame, self.app, "events", Event, loc.tr("profile_events"))
        self.tab_frames["scenarios"] = BaseEditorTab(self.content_frame, self.app, "scenarios", Scenario, loc.tr("profile_scenarios"))
        self.tab_frames["emotions"] = BaseEditorTab(self.content_frame, self.app, "emotions", Emotion, loc.tr("profile_emotions"))
        self.tab_frames["prompts"] = SystemPromptsTab(self.content_frame, self.app)
        self.tab_frames["translator_prompts"] = TranslatorPromptsTab(self.content_frame, self.app)
        self.tab_frames["stage_prompts"] = StagePromptsTab(self.content_frame, self.app)
        self.tab_frames["history"] = HistoryTab(self.content_frame, self.app)

    def show_tab(self, tab_name: str):
        if self.current_tab == tab_name:
            return
        if self.current_tab and self.current_tab in self.tab_frames:
            self.tab_frames[self.current_tab].pack_forget()
        if tab_name in self.tab_frames:
            self.tab_frames[tab_name].pack(fill=tk.BOTH, expand=True)
            self.current_tab = tab_name
            for name, btn in self.tab_buttons.items():
                if name == tab_name:
                    btn.config(state="disabled")
                else:
                    btn.config(state="normal")
            self.tab_frames[tab_name].refresh()

    def refresh(self):
        for frame in self.tab_frames.values():
            if hasattr(frame, "refresh"):
                frame.refresh()

    def cleanup_inactive_narrators(self):
        stage_frame = self.tab_frames.get("stage_prompts")
        if stage_frame and hasattr(stage_frame, "cleanup_inactive_narrators"):
            stage_frame.cleanup_inactive_narrators()

    def notify_object_created(self, obj_type: str, obj_id: str):
        frame = self.tab_frames.get(obj_type)
        if frame and hasattr(frame, "add_object"):
            frame.add_object(obj_id)

    def notify_object_updated(self, obj_type: str, obj_id: str):
        frame = self.tab_frames.get(obj_type)
        if frame and hasattr(frame, "update_object"):
            frame.update_object(obj_id)

    def notify_object_deleted(self, obj_type: str, obj_id: str):
        frame = self.tab_frames.get(obj_type)
        if frame and hasattr(frame, "remove_object"):
            frame.remove_object(obj_id)

    def notify_prompt_created(self, name: str):
        frame1 = self.tab_frames.get("prompts")
        if frame1 and hasattr(frame1, "add_prompt"):
            frame1.add_prompt(name)
        frame2 = self.tab_frames.get("translator_prompts")
        if frame2 and hasattr(frame2, "add_prompt"):
            frame2.add_prompt(name)

    def notify_prompt_updated(self, name: str):
        frame1 = self.tab_frames.get("prompts")
        if frame1 and hasattr(frame1, "update_prompt"):
            frame1.update_prompt(name)
        frame2 = self.tab_frames.get("translator_prompts")
        if frame2 and hasattr(frame2, "update_prompt"):
            frame2.update_prompt(name)

    def notify_prompt_deleted(self, name: str):
        frame1 = self.tab_frames.get("prompts")
        if frame1 and hasattr(frame1, "remove_prompt"):
            frame1.remove_prompt(name)
        frame2 = self.tab_frames.get("translator_prompts")
        if frame2 and hasattr(frame2, "remove_prompt"):
            frame2.remove_prompt(name)