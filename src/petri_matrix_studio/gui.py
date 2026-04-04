from __future__ import annotations

import math
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

from .coverage import CoverageTree, CoverageTreeBuilder, OMEGA, format_marking
from .engine import PetriMatrixEngine
from .io import load_json, save_json
from .model import Arc, PetriNet, Place, Transition
from . import analysis

PLACE_RADIUS = 26
TRANSITION_W = 18
TRANSITION_H = 64

# ─── Design Tokens ────────────────────────────────────────────────────────────
BG_BASE      = "#0d1117"   # deepest background
BG_SURFACE   = "#161b22"   # panels / cards
BG_RAISED    = "#21262d"   # inputs / secondary surfaces
BG_HOVER     = "#2d333b"   # hover state
BORDER       = "#30363d"   # subtle borders

ACCENT       = "#58a6ff"   # electric blue – primary
ACCENT_DARK  = "#1f6feb"   # darker shade for pressed state
ACCENT_GLOW  = "#388bfd"
GREEN        = "#3fb950"   # enabled transitions
GREEN_DIM    = "#238636"
RED          = "#f85149"   # danger / dead
AMBER        = "#d29922"   # warnings
PURPLE       = "#bc8cff"   # arcs / weights
CYAN         = "#39c5cf"   # coverage / analysis

TEXT_PRIMARY  = "#e6edf3"
TEXT_SECONDARY = "#8b949e"
TEXT_MUTED    = "#484f58"

FONT_MONO  = ("Consolas", 10)
FONT_UI    = ("Segoe UI", 10)
FONT_UI_SM = ("Segoe UI", 9)
FONT_UI_B  = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 13, "bold")
FONT_H2    = ("Segoe UI", 11, "bold")


# ─── Reusable Widget Helpers ──────────────────────────────────────────────────

class ModernButton(tk.Button):
    """Flat button with hover / press feedback."""

    STYLES = {
        "primary": {
            "normal":   {"bg": ACCENT_DARK,  "fg": TEXT_PRIMARY,   "relief": "flat"},
            "hover":    {"bg": ACCENT,        "fg": "#ffffff",      "relief": "flat"},
            "active":   {"bg": ACCENT_GLOW,   "fg": "#ffffff",      "relief": "flat"},
        },
        "secondary": {
            "normal":   {"bg": BG_RAISED,     "fg": TEXT_SECONDARY, "relief": "flat"},
            "hover":    {"bg": BG_HOVER,      "fg": TEXT_PRIMARY,   "relief": "flat"},
            "active":   {"bg": BORDER,        "fg": TEXT_PRIMARY,   "relief": "flat"},
        },
        "danger": {
            "normal":   {"bg": "#3d1a1a",     "fg": RED,            "relief": "flat"},
            "hover":    {"bg": "#5a1f1f",     "fg": "#ff7b72",      "relief": "flat"},
            "active":   {"bg": "#7a2828",     "fg": "#ffa198",      "relief": "flat"},
        },
        "success": {
            "normal":   {"bg": "#122118",     "fg": GREEN,          "relief": "flat"},
            "hover":    {"bg": "#1a3520",     "fg": "#56d364",      "relief": "flat"},
            "active":   {"bg": "#254a2c",     "fg": "#7ee787",      "relief": "flat"},
        },
        "ghost": {
            "normal":   {"bg": BG_BASE,       "fg": TEXT_SECONDARY, "relief": "flat"},
            "hover":    {"bg": BG_RAISED,     "fg": TEXT_PRIMARY,   "relief": "flat"},
            "active":   {"bg": BG_HOVER,      "fg": TEXT_PRIMARY,   "relief": "flat"},
        },
        "tool": {
            "normal":   {"bg": BG_RAISED,     "fg": TEXT_SECONDARY, "relief": "flat"},
            "hover":    {"bg": BG_HOVER,      "fg": ACCENT,         "relief": "flat"},
            "active":   {"bg": ACCENT_DARK,   "fg": TEXT_PRIMARY,   "relief": "flat"},
        },
    }

    def __init__(self, parent, text="", style="secondary", command=None,
                 width=None, padx=14, pady=7, font=FONT_UI, **kw):
        s = self.STYLES[style]["normal"]
        super().__init__(
            parent,
            text=text,
            command=command,
            bg=s["bg"],
            fg=s["fg"],
            relief=s["relief"],
            bd=0,
            font=font,
            activebackground=self.STYLES[style]["active"]["bg"],
            activeforeground=self.STYLES[style]["active"]["fg"],
            cursor="hand2",
            padx=padx,
            pady=pady,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            **kw,
        )
        if width:
            self.config(width=width)
        self._style = style
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _e):
        s = self.STYLES[self._style]["hover"]
        self.config(bg=s["bg"], fg=s["fg"], highlightbackground=ACCENT)

    def _on_leave(self, _e):
        s = self.STYLES[self._style]["normal"]
        self.config(bg=s["bg"], fg=s["fg"], highlightbackground=BORDER)


class ToolRadio(tk.Radiobutton):
    """Custom radio button styled as an icon-like tool pill."""

    def __init__(self, parent, text, value, variable, icon="", **kw):
        display = f"{icon}  {text}" if icon else text
        super().__init__(
            parent,
            text=display,
            value=value,
            variable=variable,
            indicatoron=False,
            bg=BG_RAISED,
            fg=TEXT_SECONDARY,
            selectcolor=ACCENT_DARK,
            activebackground=BG_HOVER,
            activeforeground=TEXT_PRIMARY,
            relief="flat",
            bd=0,
            font=FONT_UI_B,
            padx=12,
            pady=8,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=BORDER,
            **kw,
        )
        self.bind("<Enter>", lambda _e: self.config(fg=ACCENT, highlightbackground=ACCENT))
        self.bind("<Leave>", self._on_leave)
        variable.trace_add("write", lambda *_: self._sync())
        self._var = variable
        self._val = value

    def _sync(self):
        if self._var.get() == self._val:
            self.config(fg=TEXT_PRIMARY, bg=ACCENT_DARK, highlightbackground=ACCENT)
        else:
            self.config(fg=TEXT_SECONDARY, bg=BG_RAISED, highlightbackground=BORDER)

    def _on_leave(self, _e):
        self._sync()


