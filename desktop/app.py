import argparse
import io
import os
import platform
import plistlib
import shlex
import sys
import threading
import tkinter.messagebox
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customtkinter as ctk
import uvicorn
from PIL import Image, ImageDraw
import pystray

from desktop.server import app as api, manager


HOST = "127.0.0.1"
PORT = 8765
APP_NAME = "LeonTV Downloader"


def _startup_command():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--background"]
    return [sys.executable, str(Path(__file__).resolve()), "--background"]


def enable_autostart():
    system = platform.system()
    if system == "Windows":
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(
                key, "LeonTVDownloader", 0, winreg.REG_SZ, subprocess_command()
            )
    elif system == "Darwin":
        folder = Path.home() / "Library" / "LaunchAgents"
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "de.leontv.downloader.plist").open("wb") as file:
            plistlib.dump(
                {
                    "Label": "de.leontv.downloader",
                    "ProgramArguments": _startup_command(),
                    "RunAtLoad": True,
                },
                file,
            )
    elif system == "Linux":
        folder = Path.home() / ".config" / "autostart"
        folder.mkdir(parents=True, exist_ok=True)
        quoted = " ".join(_desktop_quote(arg) for arg in _startup_command())
        (folder / "leontv-downloader.desktop").write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={APP_NAME}\n"
            f"Exec={quoted}\n"
            "Terminal=false\n"
            "X-GNOME-Autostart-enabled=true\n",
            encoding="utf-8",
        )


def subprocess_command():
    import subprocess

    return subprocess.list2cmdline(_startup_command())


