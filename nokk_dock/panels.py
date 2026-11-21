"""Pannelli del dock: «Chiedi a NOKK» e impostazioni.

Sono finestre senza cornice costruite con widget Tk standard, colorate con il
tema attivo. Il pannello delle domande invia lo screenshot come allegato
immagine all'API di NOKK e mostra la risposta, mantenendo il contesto delle
domande successive.
"""

from __future__ import annotations

import copy
import queue
import sys
import threading
import tkinter as tk

from .client import NokkError
from .settings import (
    POSITIONS,
    POSITION_LABELS,
    WIDGET_LABELS,
    WIDGETS,
    default_config,
    normalize_shortcut,
    validate_config,
)
from .theme import PRESET_LABELS, PRESETS, mix

WINDOWS = sys.platform.startswith("win")

ACCENT_SWATCHES = ("#9b8cff", "#4f9dff", "#4fd1a5", "#f0b429", "#ff7a90", "#b4643a")


class _Panel:
    """Base comune: finestra senza cornice, trascinabile e chiusa con Esc."""

    def __init__(self, app, title, width, height):
        self.app = app
        self.theme = app.theme
        self.closed = False
        self.frameless = not WINDOWS
        self.win = tk.Toplevel(app.root)
        if self.frameless:
            self.win.overrideredirect(True)
        else:
            # Su Windows una finestra senza cornice non riceve il focus da
            # tastiera in modo affidabile: per i pannelli si usa quella nativa.
            self.win.title(title)
        try:
            self.win.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        self.win.configure(bg=self.theme.border)
        self.width = int(width * self.theme.scale)
        self.height = int(height * self.theme.scale)
        self.frame = tk.Frame(self.win, bg=self.theme.panel, padx=16, pady=14)
        self.frame.pack(fill="both", expand=True, padx=1, pady=1)
        header = tk.Frame(self.frame, bg=self.theme.panel)
        header.pack(fill="x", pady=(0, 10))
        tk.Label(
            header,
            text=title,
            bg=self.theme.panel,
            fg=self.theme.text,
            font=self.theme.font(11, "bold"),
        ).pack(side="left")
        close = tk.Button(
            header,
            text="✕",
            command=self.close,
            bg=self.theme.panel,
            fg=self.theme.muted,
            activebackground=self.theme.panel_hover,
            activeforeground=self.theme.text,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=6,
            pady=0,
            cursor="hand2",
            font=self.theme.font(10, "bold"),
        )
        close.pack(side="right")
        if self.frameless:
            self._bind_drag(header)
        self.win.bind("<Escape>", lambda _event: self.close())
        self.win.bind("<Button-1>", self._focus, add="+")
        app.panel_opened()

    def _focus(self, _event=None):
        try:
            self.win.focus_force()
        except tk.TclError:
            pass

    def _bind_drag(self, handle):
        state = {"x": 0, "y": 0}

        def start(event):
            state["x"] = event.x_root - self.win.winfo_rootx()
            state["y"] = event.y_root - self.win.winfo_rooty()

        def move(event):
            x = event.x_root - state["x"]
            y = event.y_root - state["y"]
            try:
                self.win.geometry(f"+{x}+{y}")
            except tk.TclError:
                pass

        handle.bind("<Button-1>", start, add="+")
        handle.bind("<B1-Motion>", move, add="+")

    def _place(self):
        plan = self.app.layout
        screen_w = self.app.root.winfo_screenwidth()
        screen_h = self.app.root.winfo_screenheight()
        if plan is not None:
            position = self.app.config["dock"]["position"]
            x = plan.x + (plan.width - self.width) // 2
            if position == "bottom":
                y = plan.y - self.height - 14
            elif position == "top":
                y = plan.y + plan.height + 14
            elif position == "left":
                x = plan.x + plan.width + 14
                y = plan.y
            else:
                x = plan.x - self.width - 14
                y = plan.y
        else:
            x = (screen_w - self.width) // 2
            y = (screen_h - self.height) // 2
        x = max(0, min(screen_w - self.width, x))
        y = max(0, min(screen_h - self.height, y))
        self.win.geometry(f"{self.width}x{self.height}+{x}+{y}")
        self.win.deiconify()
        self.win.lift()
        self._focus()

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        self.app.panel_closed()

    # -- widget helpers ---------------------------------------------------
    def _button(self, parent, text, command, primary=False, width=None):
        theme = self.theme
        background = theme.accent if primary else theme.panel_soft
        foreground = theme.on_accent if primary else theme.text
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=background,
            fg=foreground,
            activebackground=theme.accent if primary else theme.panel_hover,
            activeforeground=theme.on_accent if primary else theme.text,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=12,
            pady=6,
            cursor="hand2",
            font=theme.font(9.5),
        )
        if width:
            button.configure(width=width)
        return button

    def _entry(self, parent, variable=None, show=None):
        theme = self.theme
        entry = tk.Entry(
            parent,
            textvariable=variable,
            show=show or "",
            bg=theme.panel_soft,
            fg=theme.text,
            insertbackground=theme.text,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=theme.border,
            highlightcolor=theme.accent,
            font=theme.font(9.5),
        )
        return entry

    def _label(self, parent, text, size=9.0, color=None, weight="normal"):
        return tk.Label(
            parent,
            text=text,
            bg=self.theme.panel,
            fg=color or self.theme.muted,
            font=self.theme.font(size, weight),
            anchor="w",
            justify="left",
        )

    def _segmented(self, parent, variable, options, command=None):
        """Gruppo di pulsanti mutuamente esclusivi (Radiobutton senza pallino)."""
        theme = self.theme
        frame = tk.Frame(parent, bg=theme.panel)
        for value, label in options:
            button = tk.Radiobutton(
                frame,
                text=label,
                value=value,
                variable=variable,
                command=command,
                indicatoron=False,
                bg=theme.panel_soft,
                fg=theme.text,
                selectcolor=theme.accent,
                activebackground=theme.panel_hover,
                activeforeground=theme.text,
                relief="flat",
                bd=0,
                highlightthickness=0,
                padx=10,
                pady=5,
                cursor="hand2",
                font=theme.font(9.0),
            )
            button.pack(side="left", padx=(0, 4))
        return frame

    def _slider(self, parent, variable, low, high, step, command=None):
        theme = self.theme
        return tk.Scale(
            parent,
            from_=low,
            to=high,
            resolution=step,
            orient="horizontal",
            variable=variable,
            command=command,
            showvalue=False,
            sliderlength=14,
            width=7,
            bg=theme.panel,
            troughcolor=theme.panel_soft,
            activebackground=theme.accent,
            highlightthickness=0,
            bd=0,
            length=int(150 * theme.scale),
        )


