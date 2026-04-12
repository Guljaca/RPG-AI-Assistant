# ui_utils.py
import tkinter as tk

def add_context_menu(widget):
    """Добавляет контекстное меню (копировать/вставить/вырезать) для виджета."""
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
    if hasattr(widget, 'tag_add'):  # для текстовых виджетов
        widget.bind("<Control-a>", lambda e: widget.tag_add(tk.SEL, "1.0", tk.END))
        widget.bind("<Control-A>", lambda e: widget.tag_add(tk.SEL, "1.0", tk.END))
    else:
        widget.bind("<Control-a>", lambda e: widget.select_range(0, tk.END))
        widget.bind("<Control-A>", lambda e: widget.select_range(0, tk.END))