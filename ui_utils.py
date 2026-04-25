import tkinter as tk

def add_context_menu(widget):
    """Добавляет контекстное меню и горячие клавиши (копировать/вставить/вырезать) с поддержкой русской раскладки."""

    # --- Функции для работы с буфером обмена ---
    def copy_to_clipboard(event=None):
        try:
            selected = widget.selection_get()
            widget.clipboard_clear()
            widget.clipboard_append(selected)
        except tk.TclError:
            pass
        return "break"

    def cut_to_clipboard(event=None):
        try:
            selected = widget.selection_get()
            widget.clipboard_clear()
            widget.clipboard_append(selected)
            widget.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        return "break"

    def paste_from_clipboard(event=None):
        try:
            text = widget.clipboard_get()
            widget.insert(tk.INSERT, text)
        except tk.TclError:
            pass
        return "break"

    def select_all(event=None):
        if hasattr(widget, 'tag_add'):
            widget.tag_add(tk.SEL, "1.0", tk.END)
        else:
            widget.select_range(0, tk.END)
        return "break"

    # --- Универсальный обработчик для Ctrl+любая клавиша ---
    def on_ctrl_key(event):
        # Проверяем, зажат ли Ctrl
        if event.state & 0x4:
            # keycode 67 — это клавиша 'C/С', 86 — 'V/М', 88 — 'X/Ч', 65 — 'A/Ф'
            if event.keycode == 67:    # Клавиша C
                copy_to_clipboard()
            elif event.keycode == 88:  # Клавиша X
                cut_to_clipboard()
            elif event.keycode == 86:  # Клавиша V
                paste_from_clipboard()
            elif event.keycode == 65:  # Клавиша A
                select_all()
            return "break"

    # Привязываем наш обработчик ко всем нажатиям клавиш с зажатым Ctrl
    widget.bind('<Control-KeyPress>', on_ctrl_key)

    # --- Контекстное меню (правой кнопкой мыши) ---
    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label="Вырезать", command=cut_to_clipboard)
    menu.add_command(label="Копировать", command=copy_to_clipboard)
    menu.add_command(label="Вставить", command=paste_from_clipboard)

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

    widget.bind("<Button-3>", show_menu)  # Для Windows/Linux
    widget.bind("<Button-2>", show_menu)  # Для macOS