def _desktop_quote(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class DownloaderWindow(ctk.CTk):
    def __init__(self, background=False):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("760x590")
        self.minsize(620, 470)
        self.configure(fg_color="#0b0e16")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self._tray = None
        self._closing = False
        self._thumbnail_url = None
        self._thumbnail_image = None
        self._history_signature = None

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(22, 10))
        brand = ctk.CTkFrame(
            header, width=46, height=46, corner_radius=15, fg_color="#705ff5"
        )
        brand.pack(side="left", padx=(0, 12))
        brand.pack_propagate(False)
        ctk.CTkLabel(
            brand, text="L", text_color="white",
            font=ctk.CTkFont(size=24, weight="bold")
        ).pack(expand=True)
        heading = ctk.CTkFrame(header, fg_color="transparent")
        heading.pack(side="left")
        ctk.CTkLabel(
            heading, text="LeonTV Downloader",
            font=ctk.CTkFont(size=22, weight="bold")
        ).pack(anchor="w")
        ctk.CTkLabel(
            heading, text="Deine Downloads. Ein klarer Überblick.",
            text_color="#8e98ad", font=ctk.CTkFont(size=11)
        ).pack(anchor="w", pady=(2, 0))
        self.status_label = ctk.CTkLabel(
            header, text="●  STARTET", text_color="#b7aaff",
            fg_color="#19172d", corner_radius=12,
            font=ctk.CTkFont(size=10, weight="bold")
        )
        self.status_label.pack(side="right", padx=(8, 0), pady=8)

        self.current_card = ctk.CTkFrame(
            self, corner_radius=18, fg_color="#141925",
            border_width=1, border_color="#272e40"
        )
        self.current_card.pack(fill="x", padx=28, pady=(8, 16))
        ctk.CTkLabel(
            self.current_card, text="IN ARBEIT", text_color="#a49aff",
            font=ctk.CTkFont(size=10, weight="bold")
        ).pack(anchor="w", padx=18, pady=(16, 5))
        current_row = ctk.CTkFrame(self.current_card, fg_color="transparent")
        current_row.pack(fill="x", padx=18, pady=4)
        self.thumbnail = ctk.CTkLabel(
            current_row, text="▶", width=104, height=60,
            corner_radius=11, fg_color="#20263a",
            text_color="#9d91ff", font=ctk.CTkFont(size=22)
        )
        self.thumbnail.pack(side="left", padx=(0, 14))
        self.current_title = ctk.CTkLabel(
            current_row, text="Keine aktiven Downloads", anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"), wraplength=540
        )
        self.current_title.pack(side="left", fill="x", expand=True)
        self.progress = ctk.CTkProgressBar(
            self.current_card, height=8, corner_radius=8,
            fg_color="#272d3d", progress_color="#8271ff"
        )
        self.progress.pack(fill="x", padx=18, pady=(12, 8))
        self.progress.set(0)
        self.progress_label = ctk.CTkLabel(
            self.current_card, text="Warte auf deinen nächsten Download",
            text_color="#8e98ad", font=ctk.CTkFont(size=11)
        )
        self.progress_label.pack(anchor="w", padx=18, pady=(0, 16))

        history_header = ctk.CTkFrame(self, fg_color="transparent")
        history_header.pack(fill="x", padx=28, pady=(2, 9))
        ctk.CTkLabel(
            history_header, text="Deine Mediathek",
            font=ctk.CTkFont(size=17, weight="bold")
        ).pack(side="left")
        ctk.CTkButton(
            history_header, text="Ordner öffnen", width=126, height=32,
            corner_radius=10, fg_color="#20263a", hover_color="#2b334b",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._open_download_folder
        ).pack(side="right")
        self.history = ctk.CTkScrollableFrame(
            self, corner_radius=16, fg_color="#111621",
            border_width=1, border_color="#22293a"
        )
        self.history.pack(fill="both", expand=True, padx=28, pady=(0, 18))
        self.protocol("WM_DELETE_WINDOW", self._hide)

        threading.Thread(
            target=lambda: uvicorn.run(api, host=HOST, port=PORT, log_level="warning"),
            name="local-api",
            daemon=True,
        ).start()
        self._start_tray()
        self.after(700, self._refresh)
        if background and self._tray:
            self.withdraw()

    def _start_tray(self):
        try:
            image = Image.new("RGBA", (64, 64), "#5b8cff")
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((8, 8, 56, 56), radius=14, fill="#5b8cff")
            draw.text((22, 15), "L", fill="white")
            menu = pystray.Menu(
                pystray.MenuItem("Öffnen", self._show),
                pystray.MenuItem("Beenden", self._quit),
            )
            self._tray = pystray.Icon("leontv-downloader", image, APP_NAME, menu)
            self._tray.run_detached()
        except Exception:
            self.status_label.configure(text="Tray nicht verfügbar – Fenster bleibt aktiv")

    def _show(self, icon=None, item=None):
        self.after(0, self.deiconify)
        self.after(0, self.lift)

    def _hide(self):
        if self._tray:
            self.withdraw()
        else:
            self.status_label.configure(text="Tray nicht verfügbar – App bleibt geöffnet")

    def _quit(self, icon=None, item=None):
        self._closing = True
        if self._tray:
            self._tray.stop()
        self.after(0, self.destroy)

    def _refresh(self):
        if self._closing:
            return
        jobs = manager.snapshot()
        active = next(
            (job for job in jobs if job["status"] in {"queued", "downloading"}), None
        )
        if active:
            self.current_title.configure(
                text=f'{active["title"]} · {active["format"]}'
            )
            thumbnail_url = active.get("thumbnail")
            if thumbnail_url and thumbnail_url != self._thumbnail_url:
                self._thumbnail_url = thumbnail_url
                threading.Thread(
                    target=self._load_thumbnail,
                    args=(thumbnail_url,),
                    daemon=True,
                ).start()
            percent = active["progress"] / 100
            self.progress.set(percent)
            details = f'{active["progress"]}%'
            if active.get("speed"):
                details += f' · {active["speed"] / 1_000_000:.1f} MB/s'
            if active.get("eta") is not None:
                details += f' · noch {self._format_eta(active["eta"])}'
            self.progress_label.configure(text=details)
        else:
            self.current_title.configure(text="Keine aktiven Downloads")
            self.thumbnail.configure(image=None, text="▶")
            self._thumbnail_image = None
            self._thumbnail_url = None
            self.progress.set(0)
            self.progress_label.configure(text="Warte auf einen Download…")

        history_items = [job for job in jobs[:20] if job["status"] not in {"queued", "downloading"}]
        history_signature = tuple(
            (job["id"], job["status"], job["title"], job["format"], job["error"])
            for job in history_items
        )
        if history_signature != self._history_signature:
            self._render_history(history_items)
            self._history_signature = history_signature
        self.status_label.configure(text="●  ONLINE", text_color="#76d9a8")
        self.after(1200, self._refresh)

    def _render_history(self, jobs):
        for widget in self.history.winfo_children():
            widget.destroy()
        if not jobs:
            ctk.CTkLabel(
                self.history, text="Abgeschlossene Downloads erscheinen hier",
                text_color="#6f7a90", font=ctk.CTkFont(size=12)
            ).pack(pady=32)
            return
        for job in jobs:
            completed = job["status"] == "completed"
            color = "#72d6a5" if completed else "#ff879c"
            title = job["title"]
            if not completed:
                title += f' — {job["error"] or "Fehlgeschlagen"}'
            row = ctk.CTkFrame(
                self.history, corner_radius=11, fg_color="#171d2a",
                border_width=1, border_color="#252d3e"
            )
            row.pack(fill="x", padx=8, pady=(8, 0))
            ctk.CTkLabel(
                row, text="✓" if completed else "!",
                text_color=color,
                width=30, font=ctk.CTkFont(size=15, weight="bold")
            ).pack(side="left", padx=(11, 5), pady=10)
            ctk.CTkLabel(
                row, text=title, text_color="#dce2ed",
                anchor="w", justify="left", wraplength=570,
                font=ctk.CTkFont(size=11)
            ).pack(side="left", fill="x", expand=True, padx=(0, 7), pady=9)
            ctk.CTkLabel(
                row, text=job["format"], text_color="#9a91ff",
                fg_color="#25223c", corner_radius=8,
                font=ctk.CTkFont(size=9, weight="bold")
            ).pack(side="right", padx=10, pady=8)

    def _load_thumbnail(self, url):
        try:
            parsed = urlparse(url)
            host = parsed.hostname or ""
            if parsed.scheme != "https" or not any(
                host == domain or host.endswith(f".{domain}")
                for domain in ("ytimg.com", "ttvnw.net", "jtvnw.net", "twitchcdn.net")
            ):
                return
            request = urllib.request.Request(url, headers={"User-Agent": "LeonTVDownloader/1.0"})
            with urllib.request.urlopen(request, timeout=5) as response:
                data = response.read(2_000_001)
            if len(data) > 2_000_000:
                return
            with Image.open(io.BytesIO(data)) as source:
                if source.width * source.height > 10_000_000:
                    return
                source.thumbnail((100, 56))
                thumbnail = source.convert("RGB")
            image = ctk.CTkImage(
                light_image=thumbnail, dark_image=thumbnail, size=thumbnail.size
            )
            self.after(0, self._set_thumbnail, url, image)
        except Exception:
            return

    def _set_thumbnail(self, url, image):
        if self._closing or url != self._thumbnail_url:
            return
        self._thumbnail_image = image
        self.thumbnail.configure(image=image, text="")

    @staticmethod
    def _format_eta(seconds):
        seconds = max(0, int(seconds))
        return f"{seconds // 60}:{seconds % 60:02d} min"

    @staticmethod
    def _open_download_folder():
        from desktop.downloader import DOWNLOAD_DIR

        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        if platform.system() == "Windows":
            os.startfile(DOWNLOAD_DIR)
        elif platform.system() == "Darwin":
            os.system(f"open {shlex.quote(str(DOWNLOAD_DIR))}")
        else:
            os.system(f"xdg-open {shlex.quote(str(DOWNLOAD_DIR))}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--background", action="store_true")
    args = parser.parse_args()
    try:
        enable_autostart()
    except Exception as error:
        tkinter.messagebox.showwarning(
            APP_NAME, f"Autostart konnte nicht eingerichtet werden:\n{error}"
        )
    window = DownloaderWindow(background=args.background)
    window.mainloop()


if __name__ == "__main__":
    main()
