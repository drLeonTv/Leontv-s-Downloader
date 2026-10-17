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
        self.configure(fg_color="#10141c")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self._tray = None
        self._closing = False
        self._thumbnail_url = None
        self._thumbnail_image = None

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(22, 8))
        ctk.CTkLabel(
            header, text="LeonTV Downloader", font=ctk.CTkFont(size=25, weight="bold")
        ).pack(side="left")
        self.status_label = ctk.CTkLabel(
            header, text="Lokalserver wird gestartet…", text_color="#9ba8bc"
        )
        self.status_label.pack(side="right")

        self.current_card = ctk.CTkFrame(self, corner_radius=16, fg_color="#1a2230")
        self.current_card.pack(fill="x", padx=28, pady=10)
        ctk.CTkLabel(
            self.current_card, text="AKTUELLER DOWNLOAD", text_color="#8f9db3",
            font=ctk.CTkFont(size=11, weight="bold")
        ).pack(anchor="w", padx=18, pady=(16, 4))
        current_row = ctk.CTkFrame(self.current_card, fg_color="transparent")
        current_row.pack(fill="x", padx=18, pady=4)
        self.thumbnail = ctk.CTkLabel(current_row, text="", width=100, height=56)
        self.thumbnail.pack(side="left", padx=(0, 12))
        self.current_title = ctk.CTkLabel(
            current_row, text="Keine aktiven Downloads", anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"), wraplength=550
        )
        self.current_title.pack(side="left", fill="x", expand=True)
        self.progress = ctk.CTkProgressBar(self.current_card, progress_color="#5b8cff")
        self.progress.pack(fill="x", padx=18, pady=8)
        self.progress.set(0)
        self.progress_label = ctk.CTkLabel(
            self.current_card, text="Warte auf einen Download…", text_color="#9ba8bc"
        )
        self.progress_label.pack(anchor="w", padx=18, pady=(0, 16))

        history_header = ctk.CTkFrame(self, fg_color="transparent")
        history_header.pack(fill="x", padx=28, pady=(18, 6))
        ctk.CTkLabel(
            history_header, text="Letzte Downloads", font=ctk.CTkFont(size=18, weight="bold")
        ).pack(side="left")
        ctk.CTkButton(
            history_header, text="Downloads-Ordner öffnen", width=160,
            command=self._open_download_folder
        ).pack(side="right")
        self.history = ctk.CTkScrollableFrame(self, corner_radius=14, fg_color="#1a2230")
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
            self.thumbnail.configure(image=None)
            self._thumbnail_image = None
            self._thumbnail_url = None
            self.progress.set(0)
            self.progress_label.configure(text="Warte auf einen Download…")

        for widget in self.history.winfo_children():
            widget.destroy()
        for job in jobs[:20]:
            if job["status"] in {"queued", "downloading"}:
                continue
            color = "#80d5a0" if job["status"] == "completed" else "#ff8585"
            title = job["title"]
            if job["status"] == "failed":
                title += f' — {job["error"] or "Fehlgeschlagen"}'
            ctk.CTkLabel(
                self.history,
                text=f'{job["format"]}  ·  {title}',
                text_color=color,
                anchor="w",
                wraplength=650,
            ).pack(fill="x", padx=12, pady=7)
        self.status_label.configure(text=f"Bereit · http://{HOST}:{PORT}")
        self.after(1200, self._refresh)

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