class AskPanel(_Panel):
    """Finestra «Chiedi a NOKK», con allegato immagine opzionale."""

    def __init__(self, app, image=None, question=None):
        super().__init__(app, "Chiedi a NOKK", 560, 430)
        self.client = app.client
        self.image = image
        self.history: list[dict] = []
        self.queue: queue.Queue = queue.Queue()
        self.busy = False
        self._pump_job = None
        self._build(question)
        self._place()
        self._pump_job = self.win.after(90, self._pump)

    def _build(self, question):
        theme = self.theme
        if self.image:
            self._build_preview()
        entry_row = tk.Frame(self.frame, bg=theme.panel)
        entry_row.pack(fill="x", pady=(0, 6))
        self.question = tk.StringVar(value=question or "")
        entry = self._entry(entry_row, self.question)
        entry.pack(side="left", fill="x", expand=True, ipady=6)
        entry.bind("<Return>", lambda _event: self._send())
        self.send_button = self._button(entry_row, "Invia", self._send, primary=True)
        self.send_button.pack(side="left", padx=(8, 0))
        self.status = self._label(self.frame, "", 8.6)
        self.status.pack(fill="x", pady=(0, 6))
        body = tk.Frame(self.frame, bg=theme.panel)
        body.pack(fill="both", expand=True)
        self.answer = tk.Text(
            body,
            height=8,
            wrap="word",
            bg=theme.panel_soft,
            fg=theme.text,
            insertbackground=theme.text,
            relief="flat",
            bd=0,
            padx=12,
            pady=10,
            spacing1=2,
            spacing3=5,
            highlightthickness=1,
            highlightbackground=theme.border,
            font=theme.font(9.5),
        )
        self.answer.pack(side="left", fill="both", expand=True)
        scrollbar = tk.Scrollbar(
            body, command=self.answer.yview, width=10, bd=0,
            bg=theme.panel, troughcolor=theme.panel, activebackground=theme.muted,
            highlightthickness=0,
        )
        scrollbar.pack(side="right", fill="y")
        self.answer.configure(yscrollcommand=scrollbar.set)
        self.answer.configure(state="disabled")
        self.answer.tag_configure("user", foreground=theme.muted)
        self.answer.tag_configure("answer", foreground=theme.text)
        self.answer.tag_configure("error", foreground="#ff6b81")
        footer = tk.Frame(self.frame, bg=theme.panel)
        footer.pack(fill="x", pady=(8, 0))
        self._button(footer, "Copia ultima risposta", self._copy).pack(side="left")
        self._button(footer, "Chiudi", self.close).pack(side="right")
        self.win.after(60, lambda: entry.focus_set())

    def _build_preview(self):
        theme = self.theme
        holder = tk.Frame(self.frame, bg=theme.panel_soft)
        holder.pack(fill="x", pady=(0, 8))
        photo = self._photo()
        if photo is not None:
            label = tk.Label(holder, image=photo, bg=theme.panel_soft, bd=0)
            label.image = photo
            label.pack(padx=8, pady=8)
        else:
            tk.Label(
                holder,
                text="Screenshot pronto, anteprima non disponibile per questo formato.",
                bg=theme.panel_soft,
                fg=theme.muted,
                font=theme.font(8.6),
                padx=10,
                pady=9,
            ).pack(fill="x")

    def _photo(self):
        if not self.image:
            return None
        if self.image.get("mime_type") not in ("image/png", "image/gif"):
            return None
        try:
            photo = tk.PhotoImage(data=self.image["data"])
        except tk.TclError:
            return None
        factor = max(1, int(round(photo.width() / (self.width - 40))))
        if factor > 1:
            photo = photo.subsample(factor, factor)
        if photo.height() > int(150 * self.theme.scale):
            factor = max(2, int(round(photo.height() / (150 * self.theme.scale))))
            photo = photo.subsample(factor, factor)
        return photo

    # -- invio ------------------------------------------------------------
    def _send(self):
        if self.busy:
            return
        text = self.question.get().strip()
        if not text:
            text = self.app.config["ask"]["prompt"] if self.image else ""
        if not text:
            self._set_status("Scrivi una domanda per NOKK.", error=True)
            return
        image = self.image
        self.image = None
        self.busy = True
        self.send_button.configure(state="disabled")
        self._set_status("NOKK sta pensando…")
        self.question.set("")
        self._append(f"Tu: {text}\n", "user")
        threading.Thread(
            target=self._worker, args=(text, image), name="nokk-dock-ask", daemon=True
        ).start()

    def _worker(self, text, image):
        try:
            result = self.client.ask(
                text,
                image=image,
                history=self.history,
                on_status=self._on_partial,
            )
        except NokkError as error:
            self.queue.put(("error", error.message))
            return
        except Exception as error:  # noqa: BLE001 - mostrato all'utente
            self.queue.put(("error", f"Errore imprevisto: {error}"))
            return
        self.queue.put(("reply", (text, result)))

    def _on_partial(self, partial, _status):
        self.queue.put(("partial", partial))

    def _pump(self):
        if self.closed:
            return
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "partial":
                    length = len(payload or "")
                    self._set_status(f"NOKK sta scrivendo… {length} caratteri" if length
                                     else "NOKK sta pensando…")
                elif kind == "reply":
                    text, result = payload
                    reply = (result.get("reply") or "").strip() or "(nessun testo)"
                    self._append(f"NOKK: {reply}\n\n", "answer")
                    self.history.append({"role": "user", "content": text})
                    self.history.append({"role": "assistant", "content": reply})
                    self.history = self.history[-12:]
                    self._set_status("Risposta pronta.")
                    self._finish()
                elif kind == "error":
                    self._append(f"{payload}\n\n", "error")
                    self._set_status(str(payload), error=True)
                    self._finish()
        except queue.Empty:
            pass
        finally:
            self._pump_job = self.win.after(90, self._pump)

    def _finish(self):
        self.busy = False
        try:
            self.send_button.configure(state="normal")
        except tk.TclError:
            pass

    def _append(self, text, tag):
        try:
            self.answer.configure(state="normal")
            self.answer.insert("end", text, tag)
            self.answer.see("end")
            self.answer.configure(state="disabled")
        except tk.TclError:
            pass

    def _set_status(self, text, error=False):
        try:
            self.status.configure(text=text, fg="#ff6b81" if error else self.theme.muted)
        except tk.TclError:
            pass

    def _copy(self):
        try:
            content = self.answer.get("1.0", "end").strip()
            self.win.clipboard_clear()
            self.win.clipboard_append(content)
            self._set_status("Risposta copiata negli appunti.")
        except tk.TclError:
            pass

    def close(self):
        if self.closed:
            return
        self.busy = False
        if self._pump_job is not None:
            try:
                self.win.after_cancel(self._pump_job)
            except (tk.TclError, ValueError):
                pass
            self._pump_job = None
        super().close()


