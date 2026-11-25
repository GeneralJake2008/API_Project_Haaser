"""
dvids_viewer.py  -  DVIDS Viewer (alles in einer Datei)

Starten:  python dvids_viewer.py
Bilder:   pip install pillow   (optional - ohne geht's auch, nur ohne Bilder)

OBEN:  dein API-Teil  -> die Funktion search()
UNTEN: die GUI        -> musst du nicht anfassen
"""
import io
import queue
import re
import threading
import urllib.request
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox

import requests


# =============================================================================
#  DEIN API-TEIL
# =============================================================================

API_KEY = "key-6af47275ef19e"          
BASE_URL = "https://api.dvidshub.net/search"

def search(query, branch=None, media_type=None, max_results=20):

    parameters = {"api_key": API_KEY, "max_results": max_results}

    if query:
        parameters["q"] = query
    if branch:
        parameters["branch"] = branch
    if media_type:
        parameters["type"] = media_type

    response = requests.get(BASE_URL, params=parameters, timeout=10)
    
    data = response.json()

    return data["results"]

# =============================================================================
#  GUI  (ab hier nichts aendern noetig)
# =============================================================================

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


BRANCHES = ["All", "Marines", "Army", "Navy", "Air Force", "Coast Guard", "Joint"]
TYPES = ["all", "image", "news", "video"]

# colors (dark theme, Marine scarlet & gold)
BG = "#1b1e22"
PANEL = "#252a30"
FIELD = "#2f353c"
FG = "#e8e8e8"
MUTED = "#9aa3ab"
SCARLET = "#b3122a"
SCARLET_HOVER = "#d0173a"
GOLD = "#ffc72c"

THUMB_SIZE = (380, 285)

