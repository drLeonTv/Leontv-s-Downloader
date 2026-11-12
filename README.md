# LeonTV Downloader

Eine Desktop-App mit passender Browser-Erweiterung: Video im Browser öffnen, Format auswählen und den Fortschritt in der App sehen. Unterstützt YouTube-Videos und Twitch-VODs; verfügbar sind MP4 und MP3. Bitte lade nur Inhalte herunter, für die du die nötigen Rechte hast und deren Plattformbedingungen dies erlauben.

## Downloads

| Plattform | Download |
| --- | --- |
| Windows | [Desktop-App herunterladen](https://github.com/drLeonTv/Leontv-s-Downloader/releases/latest/download/LeonTV-Downloader-windows.zip) |
| macOS | [Desktop-App herunterladen](https://github.com/drLeonTv/Leontv-s-Downloader/releases/latest/download/LeonTV-Downloader-macos.zip) |
| Linux | [Desktop-App herunterladen](https://github.com/drLeonTv/Leontv-s-Downloader/releases/latest/download/LeonTV-Downloader-linux.zip) |
| Chrome, Brave oder Edge | [Browser-Erweiterung herunterladen](https://github.com/drLeonTv/Leontv-s-Downloader/releases/latest/download/LeonTV-Downloader-Chrome.zip) |

Die Downloads werden bei einem GitHub-Release automatisch gebaut. Die Desktop-App benötigt FFmpeg einschließlich `ffprobe`; falls es noch nicht installiert ist:

- Windows: `winget install Gyan.FFmpeg`
- macOS: `brew install ffmpeg`
- Debian/Ubuntu: `sudo apt install ffmpeg`

Entpacke anschließend das Desktop-Paket und starte **LeonTV-Downloader** (unter Windows `LeonTV-Downloader.exe`). Beim ersten Start richtet die App den Autostart für dein Benutzerkonto ein. Schließen minimiert sie in den System-Tray; zum Beenden nutze dort **Beenden**. Downloads landen standardmäßig unter `~/Downloads/LeonTV-Downloader`. Den Zielordner kannst du mit `LEONTV_DOWNLOAD_DIR` ändern. Wenn FFmpeg nicht über `PATH` gefunden wird, setze `FFMPEG_LOCATION` auf den FFmpeg-Ordner bzw. die ausführbare Datei.

### Browser-Erweiterung installieren

1. Lade das Erweiterungs-ZIP herunter und entpacke es.
2. Öffne `chrome://extensions` (Brave: `brave://extensions`, Edge: `edge://extensions`).
3. Aktiviere **Entwicklermodus** und klicke auf **Entpackte Erweiterung laden**.
4. Wähle den entpackten Ordner mit der `manifest.json` aus.
5. Starte die Desktop-App, öffne ein YouTube-Video oder Twitch-VOD (`/videos/`) und klicke auf das Erweiterungs-Symbol.

Die Desktop-App muss laufen, damit die Erweiterung Downloads übergeben kann. Chrome-basierte Browser installieren ZIP-Erweiterungen nicht direkt; die Schritte oben sind der offizielle lokale Installationsweg. Die Erweiterung erkennt das Video im aktiven Tab und bietet Format, Qualität sowie bei Twitch Start-/Endzeit für Clips an.

## Selbst starten

Benötigt werden Python 3.10 oder neuer, Tkinter und FFmpeg einschließlich `ffprobe`. Installiere die Python-Abhängigkeiten und starte die App aus dem Projektverzeichnis:

```bash
python -m pip install -r desktop/requirements.txt
python -m desktop.app
```

Zum lokalen Laden der Erweiterung wähle den Projektordner `extension/` in deinem Chromium-Browser wie oben beschrieben.

## Entwicklung

Die Desktop-App stellt eine lokale FastAPI-Schnittstelle unter `127.0.0.1:8765` bereit. CORS ist auf Chromium-Erweiterungs-Origins begrenzt. Die Schnittstelle prüft URL, Format und Ausschnitt, bevor yt-dlp den Download startet. Die Größe wird aus verfügbaren Formatmetadaten geschätzt und kann von der tatsächlichen Dateigröße abweichen. Twitch-Clips akzeptieren `MM:SS` oder `HH:MM:SS`; beide Endpunkte müssen angegeben werden. Das Schneiden verwendet FFmpeg und kann je nach Quelle die Ausgabe neu codieren.

```bash
python -m unittest discover -s desktop/tests
```