class SectionLabel(tk.Frame):
    """Horizontal rule with a label — separates sidebar sections."""

    def __init__(self, parent, text, **kw):
        super().__init__(parent, bg=BG_SURFACE, **kw)
        tk.Label(self, text=text.upper(), bg=BG_SURFACE, fg=ACCENT,
                 font=("Segoe UI", 8, "bold"), padx=0, pady=0).pack(anchor="w")
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", pady=(3, 6))


class DarkEntry(tk.Entry):
    def __init__(self, parent, textvariable=None, **kw):
        super().__init__(
            parent,
            textvariable=textvariable,
            bg=BG_RAISED,
            fg=TEXT_PRIMARY,
            insertbackground=ACCENT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            font=FONT_UI,
            **kw,
        )


class DarkSpinbox(tk.Spinbox):
    def __init__(self, parent, **kw):
        super().__init__(
            parent,
            bg=BG_RAISED,
            fg=TEXT_PRIMARY,
            insertbackground=ACCENT,
            buttonbackground=BG_HOVER,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            font=FONT_MONO,
            **kw,
        )


# ─── Main Application ─────────────────────────────────────────────────────────

@dataclass
class Selection:
    kind: str | None = None
    item_id: str | None = None


class PetriStudioApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Petri Matrix Studio")
        self.geometry("1400x860")
        self.minsize(1100, 700)
        self.configure(bg=BG_BASE)

        self.net = PetriNet(name="Nueva red")
        self.selection = Selection()
        self.current_tool = tk.StringVar(value="select")
        self.status_var = tk.StringVar(value="●  Listo")
        self.name_var = tk.StringVar(value=self.net.name)
        self.arc_weight_var = tk.IntVar(value=1)
        self.place_tokens_var = tk.IntVar(value=0)
        self.label_var = tk.StringVar(value="")
        self.pending_arc_source: str | None = None
        self.drag_node_id: str | None = None
        self.drag_offset = (0.0, 0.0)
        self.file_path: Path | None = None

        self._build_layout()
        self.redraw()

    # ─── Layout ───────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = tk.Frame(self, bg=BG_SURFACE, bd=0)
        toolbar.pack(fill="x", side="top")

        # Brand
        brand = tk.Frame(toolbar, bg=ACCENT_DARK, padx=18)
        brand.pack(side="left", fill="y")
        tk.Label(brand, text="⬡ PETRI", bg=ACCENT_DARK, fg="#ffffff",
                 font=("Segoe UI", 13, "bold")).pack(side="left", pady=10)
        tk.Label(brand, text=" STUDIO", bg=ACCENT_DARK, fg=CYAN,
                 font=("Segoe UI", 13, "bold")).pack(side="left", pady=10)

        # Thin accent line at bottom of toolbar
        tk.Frame(toolbar, bg=ACCENT, height=2).place(relx=0, rely=1.0, relwidth=1,
                                                      anchor="sw")

        # Tool group
        tool_frame = tk.Frame(toolbar, bg=BG_SURFACE, padx=12, pady=8)
        tool_frame.pack(side="left", fill="y")

        tk.Label(tool_frame, text="TOOL", bg=BG_SURFACE, fg=TEXT_MUTED,
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 8))

        icons = {"select": "↖", "place": "◯", "transition": "▬", "arc": "→"}
        labels = {"select": "Seleccionar", "place": "Lugar",
                  "transition": "Transición", "arc": "Arco"}
        for tool in ("select", "place", "transition", "arc"):
            ToolRadio(tool_frame, text=labels[tool], value=tool,
                      variable=self.current_tool, icon=icons[tool]).pack(
                side="left", padx=3)

        # Separator
        tk.Frame(toolbar, bg=BORDER, width=1).pack(side="left", fill="y",
                                                    padx=10, pady=6)

        # File actions
        file_frame = tk.Frame(toolbar, bg=BG_SURFACE, pady=8)
        file_frame.pack(side="left", fill="y")
        ModernButton(file_frame, "＋ Nueva",        style="ghost",   command=self.new_net).pack(side="left", padx=3)
        ModernButton(file_frame, "⇡ Abrir",         style="ghost",   command=self.open_json).pack(side="left", padx=3)
        ModernButton(file_frame, "⇣ Guardar",       style="ghost",   command=self.save_json_dialog).pack(side="left", padx=3)
        ModernButton(file_frame, "✕ Eliminar",      style="danger",  command=self.delete_selection).pack(side="left", padx=3)

        # Separator
        tk.Frame(toolbar, bg=BORDER, width=1).pack(side="left", fill="y",
                                                    padx=10, pady=6)

        # Analysis dropdown (custom)
        analysis_frame = tk.Frame(toolbar, bg=BG_SURFACE, pady=8)
        analysis_frame.pack(side="left", fill="y")

        analysis_menu_btn = ModernButton(
            analysis_frame, "⚗ Análisis ▾", style="primary",
            command=lambda: self._show_analysis_menu(analysis_menu_btn))
        analysis_menu_btn.pack(side="left", padx=3)

        ModernButton(analysis_frame, "⌾ Árbol cobertura", style="tool",
                     command=self.show_coverage_tree).pack(side="left", padx=3)
        ModernButton(analysis_frame, "⟳ Recentrar", style="ghost",
                     command=self.redraw).pack(side="left", padx=3)

        # ── Main area ────────────────────────────────────────────────────────
        main = tk.Frame(self, bg=BG_BASE)
        main.pack(fill="both", expand=True)

        # Canvas
        canvas_frame = tk.Frame(main, bg=BG_BASE, padx=10, pady=10)
        canvas_frame.pack(side="left", fill="both", expand=True)

        self.canvas = tk.Canvas(canvas_frame, bg="#0a0f14", highlightthickness=0,
                                cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>",       self.on_left_click)
        self.canvas.bind("<B1-Motion>",      self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        # ── Sidebar ──────────────────────────────────────────────────────────
        sidebar = tk.Frame(main, bg=BG_SURFACE, width=290, bd=0)
        sidebar.pack(side="right", fill="y")
        sidebar.pack_propagate(False)

        # Left border accent
        tk.Frame(sidebar, bg=BORDER, width=1).pack(side="left", fill="y")

        inner = tk.Frame(sidebar, bg=BG_SURFACE, padx=16, pady=16)
        inner.pack(fill="both", expand=True, side="left")

        # Network name
        SectionLabel(inner, "Red").pack(fill="x")
        DarkEntry(inner, textvariable=self.name_var).pack(fill="x", pady=(0, 6))
        ModernButton(inner, "Aplicar nombre", style="secondary",
                     command=self.apply_name).pack(fill="x", pady=(0, 12))

        # Simulation
        SectionLabel(inner, "Simulación").pack(fill="x")
        ModernButton(inner, "↺  Actualizar habilitadas",    style="tool",
                     command=self.redraw).pack(fill="x", pady=2)
        ModernButton(inner, "⊘  Resetear marcado a cero",   style="danger",
                     command=self.reset_marking).pack(fill="x", pady=2)

        tk.Frame(inner, bg=BG_SURFACE, height=12).pack()

        # Selection properties
        SectionLabel(inner, "Selección").pack(fill="x")

        tk.Label(inner, text="Etiqueta", bg=BG_SURFACE, fg=TEXT_SECONDARY,
                 font=FONT_UI_SM).pack(anchor="w")
        self.label_entry = DarkEntry(inner, textvariable=self.label_var)
        self.label_entry.pack(fill="x", pady=(2, 10))

        props_row = tk.Frame(inner, bg=BG_SURFACE)
        props_row.pack(fill="x", pady=(0, 10))

        left_col = tk.Frame(props_row, bg=BG_SURFACE)
        left_col.pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Label(left_col, text="Tokens", bg=BG_SURFACE, fg=TEXT_SECONDARY,
                 font=FONT_UI_SM).pack(anchor="w")
        self.tokens_spin = DarkSpinbox(left_col, from_=0, to=9999,
                                       textvariable=self.place_tokens_var, width=8)
        self.tokens_spin.pack(anchor="w", pady=(2, 0))

        right_col = tk.Frame(props_row, bg=BG_SURFACE)
        right_col.pack(side="left", fill="x", expand=True)
        tk.Label(right_col, text="Peso arco", bg=BG_SURFACE, fg=TEXT_SECONDARY,
                 font=FONT_UI_SM).pack(anchor="w")
        self.arc_spin = DarkSpinbox(right_col, from_=1, to=999,
                                    textvariable=self.arc_weight_var, width=8)
        self.arc_spin.pack(anchor="w", pady=(2, 0))

        ModernButton(inner, "✓  Aplicar cambios", style="primary",
                     command=self.apply_selection_changes).pack(fill="x", pady=(4, 2))

        token_row = tk.Frame(inner, bg=BG_SURFACE)
        token_row.pack(fill="x", pady=(0, 4))
        ModernButton(token_row, "＋ Token", style="success",
                     command=lambda: self.bump_tokens(1)).pack(side="left", expand=True,
                                                               fill="x", padx=(0, 3))
        ModernButton(token_row, "－ Token", style="danger",
                     command=lambda: self.bump_tokens(-1)).pack(side="left", expand=True,
                                                                fill="x")

        # Spacer
        tk.Frame(inner, bg=BG_SURFACE).pack(fill="both", expand=True)

        # ── Status bar ───────────────────────────────────────────────────────
        status_bar = tk.Frame(self, bg="#0a0f14", pady=5, padx=14)
        status_bar.pack(fill="x", side="bottom")
        tk.Frame(status_bar, bg=ACCENT, width=3, height=16).pack(side="left",
                                                                   padx=(0, 8))
        tk.Label(status_bar, textvariable=self.status_var, bg="#0a0f14",
                 fg=TEXT_SECONDARY, font=FONT_UI_SM, anchor="w").pack(side="left")

        version = tk.Label(status_bar, text="v2.0 · Matrix Engine",
                           bg="#0a0f14", fg=TEXT_MUTED, font=("Segoe UI", 8))
        version.pack(side="right")

    # ─── Analysis Popup Menu ──────────────────────────────────────────────────

    def _show_analysis_menu(self, btn: tk.Widget) -> None:
        menu = tk.Menu(self, tearoff=0,
                       bg=BG_SURFACE, fg=TEXT_PRIMARY,
                       activebackground=ACCENT_DARK, activeforeground=TEXT_PRIMARY,
                       relief="flat", bd=1,
                       font=FONT_UI)
        menu.add_command(label="  ⇢  Verificar secuencia",   command=self.verify_sequence_dialog)
        menu.add_command(label="  ◈  Alcanzabilidad exacta",  command=self.reachability_dialog)
        menu.add_command(label="  ⊆  Cobertura",             command=self.coverage_dialog)
        menu.add_separator()
        menu.add_command(label="  ⛔  Bloqueo (deadlock)",    command=self.check_deadlock)
        menu.add_command(label="  ⚡  Cuellos de botella",    command=self.check_bottlenecks)
        menu.add_separator()
        menu.add_command(label="  ☠  Transiciones muertas",  command=self.check_liveness)
        menu.add_command(label="  ∞  Acotación",             command=self.check_boundedness)

        x = btn.winfo_rootx()
        y = btn.winfo_rooty() + btn.winfo_height() + 2
        menu.tk_popup(x, y)

    # ─── Dialog helper ────────────────────────────────────────────────────────

    def _dark_dialog(self, title: str, width=420, height=180) -> tk.Toplevel:
        d = tk.Toplevel(self)
        d.title(title)
        d.geometry(f"{width}x{height}")
        d.configure(bg=BG_SURFACE)
        d.resizable(False, False)
        d.grab_set()
        # Top accent strip
        tk.Frame(d, bg=ACCENT, height=3).pack(fill="x")
        return d

    def _dialog_label(self, parent, text):
        tk.Label(parent, text=text, bg=BG_SURFACE, fg=TEXT_SECONDARY,
                 font=FONT_UI, wraplength=380, justify="left").pack(
            anchor="w", padx=20, pady=(14, 4))

    def _dialog_entry(self, parent) -> DarkEntry:
        e = DarkEntry(parent, width=48)
        e.pack(padx=20, pady=(0, 14), fill="x")
        return e

    def _msgbox(self, title, msg, kind="info"):
        d = self._dark_dialog(title, width=420, height=160)
        icon = {"info": "ℹ", "warn": "⚠", "error": "✕"}.get(kind, "ℹ")
        color = {"info": ACCENT, "warn": AMBER, "error": RED}.get(kind, ACCENT)
        row = tk.Frame(d, bg=BG_SURFACE)
        row.pack(fill="x", padx=20, pady=14)
        tk.Label(row, text=icon, bg=BG_SURFACE, fg=color,
                 font=("Segoe UI", 24)).pack(side="left", padx=(0, 12))
        tk.Label(row, text=msg, bg=BG_SURFACE, fg=TEXT_PRIMARY,
                 font=FONT_UI, wraplength=320, justify="left").pack(side="left")
        ModernButton(d, "  OK  ", style="primary", command=d.destroy,
                     pady=6).pack(pady=(0, 16))

    # ─── Core methods (unchanged logic, dark messagebox wrapper) ─────────────

    def apply_name(self) -> None:
        self.net.name = self.name_var.get().strip() or "Nueva red"
        self.status(f"Nombre actualizado: {self.net.name}")

    def new_net(self) -> None:
        self.net = PetriNet(name="Nueva red")
        self.file_path = None
        self.name_var.set(self.net.name)
        self.selection = Selection()
        self.pending_arc_source = None
        self.redraw()
        self.status("Nueva red creada")

    def open_json(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Petri JSON", "*.json")])
        if not path:
            return
        try:
            self.net = load_json(path)
            self.file_path = Path(path)
            self.name_var.set(self.net.name)
            self.selection = Selection()
            self.pending_arc_source = None
            self.redraw()
            self.status(f"Red cargada · {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("Error al abrir JSON", str(exc))

    def save_json_dialog(self) -> None:
        target = self.file_path
        if target is None:
            path = filedialog.asksaveasfilename(
                defaultextension=".json", filetypes=[("Petri JSON", "*.json")])
            if not path:
                return
            target = Path(path)
        try:
            self.apply_name()
            save_json(self.net, target)
            self.file_path = target
            self.status(f"Guardado · {target.name}")
        except Exception as exc:
            messagebox.showerror("Error al guardar JSON", str(exc))

    def delete_selection(self) -> None:
        if self.selection.kind == "arc" and self.selection.item_id:
            source, target = self.selection.item_id.split("->", 1)
            self.net.remove_arc(source, target)
            self.selection = Selection()
            self.redraw()
            self.status("Arco eliminado")
        elif self.selection.kind in {"place", "transition"} and self.selection.item_id:
            self.net.remove_node(self.selection.item_id)
            self.selection = Selection()
            self.redraw()
            self.status("Nodo eliminado")

    def reset_marking(self) -> None:
        for p in self.net.places:
            p.tokens = 0
        self.redraw()
        self.status("Marcado reiniciado a cero")

    def apply_selection_changes(self) -> None:
        if self.selection.kind == "place" and self.selection.item_id:
            place = self.net.get_place(self.selection.item_id)
            if place:
                place.label = self.label_var.get().strip() or place.id
                place.tokens = max(0, int(self.place_tokens_var.get()))
                self.redraw()
                self.status(f"Lugar {place.id} actualizado")
        elif self.selection.kind == "transition" and self.selection.item_id:
            transition = self.net.get_transition(self.selection.item_id)
            if transition:
                transition.label = self.label_var.get().strip() or transition.id
                self.redraw()
                self.status(f"Transición {transition.id} actualizada")
        elif self.selection.kind == "arc" and self.selection.item_id:
            source, target = self.selection.item_id.split("->", 1)
            arc = self.net.get_arc(source, target)
            if arc:
                arc.weight = max(1, int(self.arc_weight_var.get()))
                self.redraw()
                self.status("Peso del arco actualizado")

    def bump_tokens(self, delta: int) -> None:
        if self.selection.kind == "place" and self.selection.item_id:
            place = self.net.get_place(self.selection.item_id)
            if place:
                place.tokens = max(0, place.tokens + delta)
                self.place_tokens_var.set(place.tokens)
                self.redraw()

    def status(self, msg: str) -> None:
        self.status_var.set(f"●  {msg}")

    def show_coverage_tree(self) -> None:
        try:
            tree = CoverageTreeBuilder(self.net).build()
        except Exception as exc:
            messagebox.showerror("Error al construir el árbol de cobertura", str(exc))
            return
        CoverageTreeWindow(self, self.net.name, tree)
        self.status("Árbol de cobertura construido")

    def engine(self) -> PetriMatrixEngine:
        return PetriMatrixEngine(self.net)

    # ─── Analysis dialogs ─────────────────────────────────────────────────────

    def verify_sequence_dialog(self) -> None:
        d = self._dark_dialog("Verificar secuencia", width=440, height=180)
        self._dialog_label(d, "Secuencia de transiciones  (ej: T1, T2, T3)")
        entry = self._dialog_entry(d)

        def do_verify():
            seq_text = entry.get().strip()
            if not seq_text:
                return
            seq = [t.strip() for t in seq_text.split(",") if t.strip()]
            ok, fail_step, fail_marking = analysis.verify_sequence(self.net, seq)
            d.destroy()
            if ok:
                self._msgbox("Verificación", "La secuencia es válida ✓", "info")
            else:
                self._msgbox("Secuencia inválida",
                             f"Fallo en el paso {fail_step+1}  ({seq[fail_step]})\n"
                             f"Marcado: {fail_marking}", "error")

        ModernButton(d, "Verificar →", style="primary", command=do_verify,
                     pady=6).pack(padx=20, anchor="e")

    def reachability_dialog(self) -> None:
        d = self._dark_dialog("Alcanzabilidad exacta", width=460, height=200)
        self._dialog_label(d, "Marcación objetivo  (ej: P1:3, P2:0, P3:1)")
        entry = self._dialog_entry(d)

        def do_check():
            text = entry.get().strip()
            target = {}
            try:
                for part in text.split(","):
                    if ":" not in part:
                        raise ValueError
                    pid, val = part.split(":")
                    target[pid.strip()] = int(val.strip())
            except Exception:
                self._msgbox("Formato inválido", "Use el formato:  P1:3, P2:0", "error")
                return
            ok, path = analysis.exact_reachability(self.net, target)
            d.destroy()
            if ok is True:
                self._msgbox("Alcanzabilidad",
                             f"Alcanzable ✓\nSecuencia: {' → '.join(path)}", "info")
            elif ok is False:
                self._msgbox("Alcanzabilidad",
                             "No es alcanzable (espacio acotado explorado).", "warn")
            else:
                self._msgbox("Alcanzabilidad",
                             "No determinable (red no acotada, límite alcanzado).", "warn")

        ModernButton(d, "Verificar →", style="primary", command=do_check,
                     pady=6).pack(padx=20, anchor="e")

    def coverage_dialog(self) -> None:
        d = self._dark_dialog("Cobertura", width=460, height=200)
        self._dialog_label(d, "Marcación a cubrir  (ej: P1:2, P2:0)")
        entry = self._dialog_entry(d)

        def do_check():
            text = entry.get().strip()
            target = {}
            try:
                for part in text.split(","):
                    if ":" not in part:
                        raise ValueError
                    pid, val = part.split(":")
                    target[pid.strip()] = int(val.strip())
            except Exception:
                self._msgbox("Formato inválido", "Use el formato:  P1:2, P2:0", "error")
                return
            result = analysis.coverability(self.net, target)
            d.destroy()
            if result:
                self._msgbox("Cobertura", "La marcación es cubrible ✓\n(existe marcación ≥ objetivo)", "info")
            else:
                self._msgbox("Cobertura", "La marcación NO es cubrible.", "warn")

        ModernButton(d, "Verificar →", style="primary", command=do_check,
                     pady=6).pack(padx=20, anchor="e")

    def check_deadlock(self) -> None:
        engine = self.engine()
        if analysis.detect_deadlock(engine):
            self._msgbox("Bloqueo detectado",
                         "La red está bloqueada.\nNo hay transiciones habilitadas.", "error")
        else:
            self._msgbox("Sin bloqueo",
                         "Hay transiciones habilitadas.\nNo existe deadlock.", "info")

    def check_bottlenecks(self) -> None:
        bottlenecks = analysis.detect_bottlenecks(self.net)
        if bottlenecks:
            lines = "\n".join(f"  {pid}  →  {t} tokens" for pid, t in bottlenecks)
            self._msgbox("Cuellos de botella",
                         f"Lugares con alta acumulación:\n{lines}", "warn")
        else:
            self._msgbox("Cuellos de botella",
                         "No se detectaron cuellos de botella significativos.", "info")

    def check_liveness(self) -> None:
        dead = analysis.detect_dead_transitions(self.net)
        if dead:
            self._msgbox("Transiciones muertas",
                         f"Nunca se disparan:\n  {', '.join(dead)}", "warn")
        else:
            self._msgbox("Vivacidad",
                         "Todas las transiciones son potencialmente vivas.", "info")

    def check_boundedness(self) -> None:
        bounded, unbounded = analysis.boundedness(self.net)
        if bounded:
            self._msgbox("Red acotada",
                         "La red es acotada ✓\nNo hay crecimiento infinito de tokens.", "info")
        else:
            self._msgbox("Red no acotada",
                         f"Lugares no acotados:\n  {', '.join(unbounded)}", "warn")

    # ─── Canvas interaction ───────────────────────────────────────────────────

    def on_left_click(self, event: tk.Event) -> None:
        x, y = float(event.x), float(event.y)
        tool = self.current_tool.get()
        hit = self.hit_test(x, y)
        if tool == "place":       self.add_place(x, y);           return
        if tool == "transition":  self.add_transition(x, y);      return
        if tool == "arc":         self.handle_arc_tool(hit);       return
        self.handle_select_tool(hit, x, y)

    def on_drag(self, event: tk.Event) -> None:
        if self.current_tool.get() != "select" or not self.drag_node_id:
            return
        node = self.net.get_node(self.drag_node_id)
        if not node:
            return
        node.x = event.x - self.drag_offset[0]
        node.y = event.y - self.drag_offset[1]
        self.redraw()

    def on_release(self, _event: tk.Event) -> None:
        self.drag_node_id = None

    def add_place(self, x: float, y: float) -> None:
        pid = self.net.next_place_id()
        self.net.places.append(Place(id=pid, label=pid, x=x, y=y, tokens=0))
        self.selection = Selection(kind="place", item_id=pid)
        self.refresh_property_panel()
        self.redraw()
        self.status(f"Lugar {pid} agregado")

    def add_transition(self, x: float, y: float) -> None:
        tid = self.net.next_transition_id()
        self.net.transitions.append(Transition(id=tid, label=tid, x=x, y=y))
        self.selection = Selection(kind="transition", item_id=tid)
        self.refresh_property_panel()
        self.redraw()
        self.status(f"Transición {tid} agregada")

    def handle_arc_tool(self, hit) -> None:
        if not hit:
            self.pending_arc_source = None
            self.status("Seleccione origen y luego destino del arco")
            return
        kind, node_id = hit
        if self.pending_arc_source is None:
            self.pending_arc_source = node_id
            self.status(f"Origen: {node_id}  →  ahora seleccione el destino")
            return
        source, target = self.pending_arc_source, node_id
        self.pending_arc_source = None
        if source == target:
            self.status("Un arco no puede conectar un nodo consigo mismo")
            return
        if self.net.node_kind(source) == self.net.node_kind(target):
            self.status("Solo se permiten arcos lugar↔transición")
            return
        self.net.upsert_arc(source, target, weight=1)
        self.selection = Selection(kind="arc", item_id=f"{source}->{target}")
        self.refresh_property_panel()
        self.redraw()
        self.status(f"Arco  {source} → {target}  creado")

    def handle_select_tool(self, hit, x: float, y: float) -> None:
        if not hit:
            self.selection = Selection()
            self.drag_node_id = None
            self.refresh_property_panel()
            self.redraw()
            return
        kind, item_id = hit
        self.selection = Selection(kind=kind, item_id=item_id)
        self.refresh_property_panel()
        if kind == "transition":
            if self.engine().is_enabled(item_id):
                try:
                    self.engine().fire(item_id)
                    self.status(f"⚡  Disparó  {item_id}")
                except Exception as exc:
                    messagebox.showerror("Error al disparar", str(exc))
        elif kind in {"place", "transition"}:
            node = self.net.get_node(item_id)
            if node:
                self.drag_node_id = item_id
                self.drag_offset = (x - node.x, y - node.y)
        self.redraw()

    def hit_test(self, x: float, y: float):
        for place in reversed(self.net.places):
            if (x - place.x) ** 2 + (y - place.y) ** 2 <= PLACE_RADIUS**2:
                return ("place", place.id)
        for transition in reversed(self.net.transitions):
            if (transition.x - TRANSITION_W/2 <= x <= transition.x + TRANSITION_W/2
                    and transition.y - TRANSITION_H/2 <= y <= transition.y + TRANSITION_H/2):
                return ("transition", transition.id)
        for arc in self.net.arcs:
            if self.hit_test_arc(arc, x, y):
                return ("arc", f"{arc.source}->{arc.target}")
        return None

    def hit_test_arc(self, arc: Arc, x: float, y: float) -> bool:
        src = self.net.get_node(arc.source)
        dst = self.net.get_node(arc.target)
        if not src or not dst:
            return False
        mx, my = (src.x + dst.x) / 2, (src.y + dst.y) / 2
        return (x - mx) ** 2 + (y - my) ** 2 < 14**2

    def refresh_property_panel(self) -> None:
        self.label_var.set("")
        self.place_tokens_var.set(0)
        self.arc_weight_var.set(1)
        if self.selection.kind == "place" and self.selection.item_id:
            place = self.net.get_place(self.selection.item_id)
            if place:
                self.label_var.set(place.label)
                self.place_tokens_var.set(place.tokens)
        elif self.selection.kind == "transition" and self.selection.item_id:
            t = self.net.get_transition(self.selection.item_id)
            if t:
                self.label_var.set(t.label)
        elif self.selection.kind == "arc" and self.selection.item_id:
            source, target = self.selection.item_id.split("->", 1)
            arc = self.net.get_arc(source, target)
            if arc:
                self.arc_weight_var.set(arc.weight)

    # ─── Drawing ──────────────────────────────────────────────────────────────

    def redraw(self) -> None:
        self.canvas.delete("all")
        self.title(f"Petri Matrix Studio  ·  {self.net.name}")

        # Subtle grid
        cw = self.canvas.winfo_width()  or 1000
        ch = self.canvas.winfo_height() or 700
        step = 40
        for gx in range(0, cw, step):
            self.canvas.create_line(gx, 0, gx, ch, fill="#0f1822", width=1)
        for gy in range(0, ch, step):
            self.canvas.create_line(0, gy, cw, gy, fill="#0f1822", width=1)

        # Net label
        self.canvas.create_text(18, 18, anchor="nw", text=self.net.name,
                                font=FONT_TITLE, fill=TEXT_SECONDARY)

        enabled = set(self.engine().enabled_transition_ids()) if self.net.transitions else set()

        for arc in self.net.arcs:
            self.draw_arc(arc)
        for place in self.net.places:
            self.draw_place(place)
        for transition in self.net.transitions:
            self.draw_transition(transition, transition.id in enabled)

        if self.pending_arc_source:
            node = self.net.get_node(self.pending_arc_source)
            if node:
                for r in (8, 14, 20):
                    self.canvas.create_oval(node.x-r, node.y-r, node.x+r, node.y+r,
                                            outline=ACCENT, width=1)

    def draw_place(self, place: Place) -> None:
        selected = self.selection.kind == "place" and self.selection.item_id == place.id
        outline = ACCENT if selected else "#3d4f63"
        width   = 3     if selected else 2
        glow_r  = PLACE_RADIUS + 7

        if selected:
            self.canvas.create_oval(
                place.x - glow_r, place.y - glow_r,
                place.x + glow_r, place.y + glow_r,
                outline=ACCENT_DARK, width=6, dash=(2, 4))

        self.canvas.create_oval(
            place.x - PLACE_RADIUS, place.y - PLACE_RADIUS,
            place.x + PLACE_RADIUS, place.y + PLACE_RADIUS,
            fill=BG_SURFACE, outline=outline, width=width)

        # Token dots or number
        if 0 < place.tokens <= 5:
            positions = {
                1: [(0, 0)],
                2: [(-7, 0), (7, 0)],
                3: [(-8, 5), (8, 5), (0, -7)],
                4: [(-7,-7),(7,-7),(-7,7),(7,7)],
                5: [(-9,-7),(9,-7),(0,0),(-9,7),(9,7)],
            }
            for dx, dy in positions[place.tokens]:
                self.canvas.create_oval(
                    place.x+dx-4, place.y+dy-4,
                    place.x+dx+4, place.y+dy+4,
                    fill=CYAN, outline="")
        else:
            tok_color = CYAN if place.tokens > 0 else TEXT_MUTED
            self.canvas.create_text(place.x, place.y, text=str(place.tokens),
                                    font=("Consolas", 12, "bold"), fill=tok_color)

        # Label above
        self.canvas.create_text(place.x, place.y - PLACE_RADIUS - 10,
                                text=place.label, font=FONT_UI_B, fill=TEXT_PRIMARY)

    def draw_transition(self, transition: Transition, enabled: bool) -> None:
        selected = (self.selection.kind == "transition"
                    and self.selection.item_id == transition.id)
        fill    = GREEN      if enabled  else "#1e2d3d"
        outline = ACCENT     if selected else ("#22593a" if enabled else "#2a3a4a")
        width   = 3          if selected else 2

        if enabled:
            # Glow effect
            for expand in (10, 6, 3):
                self.canvas.create_rectangle(
                    transition.x - TRANSITION_W/2 - expand,
                    transition.y - TRANSITION_H/2 - expand,
                    transition.x + TRANSITION_W/2 + expand,
                    transition.y + TRANSITION_H/2 + expand,
                    outline=GREEN_DIM, width=1)

        self.canvas.create_rectangle(
            transition.x - TRANSITION_W/2, transition.y - TRANSITION_H/2,
            transition.x + TRANSITION_W/2, transition.y + TRANSITION_H/2,
            fill=fill, outline=outline, width=width)

        self.canvas.create_text(
            transition.x, transition.y - TRANSITION_H/2 - 12,
            text=transition.label, font=FONT_UI_B, fill=TEXT_PRIMARY)

        if enabled:
            self.canvas.create_text(transition.x, transition.y,
                                    text="⚡", font=("Segoe UI", 10))

    def node_anchor(self, node_id: str, toward_x: float, toward_y: float):
        place = self.net.get_place(node_id)
        if place:
            dx, dy = toward_x - place.x, toward_y - place.y
            norm = math.hypot(dx, dy) or 1.0
            return place.x + PLACE_RADIUS*dx/norm, place.y + PLACE_RADIUS*dy/norm
        t = self.net.get_transition(node_id)
        if not t:
            return toward_x, toward_y
        dx, dy = toward_x - t.x, toward_y - t.y
        if abs(dx) > abs(dy):
            return (t.x + math.copysign(TRANSITION_W/2, dx),
                    t.y + dy*(TRANSITION_W/2)/(abs(dx) or 1.0))
        return (t.x + dx*(TRANSITION_H/2)/(abs(dy) or 1.0),
                t.y + math.copysign(TRANSITION_H/2, dy))

    def draw_arc(self, arc: Arc) -> None:
        src = self.net.get_node(arc.source)
        dst = self.net.get_node(arc.target)
        if not src or not dst:
            return
        reverse_exists = self.net.has_arc(arc.target, arc.source)
        sx, sy = self.node_anchor(arc.source, dst.x, dst.y)
        tx, ty = self.node_anchor(arc.target, src.x, src.y)
        selected = (self.selection.kind == "arc"
                    and self.selection.item_id == f"{arc.source}->{arc.target}")
        color = ACCENT if selected else "#3d5a80"
        width = 3      if selected else 2

        if reverse_exists:
            mx, my = (sx+tx)/2, (sy+ty)/2
            dx, dy = tx-sx, ty-sy
            norm = math.hypot(dx, dy) or 1.0
            ox, oy = -dy/norm*26, dx/norm*26
            self.canvas.create_line(sx, sy, mx+ox, my+oy, tx, ty,
                                    smooth=True, arrow=tk.LAST, width=width,
                                    fill=color, arrowshape=(10, 12, 4))
            lx, ly = mx+ox, my+oy
        else:
            self.canvas.create_line(sx, sy, tx, ty, arrow=tk.LAST, width=width,
                                    fill=color, arrowshape=(10, 12, 4))
            lx, ly = (sx+tx)/2, (sy+ty)/2

        if arc.weight > 1:
            # Badge background
            self.canvas.create_oval(lx-10, ly-18, lx+10, ly-2,
                                    fill=PURPLE, outline="")
            self.canvas.create_text(lx, ly-10, text=str(arc.weight),
                                    font=("Consolas", 9, "bold"), fill="#ffffff")


# ─── Entry point ──────────────────────────────────────────────────────────────

def run_app() -> None:
    app = PetriStudioApp()
    app.mainloop()


# ─── Coverage Tree Window ──────────────────────────────────────────────────────

class CoverageTreeWindow(tk.Toplevel):
    COLORS = {
        "frontier": "#7a4f0d",
        "terminal": "#5a1a1a",
        "duplicate": "#2d1f5a",
        "internal": "#0d2b42",
    }
    TEXT_COLORS = {
        "frontier": AMBER,
        "terminal": RED,
        "duplicate": PURPLE,
        "internal": CYAN,
    }

    def __init__(self, master: tk.Misc, net_name: str, tree: CoverageTree) -> None:
        super().__init__(master)
        self.title(f"Árbol de cobertura  ·  {net_name}")
        self.geometry("1200x760")
        self.configure(bg=BG_BASE)
        self.tree = tree

        # Header
        header = tk.Frame(self, bg=BG_SURFACE, pady=10, padx=16)
        header.pack(fill="x")
        tk.Frame(header, bg=ACCENT, width=4).pack(side="left", fill="y", padx=(0, 12))
        tk.Label(header, text="Árbol de Cobertura", bg=BG_SURFACE, fg=TEXT_PRIMARY,
                 font=FONT_TITLE).pack(side="left")
        tk.Label(header, text=net_name, bg=BG_SURFACE, fg=TEXT_SECONDARY,
                 font=FONT_UI).pack(side="left", padx=12)

        # Legend
        legend = tk.Frame(self, bg=BG_SURFACE, pady=8, padx=16)
        legend.pack(fill="x")
        tk.Label(legend, text="Tipos de nodo:", bg=BG_SURFACE, fg=TEXT_MUTED,
                 font=FONT_UI_SM).pack(side="left", padx=(0, 12))
        labels = [("frontier","Frontera"), ("terminal","Terminal"),
                  ("duplicate","Duplicado"), ("internal","Interno")]
        for kind, text in labels:
            chip = tk.Label(legend, text=f"  {text}  ",
                            bg=self.COLORS[kind], fg=self.TEXT_COLORS[kind],
                            font=FONT_UI_SM, relief="flat", padx=4, pady=3,
                            highlightthickness=1, highlightbackground=self.TEXT_COLORS[kind])
            chip.pack(side="left", padx=4)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Scrollable canvas
        container = tk.Frame(self, bg=BG_BASE)
        container.pack(fill="both", expand=True, padx=8, pady=8)
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(container, bg="#080d12", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ybar = ttk.Scrollbar(container, orient="vertical",   command=self.canvas.yview)
        xbar = ttk.Scrollbar(container, orient="horizontal", command=self.canvas.xview)
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        self.canvas.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)

        self._draw_tree()

    def _draw_tree(self) -> None:
        levels: dict[int, list[int]] = {}
        depth_map = self._compute_depths()
        for node_id, depth in depth_map.items():
            levels.setdefault(depth, []).append(node_id)

        x_gap = 230; y_gap = 160
        node_w = 148; node_h = 60
        margin_x = 90; margin_y = 70
        positions: dict[int, tuple[float, float]] = {}

        for depth in sorted(levels):
            for idx, node_id in enumerate(levels[depth]):
                positions[node_id] = (margin_x + idx*x_gap, margin_y + depth*y_gap)

        # Edges
        for node in self.tree.nodes.values():
            if node.parent_id is None:
                continue
            x1, y1 = positions[node.parent_id]
            x2, y2 = positions[node.node_id]
            self.canvas.create_line(x1, y1+node_h/2, x2, y2-node_h/2,
                                    arrow=tk.LAST, width=2, fill="#2a3f52",
                                    arrowshape=(10, 12, 4))
            if node.via_transition:
                self.canvas.create_text((x1+x2)/2+22, (y1+y2)/2-12,
                                        text=node.via_transition,
                                        font=FONT_UI_B, fill=ACCENT)

        # Nodes
        for node_id, node in self.tree.nodes.items():
            x, y = positions[node_id]
            fill    = self.COLORS.get(node.kind, BG_RAISED)
            txcolor = self.TEXT_COLORS.get(node.kind, TEXT_PRIMARY)

            # Glow border
            self.canvas.create_rectangle(x-node_w/2-2, y-node_h/2-2,
                                         x+node_w/2+2, y+node_h/2+2,
                                         fill="", outline=txcolor, width=1)
            self.canvas.create_rectangle(x-node_w/2, y-node_h/2,
                                         x+node_w/2, y+node_h/2,
                                         fill=fill, outline=txcolor, width=2)

            self.canvas.create_text(x, y-14,
                                    text=f"n{node.node_id}  ·  {node.kind.upper()}",
                                    font=("Segoe UI", 9, "bold"), fill=txcolor)
            self.canvas.create_text(x, y+6, text=format_marking(node.marking),
                                    font=("Consolas", 10), fill=TEXT_PRIMARY)
            if node.kind == "duplicate" and node.duplicate_of is not None:
                self.canvas.create_text(x, y+22, text=f"= n{node.duplicate_of}",
                                        font=FONT_UI_SM, fill=TEXT_SECONDARY)

        max_x = max(x for x, _ in positions.values()) if positions else 600
        max_y = max(y for _, y in positions.values()) if positions else 400
        self.canvas.configure(
            scrollregion=(0, 0, max_x+margin_x+130, max_y+margin_y+130))

    def _compute_depths(self) -> dict[int, int]:
        depths: dict[int, int] = {}
        stack = [(self.tree.root_id, 0)]
        while stack:
            node_id, depth = stack.pop()
            depths[node_id] = depth
            for child_id in reversed(self.tree.nodes[node_id].children_ids):
                stack.append((child_id, depth+1))
        return depths