class DvidsViewer(tk.Tk):  # pylint: disable=too-many-instance-attributes
    """Hauptfenster des DVIDS Viewers."""

    def __init__(self):
        super().__init__()
        self.title("DVIDS Viewer")
        self.geometry("1150x680")
        self.minsize(850, 500)
        self.configure(bg=BG)

        self.results = []
        self.current_url = None      # url of the selected item
        self.current_thumb = None    # keeps the image alive (tkinter needs this)
        self._empty = None           # empty placeholder image
        self._jobs = queue.Queue()   # results from background threads

        self._setup_style()
        self._build_top_bar()
        self._build_status_bar()     # before main area, so it never gets squeezed out
        self._build_main_area()
        self._show_details(None)

        self.after(100, self._poll_jobs)
        self.search_entry.focus_set()

    # ------------------------------------------------------------- styling
    def _setup_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=FIELD,
                    font=("Segoe UI", 10))
        s.configure("TFrame", background=BG)
        s.configure("Panel.TFrame", background=PANEL)
        s.configure("TLabel", background=BG, foreground=FG)
        s.configure("Panel.TLabel", background=PANEL, foreground=FG)
        s.configure("Muted.TLabel", background=PANEL, foreground=MUTED)
        s.configure("Header.TLabel", background=BG, foreground=GOLD,
                    font=("Segoe UI", 16, "bold"))
        s.configure("Title.TLabel", background=PANEL, foreground=FG,
                    font=("Segoe UI", 13, "bold"))
        s.configure("Status.TLabel", background=PANEL, foreground=MUTED,
                    padding=(10, 4))

        s.configure("Accent.TButton", background=SCARLET, foreground="white",
                    borderwidth=0, padding=(14, 6), font=("Segoe UI", 10, "bold"))
        s.map("Accent.TButton",
              background=[("disabled", "#5a2a32"), ("active", SCARLET_HOVER)])

        s.configure("TEntry", fieldbackground=FIELD, foreground=FG,
                    insertcolor=FG, borderwidth=0, padding=6)
        s.configure("TCombobox", fieldbackground=FIELD, background=FIELD,
                    foreground=FG, arrowcolor=FG, padding=4)
        s.map("TCombobox", fieldbackground=[("readonly", FIELD)],
              foreground=[("readonly", FG)])
        s.configure("TSpinbox", fieldbackground=FIELD, foreground=FG,
                    arrowcolor=FG, padding=4)
        self.option_add("*TCombobox*Listbox.background", FIELD)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", SCARLET)

        s.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                    foreground=FG, rowheight=28, borderwidth=0)
        s.map("Treeview", background=[("selected", SCARLET)],
              foreground=[("selected", "white")])
        s.configure("Treeview.Heading", background=FIELD, foreground=GOLD,
                    font=("Segoe UI", 10, "bold"), borderwidth=0)
        s.map("Treeview.Heading", background=[("active", FIELD)])

    # ------------------------------------------------------------- layout
    def _build_top_bar(self):
        top_bar = ttk.Frame(self, padding=(14, 12))
        top_bar.pack(fill="x")

        ttk.Label(top_bar, text="DVIDS VIEWER", style="Header.TLabel").pack(
            side="left", padx=(0, 20))

        self.search_var = tk.StringVar(value="marines")
        self.search_entry = ttk.Entry(top_bar, textvariable=self.search_var, width=30)
        self.search_entry.pack(side="left", padx=(0, 10))
        self.search_entry.bind("<Return>", lambda e: self.do_search())

        ttk.Label(top_bar, text="Branch").pack(side="left", padx=(6, 4))
        self.branch_var = tk.StringVar(value="Marines")
        ttk.Combobox(top_bar, textvariable=self.branch_var, values=BRANCHES,
                     state="readonly", width=11).pack(side="left")

        ttk.Label(top_bar, text="Type").pack(side="left", padx=(12, 4))
        self.type_var = tk.StringVar(value="all")
        ttk.Combobox(top_bar, textvariable=self.type_var, values=TYPES,
                     state="readonly", width=7).pack(side="left")

        ttk.Label(top_bar, text="Max").pack(side="left", padx=(12, 4))
        self.max_var = tk.IntVar(value=25)
        ttk.Spinbox(top_bar, from_=1, to=50, textvariable=self.max_var,
                    width=4).pack(side="left")

        self.search_btn = ttk.Button(top_bar, text="SEARCH", style="Accent.TButton",
                                     command=self.do_search)
        self.search_btn.pack(side="left", padx=(14, 0))

    def _build_main_area(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        # start with the results list a bit wider than the details (drag to resize)
        self.after(50, lambda: paned.sashpos(0, int(self.winfo_width() * 0.56)))

        # left: results table
        left = ttk.Frame(paned, style="Panel.TFrame")
        cols = ("date", "type", "title", "unit")
        self.tree = ttk.Treeview(left, columns=cols, show="headings",
                                 selectmode="browse")
        for col, text, width, stretch in [
            ("date", "Date", 95, False),
            ("type", "Type", 65, False),
            ("title", "Title", 220, True),
            ("unit", "Unit", 150, False),
        ]:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, minwidth=50, stretch=stretch,
                             anchor="w")
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda e: self.open_in_browser())
        paned.add(left, weight=3)

        # right: details
        right = ttk.Frame(paned, style="Panel.TFrame", padding=16)
        self.thumb_label = tk.Label(right, bg=FIELD, fg=MUTED,
                                    width=THUMB_SIZE[0], height=THUMB_SIZE[1])
        self._blank_thumb(text="")
        self.thumb_label.pack(fill="x")

        self.title_label = ttk.Label(right, style="Title.TLabel",
                                     wraplength=THUMB_SIZE[0], justify="left")
        self.title_label.pack(fill="x", pady=(12, 4))
        self.meta_label = ttk.Label(right, style="Muted.TLabel",
                                    wraplength=THUMB_SIZE[0], justify="left")
        self.meta_label.pack(fill="x")
        self.unit_label = ttk.Label(right, style="Panel.TLabel",
                                    wraplength=THUMB_SIZE[0], justify="left")
        self.unit_label.pack(fill="x", pady=(8, 0))
        self.credit_label = ttk.Label(right, style="Muted.TLabel",
                                      wraplength=THUMB_SIZE[0], justify="left")
        self.credit_label.pack(fill="x")

        # button first with side="bottom", so it always stays visible
        self.open_btn = ttk.Button(right, text="OPEN ON DVIDS",
                                   style="Accent.TButton",
                                   command=self.open_in_browser)
        self.open_btn.pack(side="bottom", anchor="w", pady=(10, 0))

        self.desc_text = tk.Text(right, wrap="word", height=4, bg=PANEL, fg=FG,
                                 relief="flat", font=("Segoe UI", 10),
                                 highlightthickness=0, padx=0, pady=8)
        self.desc_text.pack(fill="both", expand=True, pady=(6, 0))
        paned.add(right, weight=2)

    def _build_status_bar(self):
        self.status_var = tk.StringVar(value="Ready. Type something and press Enter.")
        ttk.Label(self, textvariable=self.status_var, style="Status.TLabel",
                  anchor="w").pack(fill="x", side="bottom")

    # ------------------------------------------------------------- background jobs
    def _run_in_background(self, func, callback, *args):
        """Runs func(*args) in a thread so the window doesn't freeze."""
        def worker():
            try:
                self._jobs.put((callback, func(*args), None))
            except Exception as e:  # pylint: disable=broad-exception-caught
                self._jobs.put((callback, None, e))
        threading.Thread(target=worker, daemon=True).start()

    def _poll_jobs(self):
        while not self._jobs.empty():
            callback, result, error = self._jobs.get_nowait()
            callback(result, error)
        self.after(100, self._poll_jobs)

    # ------------------------------------------------------------- search
    def do_search(self):
        """Liest die Eingaben aus und startet die Suche im Hintergrund."""
        query = self.search_var.get().strip()
        branch = None if self.branch_var.get() == "All" else self.branch_var.get()
        media_type = None if self.type_var.get() == "all" else self.type_var.get()
        try:
            max_results = max(1, min(50, int(self.max_var.get())))
        except (tk.TclError, ValueError):
            max_results = 25

        self.search_btn.state(["disabled"])
        self.status_var.set("Searching...")
        self.tree.delete(*self.tree.get_children())
        self._show_details(None)

        self._run_in_background(search, self._on_results,
                                query, branch, media_type, max_results)

    def _on_results(self, results, error):
        self.search_btn.state(["!disabled"])
        if error:
            self.status_var.set(f"Error: {error}")
            messagebox.showerror("Search failed", str(error))
            return

        self.results = list(results or [])
        for i, item in enumerate(self.results):
            self.tree.insert("", "end", iid=str(i), values=(
                _short_date(item),
                item.get("type", ""),
                item.get("title", "(no title)"),
                item.get("unit_name", ""),
            ))
        self.status_var.set(f"{len(self.results)} results")
        if self.results:
            self.tree.selection_set("0")
            self.tree.focus("0")

    # ------------------------------------------------------------- details
    def _on_select(self, _event=None):
        sel = self.tree.selection()
        self._show_details(self.results[int(sel[0])] if sel else None)

    def _show_details(self, item):
        if item is None:
            self.current_url = None
            self.title_label.config(text="No item selected")
            for lbl in (self.meta_label, self.unit_label, self.credit_label):
                lbl.config(text="")
            self._set_description("")
            self._blank_thumb(text="")
            self.open_btn.state(["disabled"])
            return

        self.current_url = item.get("url")
        self.title_label.config(text=item.get("title", "(no title)"))
        meta = [_short_date(item), item.get("type", ""), item.get("branch", "")]
        self.meta_label.config(text="  |  ".join(m for m in meta if m))
        place = ", ".join(p for p in (item.get("city"), item.get("state"),
                                      item.get("country")) if p)
        unit = item.get("unit_name", "")
        self.unit_label.config(text=" - ".join(p for p in (unit, place) if p))
        credit = item.get("credit", "")
        self.credit_label.config(text=f"Credit: {credit}" if credit else "")
        self._set_description(item.get("short_description")
                              or item.get("description") or "")
        self.open_btn.state(["!disabled" if self.current_url else "disabled"])

        thumb_url = item.get("thumbnail")
        if not HAS_PIL:
            self._blank_thumb("Install Pillow to see pictures\n(pip install pillow)")
        elif not thumb_url:
            self._blank_thumb("No picture")
        else:
            self._blank_thumb("Loading picture...")
            self._run_in_background(_download_image, self._on_image, thumb_url)

    def _on_image(self, result, error):
        if error or result is None:
            self._blank_thumb("Picture could not be loaded")
            return
        url, img = result
        sel = self.tree.selection()
        if not sel or self.results[int(sel[0])].get("thumbnail") != url:
            return  # user already clicked something else
        img.thumbnail(THUMB_SIZE)
        self.current_thumb = ImageTk.PhotoImage(img)
        self.thumb_label.config(image=self.current_thumb, text="",
                                width=THUMB_SIZE[0], height=THUMB_SIZE[1])

    def _blank_thumb(self, text):
        self.current_thumb = None
        # width/height are pixels when an image is set, so use an empty image
        self._empty = tk.PhotoImage(width=1, height=1)
        self.thumb_label.config(image=self._empty, text=text, compound="center",
                                width=THUMB_SIZE[0], height=THUMB_SIZE[1],
                                font=("Segoe UI", 10))

    def _set_description(self, text):
        self.desc_text.config(state="normal")
        self.desc_text.delete("1.0", "end")
        self.desc_text.insert("1.0", text)
        self.desc_text.config(state="disabled")

    def open_in_browser(self):
        """Oeffnet das ausgewaehlte Element auf dvidshub.net."""
        if self.current_url:
            webbrowser.open(self.current_url)


# ----------------------------------------------------------------- helpers
def _short_date(item):
    return (item.get("date") or item.get("publishdate") or "")[:10]


def _download_image(url):
    """Tries a bigger version of the DVIDS thumbnail first, then the original."""
    bigger = re.sub(r"/\d+x\d+_q\d+\.", "/600x450_q95.", url)
    for candidate in dict.fromkeys([bigger, url]):   # no duplicates, keeps order
        try:
            with urllib.request.urlopen(candidate, timeout=10) as resp:
                img = Image.open(io.BytesIO(resp.read()))
                img.load()
                return url, img.convert("RGB")
        except Exception:  # pylint: disable=broad-exception-caught
            continue
    raise RuntimeError("image download failed")


if __name__ == "__main__":
    DvidsViewer().mainloop()