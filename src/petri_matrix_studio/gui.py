from __future__ import annotations

import math
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .coverage import CoverageTree, CoverageTreeBuilder, OMEGA, format_marking
from .engine import PetriMatrixEngine
from .io import load_json, save_json
from .model import Arc, PetriNet, Place, Transition

PLACE_RADIUS = 26
TRANSITION_W = 18
TRANSITION_H = 64


@dataclass
class Selection:
    kind: str | None = None
    item_id: str | None = None


class PetriStudioApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Petri Matrix Studio")
        self.geometry("1320x820")
        self.minsize(1100, 700)
        self.configure(bg="#e8edf3")

        self.net = PetriNet(name="Nueva red")
        self.selection = Selection()
        self.current_tool = tk.StringVar(value="select")
        self.status_var = tk.StringVar(value="Listo")
        self.name_var = tk.StringVar(value=self.net.name)
        self.arc_weight_var = tk.IntVar(value=1)
        self.place_tokens_var = tk.IntVar(value=0)
        self.label_var = tk.StringVar(value="")
        self.pending_arc_source: str | None = None
        self.drag_node_id: str | None = None
        self.drag_offset = (0.0, 0.0)
        self.file_path: Path | None = None

        self._setup_style()
        self._build_layout()
        self.redraw()

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#e8edf3")
        style.configure("Card.TFrame", background="#f8fbff")
        style.configure("TLabel", background="#e8edf3", foreground="#1f2937", font=("Segoe UI", 10))
        style.configure("Header.TLabel", background="#e8edf3", foreground="#0f172a", font=("Segoe UI", 12, "bold"))
        style.configure("TButton", font=("Segoe UI", 10))
        style.configure("Tool.TButton", padding=6)
        style.configure("TEntry", padding=4)
        style.configure("Sidebar.TLabelframe", background="#f8fbff")
        style.configure("Sidebar.TLabelframe.Label", background="#f8fbff", foreground="#0f172a", font=("Segoe UI", 10, "bold"))

    def _build_layout(self) -> None:
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=0)
        root.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(root, padding=(12, 10))
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        toolbar.columnconfigure(99, weight=1)

        ttk.Label(toolbar, text="Herramientas", style="Header.TLabel").grid(row=0, column=0, padx=(0, 10))
        self._tool_button(toolbar, "Seleccionar / Disparar", "select", 1)
        self._tool_button(toolbar, "Lugar", "place", 2)
        self._tool_button(toolbar, "Transición", "transition", 3)
        self._tool_button(toolbar, "Arco", "arc", 4)

        ttk.Button(toolbar, text="Nueva", command=self.new_net).grid(row=0, column=5, padx=6)
        ttk.Button(toolbar, text="Abrir JSON", command=self.open_json).grid(row=0, column=6, padx=6)
        ttk.Button(toolbar, text="Guardar JSON", command=self.save_json_dialog).grid(row=0, column=7, padx=6)
        ttk.Button(toolbar, text="Eliminar selección", command=self.delete_selection).grid(row=0, column=8, padx=6)
        ttk.Button(toolbar, text="Árbol de cobertura", command=self.show_coverage_tree).grid(row=0, column=9, padx=6)
        ttk.Button(toolbar, text="Recentrar vista", command=self.redraw).grid(row=0, column=10, padx=6)

        self.canvas = tk.Canvas(root, bg="#ffffff", highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=(12, 8), pady=(0, 8))
        self.canvas.bind("<Button-1>", self.on_left_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        sidebar = ttk.Frame(root, style="Card.TFrame", padding=12)
        sidebar.grid(row=1, column=1, sticky="ns", padx=(0, 12), pady=(0, 8))
        sidebar.configure(width=320)

        net_box = ttk.LabelFrame(sidebar, text="Red", style="Sidebar.TLabelframe", padding=10)
        net_box.pack(fill="x", pady=(0, 12))
        ttk.Label(net_box, text="Nombre").pack(anchor="w")
        name_entry = ttk.Entry(net_box, textvariable=self.name_var)
        name_entry.pack(fill="x", pady=(4, 8))
        name_entry.bind("<KeyRelease>", lambda _e: self.apply_name())
        ttk.Button(net_box, text="Aplicar nombre", command=self.apply_name).pack(fill="x")

        sim_box = ttk.LabelFrame(sidebar, text="Simulación matricial", style="Sidebar.TLabelframe", padding=10)
        sim_box.pack(fill="x", pady=(0, 12))
        ttk.Button(sim_box, text="Actualizar transiciones habilitadas", command=self.redraw).pack(fill="x")
        ttk.Button(sim_box, text="Resetear marcado a cero", command=self.reset_marking).pack(fill="x", pady=(8, 0))
        ttk.Button(sim_box, text="Construir árbol de cobertura", command=self.show_coverage_tree).pack(fill="x", pady=(8, 0))

        prop_box = ttk.LabelFrame(sidebar, text="Propiedades de selección", style="Sidebar.TLabelframe", padding=10)
        prop_box.pack(fill="both", expand=True)

        ttk.Label(prop_box, text="Etiqueta").pack(anchor="w")
        self.label_entry = ttk.Entry(prop_box, textvariable=self.label_var)
        self.label_entry.pack(fill="x", pady=(4, 8))

        ttk.Label(prop_box, text="Tokens del lugar").pack(anchor="w")
        self.tokens_spin = tk.Spinbox(prop_box, from_=0, to=9999, textvariable=self.place_tokens_var, width=8)
        self.tokens_spin.pack(anchor="w", pady=(4, 8))

        ttk.Label(prop_box, text="Peso del arco").pack(anchor="w")
        self.arc_spin = tk.Spinbox(prop_box, from_=1, to=999, textvariable=self.arc_weight_var, width=8)
        self.arc_spin.pack(anchor="w", pady=(4, 8))

        ttk.Button(prop_box, text="Aplicar cambios", command=self.apply_selection_changes).pack(fill="x", pady=(6, 0))
        ttk.Button(prop_box, text="Sumar token", command=lambda: self.bump_tokens(1)).pack(fill="x", pady=(8, 0))
        ttk.Button(prop_box, text="Restar token", command=lambda: self.bump_tokens(-1)).pack(fill="x", pady=(8, 0))

        status = ttk.Label(root, textvariable=self.status_var, anchor="w")
        status.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 8))

    def _tool_button(self, parent: ttk.Frame, text: str, value: str, column: int) -> None:
        btn = ttk.Radiobutton(parent, text=text, value=value, variable=self.current_tool)
        btn.grid(row=0, column=column, padx=4)

    def apply_name(self) -> None:
        self.net.name = self.name_var.get().strip() or "Nueva red"
        self.status(f"Nombre de la red actualizado: {self.net.name}")

    def new_net(self) -> None:
        self.net = PetriNet(name="Nueva red")
        self.file_path = None
        self.name_var.set(self.net.name)
        self.selection = Selection()
        self.pending_arc_source = None
        self.redraw()
        self.status("Se creó una nueva red")

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
            self.status(f"Red cargada desde {path}")
        except Exception as exc:
            messagebox.showerror("Error al abrir JSON", str(exc))

    def save_json_dialog(self) -> None:
        target = self.file_path
        if target is None:
            path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Petri JSON", "*.json")])
            if not path:
                return
            target = Path(path)
        try:
            self.apply_name()
            save_json(self.net, target)
            self.file_path = target
            self.status(f"Red guardada en {target}")
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
        self.status_var.set(msg)

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

    def on_left_click(self, event: tk.Event) -> None:
        x, y = float(event.x), float(event.y)
        tool = self.current_tool.get()
        hit = self.hit_test(x, y)

        if tool == "place":
            self.add_place(x, y)
            return
        if tool == "transition":
            self.add_transition(x, y)
            return
        if tool == "arc":
            self.handle_arc_tool(hit)
            return
        self.handle_select_tool(hit, x, y)

    def on_drag(self, event: tk.Event) -> None:
        if self.current_tool.get() != "select":
            return
        if not self.drag_node_id:
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
        place = Place(id=pid, label=pid, x=x, y=y, tokens=0)
        self.net.places.append(place)
        self.selection = Selection(kind="place", item_id=pid)
        self.refresh_property_panel()
        self.redraw()
        self.status(f"Lugar {pid} agregado")

    def add_transition(self, x: float, y: float) -> None:
        tid = self.net.next_transition_id()
        transition = Transition(id=tid, label=tid, x=x, y=y)
        self.net.transitions.append(transition)
        self.selection = Selection(kind="transition", item_id=tid)
        self.refresh_property_panel()
        self.redraw()
        self.status(f"Transición {tid} agregada")

    def handle_arc_tool(self, hit: tuple[str, str] | None) -> None:
        if not hit:
            self.pending_arc_source = None
            self.status("Seleccione un nodo origen y luego un nodo destino")
            return
        kind, node_id = hit
        if self.pending_arc_source is None:
            self.pending_arc_source = node_id
            self.status(f"Origen seleccionado: {node_id}. Ahora seleccione el destino")
            return
        source = self.pending_arc_source
        target = node_id
        self.pending_arc_source = None
        if source == target:
            self.status("Un arco no puede conectar un nodo consigo mismo")
            return
        if self.net.node_kind(source) == self.net.node_kind(target):
            self.status("Solo se permiten arcos lugar→transición o transición→lugar")
            return
        self.net.upsert_arc(source, target, weight=1)
        self.selection = Selection(kind="arc", item_id=f"{source}->{target}")
        self.refresh_property_panel()
        self.redraw()
        self.status(f"Arco {source} → {target} creado")

    def handle_select_tool(self, hit: tuple[str, str] | None, x: float, y: float) -> None:
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
                    self.status(f"Se disparó la transición {item_id}")
                except Exception as exc:
                    messagebox.showerror("Error al disparar transición", str(exc))
        elif kind in {"place", "transition"}:
            node = self.net.get_node(item_id)
            if node:
                self.drag_node_id = item_id
                self.drag_offset = (x - node.x, y - node.y)
        self.redraw()

    def hit_test(self, x: float, y: float) -> tuple[str, str] | None:
        for place in reversed(self.net.places):
            if (x - place.x) ** 2 + (y - place.y) ** 2 <= PLACE_RADIUS ** 2:
                return ("place", place.id)
        for transition in reversed(self.net.transitions):
            if (transition.x - TRANSITION_W / 2 <= x <= transition.x + TRANSITION_W / 2 and
                transition.y - TRANSITION_H / 2 <= y <= transition.y + TRANSITION_H / 2):
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
        return (x - mx) ** 2 + (y - my) ** 2 < 14 ** 2

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
            transition = self.net.get_transition(self.selection.item_id)
            if transition:
                self.label_var.set(transition.label)
        elif self.selection.kind == "arc" and self.selection.item_id:
            source, target = self.selection.item_id.split("->", 1)
            arc = self.net.get_arc(source, target)
            if arc:
                self.arc_weight_var.set(arc.weight)

    def redraw(self) -> None:
        self.canvas.delete("all")
        self.title(f"Petri Matrix Studio — {self.net.name}")
        enabled = set(self.engine().enabled_transition_ids()) if self.net.transitions else set()

        self.canvas.create_text(18, 16, anchor="nw", text=self.net.name, font=("Segoe UI", 14, "bold"), fill="#0f172a")

        for arc in self.net.arcs:
            self.draw_arc(arc)
        for place in self.net.places:
            self.draw_place(place)
        for transition in self.net.transitions:
            self.draw_transition(transition, transition.id in enabled)

        if self.pending_arc_source:
            node = self.net.get_node(self.pending_arc_source)
            if node:
                self.canvas.create_oval(node.x - 6, node.y - 6, node.x + 6, node.y + 6, outline="#fb7185", width=2)

    def draw_place(self, place: Place) -> None:
        outline = "#2563eb" if self.selection.kind == "place" and self.selection.item_id == place.id else "#1f2937"
        self.canvas.create_oval(
            place.x - PLACE_RADIUS,
            place.y - PLACE_RADIUS,
            place.x + PLACE_RADIUS,
            place.y + PLACE_RADIUS,
            fill="#f8fafc",
            outline=outline,
            width=3 if outline == "#2563eb" else 2,
        )
        self.canvas.create_text(place.x, place.y - 44, text=place.label, font=("Segoe UI", 10, "bold"), fill="#111827")
        self.canvas.create_text(place.x, place.y, text=str(place.tokens), font=("Segoe UI", 12, "bold"), fill="#0f172a")

    def draw_transition(self, transition: Transition, enabled: bool) -> None:
        selected = self.selection.kind == "transition" and self.selection.item_id == transition.id
        fill = "#22c55e" if enabled else "#94a3b8"
        outline = "#2563eb" if selected else "#0f172a"
        self.canvas.create_rectangle(
            transition.x - TRANSITION_W / 2,
            transition.y - TRANSITION_H / 2,
            transition.x + TRANSITION_W / 2,
            transition.y + TRANSITION_H / 2,
            fill=fill,
            outline=outline,
            width=3 if selected else 2,
        )
        self.canvas.create_text(transition.x, transition.y - 48, text=transition.label, font=("Segoe UI", 10, "bold"), fill="#111827")

    def node_anchor(self, node_id: str, toward_x: float, toward_y: float) -> tuple[float, float]:
        place = self.net.get_place(node_id)
        if place:
            dx, dy = toward_x - place.x, toward_y - place.y
            norm = math.hypot(dx, dy) or 1.0
            return place.x + PLACE_RADIUS * dx / norm, place.y + PLACE_RADIUS * dy / norm
        transition = self.net.get_transition(node_id)
        if not transition:
            return toward_x, toward_y
        dx, dy = toward_x - transition.x, toward_y - transition.y
        if abs(dx) > abs(dy):
            return (
                transition.x + math.copysign(TRANSITION_W / 2, dx),
                transition.y + dy * (TRANSITION_W / 2) / (abs(dx) or 1.0),
            )
        return (
            transition.x + dx * (TRANSITION_H / 2) / (abs(dy) or 1.0),
            transition.y + math.copysign(TRANSITION_H / 2, dy),
        )

    def draw_arc(self, arc: Arc) -> None:
        src = self.net.get_node(arc.source)
        dst = self.net.get_node(arc.target)
        if not src or not dst:
            return
        reverse_exists = self.net.has_arc(arc.target, arc.source)
        sx, sy = self.node_anchor(arc.source, dst.x, dst.y)
        tx, ty = self.node_anchor(arc.target, src.x, src.y)
        selected = self.selection.kind == "arc" and self.selection.item_id == f"{arc.source}->{arc.target}"
        color = "#2563eb" if selected else "#334155"
        width = 3 if selected else 2

        if reverse_exists:
            mx, my = (sx + tx) / 2, (sy + ty) / 2
            dx, dy = tx - sx, ty - sy
            norm = math.hypot(dx, dy) or 1.0
            ox, oy = -dy / norm * 26, dx / norm * 26
            self.canvas.create_line(sx, sy, mx + ox, my + oy, tx, ty, smooth=True, arrow=tk.LAST, width=width, fill=color)
            lx, ly = mx + ox, my + oy
        else:
            self.canvas.create_line(sx, sy, tx, ty, arrow=tk.LAST, width=width, fill=color)
            lx, ly = (sx + tx) / 2, (sy + ty) / 2

        if arc.weight > 1:
            self.canvas.create_text(lx, ly - 10, text=str(arc.weight), font=("Segoe UI", 10, "bold"), fill="#7c3aed")