class SettingsPanel(_Panel):
    """Pannello di personalizzazione completo del dock."""

    def __init__(self, app):
        super().__init__(app, "Impostazioni del dock", 620, 620)
        self.draft = copy.deepcopy(app.config)
        self.widget_order = list(self.draft["widgets"])
        for key in WIDGETS:
            if key not in self.widget_order:
                self.widget_order.append(key)
        self.widget_vars = {key: tk.BooleanVar(value=key in self.widget_order) for key in WIDGETS}
        self.status_text = tk.StringVar(value="")
        self.queue: queue.Queue = queue.Queue()
        self._pump_job = None
        self._build()
        self._place()
        self.win.after(80, self._focus)
        self._pump_job = self.win.after(90, self._pump)

    # -- costruzione ------------------------------------------------------
    def _build(self):
        theme = self.theme
        outer = tk.Frame(self.frame, bg=theme.panel)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=theme.panel, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(
            outer, orient="vertical", command=canvas.yview, width=10, bd=0,
            bg=theme.panel, troughcolor=theme.panel, activebackground=theme.muted,
            highlightthickness=0,
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(canvas, bg=theme.panel)
        self._body_window = canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(self._body_window, width=event.width),
        )
        canvas.bind_all("<Button-4>", lambda _event: canvas.yview_scroll(-2, "units"))
        canvas.bind_all("<Button-5>", lambda _event: canvas.yview_scroll(2, "units"))
        self.canvas = canvas

        self._build_position_section()
        self._build_theme_section()
        self._build_widget_section()
        self._build_weather_section()
        self._build_nokk_section()
        self._build_capture_section()
        self._build_dock_section()
        self._build_footer()

    def _section(self, title):
        theme = self.theme
        container = tk.Frame(self.body, bg=theme.panel)
        container.pack(fill="x", pady=(6, 10))
        tk.Label(
            container,
            text=title.upper(),
            bg=theme.panel,
            fg=theme.muted,
            font=theme.font(8.0, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 6))
        return container

    def _row(self, parent, label, builder, hint=None):
        """Riga etichetta + controllo; `builder` crea il controllo nella riga."""
        theme = self.theme
        row = tk.Frame(parent, bg=theme.panel)
        row.pack(fill="x", pady=3)
        tk.Label(
            row, text=label, bg=theme.panel, fg=theme.text,
            font=theme.font(9.2), width=16, anchor="w",
        ).pack(side="left")
        widget = builder(row)
        widget.pack(side="left", fill="x", expand=True)
        if hint:
            tk.Label(
                row, text=hint, bg=theme.panel, fg=theme.muted,
                font=theme.font(7.8), anchor="w",
            ).pack(side="left", padx=(8, 0))
        return row

    def _build_position_section(self):
        section = self._section("Posizione sullo schermo")
        self.var_position = tk.StringVar(value=self.draft["dock"]["position"])
        segmented = self._segmented(
            section,
            self.var_position,
            [(position, POSITION_LABELS[position]) for position in POSITIONS],
        )
        segmented.pack(anchor="w")
        self.var_offset = tk.DoubleVar(value=self.draft["dock"]["offset"])
        self._row(
            section, "Posizione sul lato",
            lambda row: self._slider(row, self.var_offset, 0.0, 1.0, 0.05),
            "0 = inizio · 1 = fine",
        )

    def _build_theme_section(self):
        section = self._section("Tema")
        self.var_preset = tk.StringVar(value=self.draft["theme"]["preset"])
        segmented = self._segmented(
            section,
            self.var_preset,
            [(preset, PRESET_LABELS.get(preset, preset)) for preset in PRESETS],
            command=self._refresh_preview_note,
        )
        segmented.pack(anchor="w", pady=(0, 4))
        accent_row = tk.Frame(section, bg=self.theme.panel)
        accent_row.pack(fill="x", pady=3)
        tk.Label(
            accent_row, text="Colore accento", bg=self.theme.panel,
            fg=self.theme.text, font=self.theme.font(9.2), width=16, anchor="w",
        ).pack(side="left")
        self.var_accent = tk.StringVar(value=self.draft["theme"]["accent"])
        for color in ACCENT_SWATCHES:
            tk.Button(
                accent_row, bg=color, width=2, relief="flat", bd=0,
                highlightthickness=1, highlightbackground=self.theme.border,
                activebackground=color, cursor="hand2",
                command=lambda value=color: self.var_accent.set(value),
            ).pack(side="left", padx=(0, 4))
        entry = self._entry(accent_row, self.var_accent)
        entry.configure(width=9)
        entry.pack(side="left", padx=(6, 0), ipady=3)

        self.var_opacity = tk.DoubleVar(value=self.draft["dock"]["opacity"])
        self._row(section, "Opacità",
                  lambda row: self._slider(row, self.var_opacity, 0.4, 1.0, 0.05))
        self.var_scale = tk.DoubleVar(value=self.draft["theme"]["scale"])
        self._row(section, "Dimensione",
                  lambda row: self._slider(row, self.var_scale, 0.7, 1.6, 0.05))
        self.var_radius = tk.DoubleVar(value=self.draft["theme"]["radius"])
        self._row(section, "Angoli",
                  lambda row: self._slider(row, self.var_radius, 0.0, 40.0, 1.0))
        self.preview_note = self._label(section, "", 8.2)
        self.preview_note.pack(fill="x", pady=(4, 0))
        self._refresh_preview_note()

    def _refresh_preview_note(self):
        preset = self.var_preset.get()
        base = PRESETS.get(preset, {})
        accent = self.var_accent.get() if hasattr(self, "var_accent") else ""
        accent = accent or base.get("accent", "#9b8cff")
        text = f"Preset «{PRESET_LABELS.get(preset, preset)}» · accento {accent}"
        if base.get("light"):
            text += " · tema chiaro"
        try:
            self.preview_note.configure(text=text)
        except tk.TclError:
            pass

    def _build_widget_section(self):
        self.widget_section = self._section("Widget e ordine")
        self.widget_rows = tk.Frame(self.widget_section, bg=self.theme.panel)
        self.widget_rows.pack(fill="x")
        self._render_widget_rows()

    def _render_widget_rows(self):
        theme = self.theme
        for child in self.widget_rows.winfo_children():
            child.destroy()
        for index, key in enumerate(self.widget_order):
            row = tk.Frame(self.widget_rows, bg=theme.panel)
            row.pack(fill="x", pady=1)
            tk.Checkbutton(
                row,
                text=WIDGET_LABELS.get(key, key),
                variable=self.widget_vars[key],
                bg=theme.panel,
                fg=theme.text,
                activebackground=theme.panel,
                activeforeground=theme.text,
                selectcolor=theme.panel_soft,
                highlightthickness=0,
                bd=0,
                font=theme.font(9.2),
                anchor="w",
                cursor="hand2",
            ).pack(side="left")
            for label, delta in (("▲", -1), ("▼", 1)):
                tk.Button(
                    row,
                    text=label,
                    command=lambda k=key, d=delta: self._move_widget(k, d),
                    bg=theme.panel_soft,
                    fg=theme.muted,
                    activebackground=theme.panel_hover,
                    activeforeground=theme.text,
                    relief="flat",
                    bd=0,
                    highlightthickness=0,
                    padx=6,
                    pady=0,
                    cursor="hand2",
                    font=theme.font(7.5),
                ).pack(side="right", padx=(4, 0))
        if not self.widget_order:
            self._label(self.widget_rows, "Nessun widget attivo").pack(anchor="w")

    def _move_widget(self, key, delta):
        try:
            index = self.widget_order.index(key)
        except ValueError:
            return
        target = max(0, min(len(self.widget_order) - 1, index + delta))
        if target == index:
            return
        self.widget_order.insert(target, self.widget_order.pop(index))
        self._render_widget_rows()

    def _build_weather_section(self):
        section = self._section("Meteo")
        city_row = tk.Frame(section, bg=self.theme.panel)
        city_row.pack(fill="x", pady=3)
        tk.Label(
            city_row, text="Città", bg=self.theme.panel, fg=self.theme.text,
            font=self.theme.font(9.2), width=16, anchor="w",
        ).pack(side="left")
        self.var_city = tk.StringVar(value=self.draft["weather"]["city"])
        self.var_latitude = self.draft["weather"].get("latitude")
        self.var_longitude = self.draft["weather"].get("longitude")
        entry = self._entry(city_row, self.var_city)
        entry.pack(side="left", fill="x", expand=True, ipady=4)
        self._button(city_row, "Rileva", self._detect_city).pack(side="left", padx=(8, 0))
        self.city_status = self._label(section, self._coordinates_text(), 8.0)
        self.city_status.pack(fill="x", pady=(2, 4))
        self.var_units = tk.StringVar(value=self.draft["weather"]["units"])
        self._segmented(section, self.var_units,
                        [("metric", "Celsius"), ("imperial", "Fahrenheit")]).pack(anchor="w")

    def _coordinates_text(self):
        if self.var_latitude is None or self.var_longitude is None:
            return "Coordinate non impostate: premi Rileva dopo aver scritto la città."
        return f"Coordinate: {self.var_latitude:.3f}, {self.var_longitude:.3f}"

    def _detect_city(self):
        city = self.var_city.get().strip()
        if not city:
            self.city_status.configure(text="Scrivi prima il nome della città.")
            return
        self.city_status.configure(text="Ricerca della località…")

        def worker():
            service = self.app.weather_service
            resolved, error = service._resolve(city)
            self.queue.put(lambda: self._city_detected(resolved, error))

        threading.Thread(target=worker, daemon=True).start()

    def _city_detected(self, resolved, error):
        if self.closed:
            return
        if resolved is None:
            self.city_status.configure(text=error or "Località non trovata.")
            return
        name, latitude, longitude = resolved
        self.var_latitude = latitude
        self.var_longitude = longitude
        self.var_city.set(name)
        self.city_status.configure(text=f"Trovata: {name} · {latitude:.3f}, {longitude:.3f}")

    def _build_nokk_section(self):
        section = self._section("Collegamento a NOKK")
        self.var_base_url = tk.StringVar(value=self.draft["nokk"]["base_url"])
        self.var_api_key = tk.StringVar(value=self.draft["nokk"]["api_key"])
        self.var_mode = tk.StringVar(value=self.draft["nokk"]["mode"])
        self._row(section, "Indirizzo",
                  lambda row: self._entry(row, self.var_base_url))
        self._row(section, "Chiave API",
                  lambda row: self._entry(row, self.var_api_key, show="•"))
        self._segmented(
            section,
            self.var_mode,
            [("", "Predefinita"), ("codice", "Codice"), ("studio", "Studio"), ("analista", "Analista")],
        ).pack(anchor="w", pady=(4, 4))
        actions = tk.Frame(section, bg=self.theme.panel)
        actions.pack(fill="x", pady=(2, 0))
        self._button(actions, "Verifica", self._test_connection).pack(side="left")
        self._button(actions, "Apri NOKK", self._open_nokk).pack(side="left", padx=(8, 0))
        self.nokk_status = self._label(section, "", 8.2)
        self.nokk_status.pack(fill="x", pady=(4, 0))
        self._label(
            section,
            "La chiave si crea in NOKK → Impostazioni → API. Resta solo su questo computer.",
            7.8,
        ).pack(fill="x", pady=(2, 0))

    def _test_connection(self):
        base_url = self.var_base_url.get().strip().rstrip("/")
        api_key = self.var_api_key.get().strip()
        self.nokk_status.configure(text="Verifica in corso…")

        def worker():
            from .client import NokkClient

            client = NokkClient(base_url, api_key, timeout=12)
            health = client.health()
            if health is None:
                message = "NOKK non risponde su questo indirizzo."
            else:
                try:
                    client._request("GET", "/planner", timeout=8)
                except NokkError as error:
                    message = error.message
                else:
                    message = "Connessione riuscita con NOKK."
            self.queue.put(lambda: self.nokk_status.configure(text=message))

        threading.Thread(target=worker, daemon=True).start()

    def _open_nokk(self):
        import webbrowser

        webbrowser.open(self.var_base_url.get().strip() or "http://127.0.0.1:8000")

    def _build_capture_section(self):
        section = self._section("Cattura schermo")
        self.var_shortcut = tk.StringVar(value=self.draft["capture"]["shortcut"])
        self._row(section, "Scorciatoia",
                  lambda row: self._entry(row, self.var_shortcut))
        self.var_capture_scale = tk.DoubleVar(value=self.draft["capture"]["scale"])
        self._row(section, "Dettaglio",
                  lambda row: self._slider(row, self.var_capture_scale, 0.25, 1.0, 0.05))
        self._label(
            section,
            "Su X11 la scorciatoia viene registrata subito. Su Wayland il desktop non "
            "permette scorciatoie globali: assegna a «python dock_start.py --capture» "
            "la combinazione che preferisci.",
            7.8,
        ).pack(fill="x", pady=(2, 0))
        self.var_prompt = tk.StringVar(value=self.draft["ask"]["prompt"])
        self._row(section, "Domanda",
                  lambda row: self._entry(row, self.var_prompt))

    def _build_dock_section(self):
        section = self._section("Comportamento")
        self.var_auto_hide = tk.BooleanVar(value=self.draft["dock"]["auto_hide"])
        self.var_topmost = tk.BooleanVar(value=self.draft["dock"]["always_on_top"])
        for text, variable in (
            ("Nascondi quando non serve", self.var_auto_hide),
            ("Sempre sopra le finestre", self.var_topmost),
        ):
            tk.Checkbutton(
                section, text=text, variable=variable, bg=self.theme.panel,
                fg=self.theme.text, activebackground=self.theme.panel,
                activeforeground=self.theme.text, selectcolor=self.theme.panel_soft,
                highlightthickness=0, bd=0, font=self.theme.font(9.2),
                anchor="w", cursor="hand2",
            ).pack(anchor="w")
        self.var_thickness = tk.DoubleVar(value=self.draft["dock"]["thickness"])
        self._row(section, "Spessore",
                  lambda row: self._slider(row, self.var_thickness, 44, 100, 1))
        self.var_length = tk.DoubleVar(value=self.draft["dock"]["length"])
        self._row(section, "Lunghezza",
                  lambda row: self._slider(row, self.var_length, 300, 1400, 10))
        self.var_margin = tk.DoubleVar(value=self.draft["dock"]["margin"])
        self._row(section, "Distanza dal bordo",
                  lambda row: self._slider(row, self.var_margin, 0, 120, 1))
        self.var_magnify = tk.DoubleVar(value=self.draft["dock"]["magnify"])
        self._row(section, "Ingrandimento",
                  lambda row: self._slider(row, self.var_magnify, 1.0, 1.6, 0.05),
                  "sotto il cursore")
        self.var_labels = tk.BooleanVar(value=self.draft["dock"]["show_labels"])
        tk.Checkbutton(
            section, text="Etichette al passaggio del mouse", variable=self.var_labels,
            bg=self.theme.panel, fg=self.theme.text,
            activebackground=self.theme.panel, activeforeground=self.theme.text,
            selectcolor=self.theme.panel_soft, highlightthickness=0, bd=0,
            font=self.theme.font(9.2), anchor="w", cursor="hand2",
        ).pack(anchor="w")

    def _build_footer(self):
        theme = self.theme
        footer = tk.Frame(self.body, bg=theme.panel)
        footer.pack(fill="x", pady=(4, 8))
        self._button(footer, "Salva", self._save, primary=True).pack(side="right")
        self._button(footer, "Annulla", self.close).pack(side="right", padx=(0, 8))
        self._button(footer, "Predefiniti", self._reset).pack(side="left")
        tk.Label(
            footer, textvariable=self.status_text, bg=theme.panel,
            fg=theme.muted, font=theme.font(8.2), anchor="w",
        ).pack(side="left", padx=(10, 0))

    # -- salvataggio ------------------------------------------------------
    def _collect(self):
        config = copy.deepcopy(self.draft)
        enabled = [key for key in self.widget_order if self.widget_vars[key].get()]
        config["dock"]["position"] = self.var_position.get()
        config["dock"]["offset"] = float(self.var_offset.get())
        config["dock"]["opacity"] = float(self.var_opacity.get())
        config["dock"]["auto_hide"] = bool(self.var_auto_hide.get())
        config["dock"]["always_on_top"] = bool(self.var_topmost.get())
        config["dock"]["thickness"] = int(round(float(self.var_thickness.get())))
        config["dock"]["length"] = int(round(float(self.var_length.get())))
        config["dock"]["margin"] = int(round(float(self.var_margin.get())))
        config["dock"]["magnify"] = float(self.var_magnify.get())
        config["dock"]["show_labels"] = bool(self.var_labels.get())
        config["theme"]["preset"] = self.var_preset.get()
        config["theme"]["accent"] = self.var_accent.get().strip()
        config["theme"]["scale"] = float(self.var_scale.get())
        config["theme"]["radius"] = float(self.var_radius.get())
        config["widgets"] = enabled
        config["weather"]["city"] = self.var_city.get().strip()
        config["weather"]["latitude"] = self.var_latitude
        config["weather"]["longitude"] = self.var_longitude
        config["weather"]["units"] = self.var_units.get()
        config["nokk"]["base_url"] = self.var_base_url.get().strip().rstrip("/")
        config["nokk"]["api_key"] = self.var_api_key.get().strip()
        config["nokk"]["mode"] = self.var_mode.get()
        config["capture"]["shortcut"] = normalize_shortcut(self.var_shortcut.get())
        config["capture"]["scale"] = float(self.var_capture_scale.get())
        config["ask"]["prompt"] = self.var_prompt.get().strip() or default_config()["ask"]["prompt"]
        return config

    def _save(self):
        try:
            config = validate_config(self._collect())
        except ValueError as error:
            self.status_text.set(str(error))
            return
        try:
            self.app._apply_config(config)
            self.app._install_hotkey()
        except (OSError, ValueError) as error:
            self.status_text.set(f"Impossibile salvare: {error}")
            return
        self.app.toast("Impostazioni del dock salvate.")
        self.close()

    def _reset(self):
        defaults = default_config()
        self.draft = defaults
        self.widget_order = list(defaults["widgets"])
        for key, variable in self.widget_vars.items():
            variable.set(key in self.widget_order)
        self._render_widget_rows()
        self.var_position.set(defaults["dock"]["position"])
        self.var_offset.set(defaults["dock"]["offset"])
        self.var_opacity.set(defaults["dock"]["opacity"])
        self.var_scale.set(defaults["theme"]["scale"])
        self.var_radius.set(defaults["theme"]["radius"])
        self.var_preset.set(defaults["theme"]["preset"])
        self.var_accent.set("")
        self.var_auto_hide.set(defaults["dock"]["auto_hide"])
        self.var_topmost.set(defaults["dock"]["always_on_top"])
        self.var_thickness.set(defaults["dock"]["thickness"])
        self.var_length.set(defaults["dock"]["length"])
        self.var_margin.set(defaults["dock"]["margin"])
        self.var_magnify.set(defaults["dock"]["magnify"])
        self.var_labels.set(defaults["dock"]["show_labels"])
        self.var_city.set(defaults["weather"]["city"])
        self.var_latitude = defaults["weather"]["latitude"]
        self.var_longitude = defaults["weather"]["longitude"]
        self.city_status.configure(text=self._coordinates_text())
        self.var_units.set(defaults["weather"]["units"])
        self.var_base_url.set(defaults["nokk"]["base_url"])
        self.var_api_key.set(defaults["nokk"]["api_key"])
        self.var_mode.set(defaults["nokk"]["mode"])
        self.var_shortcut.set(defaults["capture"]["shortcut"])
        self.var_capture_scale.set(defaults["capture"]["scale"])
        self.var_prompt.set(defaults["ask"]["prompt"])
        self.status_text.set("Valori predefiniti caricati: premi Salva per applicarli.")

    def _pump(self):
        if self.closed:
            return
        try:
            while True:
                callback = self.queue.get_nowait()
                try:
                    callback()
                except tk.TclError:
                    pass
        except queue.Empty:
            pass
        finally:
            self._pump_job = self.win.after(90, self._pump)

    def close(self):
        if self.closed:
            return
        if self._pump_job is not None:
            try:
                self.win.after_cancel(self._pump_job)
            except (tk.TclError, ValueError):
                pass
            self._pump_job = None
        try:
            self.canvas.unbind_all("<Button-4>")
            self.canvas.unbind_all("<Button-5>")
        except tk.TclError:
            pass
        super().close()


__all__ = ["AskPanel", "SettingsPanel", "mix"]