def run_app() -> None:
    app = PetriStudioApp()
    app.mainloop()


class CoverageTreeWindow(tk.Toplevel):
    COLORS = {
        "frontier": "#f59e0b",
        "terminal": "#ef4444",
        "duplicate": "#8b5cf6",
        "internal": "#38bdf8",
    }

    def __init__(self, master: tk.Misc, net_name: str, tree: CoverageTree) -> None:
        super().__init__(master)
        self.title(f"Árbol de cobertura — {net_name}")
        self.geometry("1200x760")
        self.configure(bg="#f1f5f9")
        self.tree = tree

        container = ttk.Frame(self, padding=8)
        container.pack(fill="both", expand=True)
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(container, bg="#ffffff", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ybar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        xbar = ttk.Scrollbar(container, orient="horizontal", command=self.canvas.xview)
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        self.canvas.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)

        legend = ttk.Frame(self, padding=(10, 4, 10, 10))
        legend.pack(fill="x")
        ttk.Label(legend, text="Colores:").pack(side="left")
        for kind, text in [("frontier", "frontera"), ("terminal", "terminal"), ("duplicate", "duplicado"), ("internal", "interno")]:
            chip = tk.Label(legend, text=text, bg=self.COLORS[kind], fg="#0f172a", padx=8, pady=3)
            chip.pack(side="left", padx=5)

        self._draw_tree()

    def _draw_tree(self) -> None:
        levels: dict[int, list[int]] = {}
        depth_map = self._compute_depths()
        for node_id, depth in depth_map.items():
            levels.setdefault(depth, []).append(node_id)

        x_gap = 220
        y_gap = 150
        node_w = 140
        node_h = 56
        margin_x = 80
        margin_y = 60
        positions: dict[int, tuple[float, float]] = {}

        for depth in sorted(levels):
            node_ids = levels[depth]
            for idx, node_id in enumerate(node_ids):
                x = margin_x + idx * x_gap
                y = margin_y + depth * y_gap
                positions[node_id] = (x, y)

        for node in self.tree.nodes.values():
            if node.parent_id is None:
                continue
            x1, y1 = positions[node.parent_id]
            x2, y2 = positions[node.node_id]
            self.canvas.create_line(x1, y1 + node_h / 2, x2, y2 - node_h / 2, arrow=tk.LAST, width=2, fill="#475569")
            if node.via_transition:
                self.canvas.create_text((x1 + x2) / 2 + 20, (y1 + y2) / 2 - 10, text=node.via_transition, font=("Segoe UI", 10, "bold"), fill="#0f172a")

        for node_id, node in self.tree.nodes.items():
            x, y = positions[node_id]
            fill = self.COLORS.get(node.kind, "#cbd5e1")
            self.canvas.create_rectangle(x - node_w / 2, y - node_h / 2, x + node_w / 2, y + node_h / 2, fill=fill, outline="#0f172a", width=2)
            self.canvas.create_text(x, y - 10, text=f"n{node.node_id} · {node.kind}", font=("Segoe UI", 10, "bold"), fill="#0f172a")
            self.canvas.create_text(x, y + 12, text=format_marking(node.marking), font=("Consolas", 10), fill="#0f172a")
            if node.kind == "duplicate" and node.duplicate_of is not None:
                self.canvas.create_text(x, y + 28, text=f"= n{node.duplicate_of}", font=("Segoe UI", 9), fill="#111827")

        max_x = max(x for x, _ in positions.values()) if positions else 600
        max_y = max(y for _, y in positions.values()) if positions else 400
        self.canvas.configure(scrollregion=(0, 0, max_x + margin_x + 120, max_y + margin_y + 120))

    def _compute_depths(self) -> dict[int, int]:
        depths: dict[int, int] = {}
        stack = [(self.tree.root_id, 0)]
        while stack:
            node_id, depth = stack.pop()
            depths[node_id] = depth
            for child_id in reversed(self.tree.nodes[node_id].children_ids):
                stack.append((child_id, depth + 1))
        return depths
