# LeonTV Downloader

Desktop-App und Chromium-Erweiterung zum Herunterladen unterstützter YouTube-Videos und Twitch-VODs. Es werden ausschließlich MP4 (Video) und MP3 (Audio) angeboten. Bitte lade nur Inhalte herunter, für die du die nötigen Rechte hast und deren Plattformbedingungen dies erlauben.

## Architektur und Dateien

```text
desktop/
  app.py                 CustomTkinter-Dashboard, Tray und Autostart
  server.py              lokale FastAPI-Endpunkte und Download-Warteschlange
  downloader.py          yt-dlp, Format-/Größenschätzung und VOD-Ausschnitte
  requirements.txt       Python-Abhängigkeiten
  tests/test_downloader.py
extension/
  manifest.json          Chromium Manifest V3-Konfiguration
  popup.html             Popup-Oberfläche
  popup.css              Dark-Mode-Design
  popup.js               Tab-Erkennung und API-Aufrufe
```

Das Popup erkennt das aktive YouTube-Video oder Twitch-VOD, fragt Titel, Qualitäten und Dateigrößenschätzungen beim lokalen Server ab und sendet den Downloadauftrag an `127.0.0.1:8765`. FastAPI prüft URL, Format und Ausschnitt, bevor yt-dlp den Download in einem Hintergrund-Thread startet. Die Desktop-App zeigt Titel, Vorschaubild, Fortschritt, Geschwindigkeit, Restzeit und die zuletzt abgeschlossenen Downloads. Der Server bindet ausschließlich an Loopback; CORS ist auf Chromium-Erweiterungs-Origins begrenzt.

## Voraussetzungen und Start

Benötigt werden Python 3.10 oder neuer, Tkinter und FFmpeg einschließlich `ffprobe`. Auf Debian/Ubuntu installiere Tkinter bei Bedarf mit `sudo apt install python3-tk`.

1. Installiere FFmpeg:
   - Windows: `winget install Gyan.FFmpeg`
   - macOS: `brew install ffmpeg`
   - Debian/Ubuntu: `sudo apt install ffmpeg`
2. Installiere die Python-Pakete aus dem Projektverzeichnis:

   ```bash
   python -m pip install -r desktop/requirements.txt
   ```

3. Starte die Desktop-App aus dem Projektverzeichnis:

   ```bash
   python -m desktop.app
   ```

   Beim ersten Start wird der Autostart für dein Benutzerkonto eingerichtet. Schließen minimiert das Fenster in den System-Tray; zum Beenden nutze dort **Beenden**. Downloads landen standardmäßig unter `~/Downloads/LeonTV-Downloader`. Den Zielordner kannst du mit `LEONTV_DOWNLOAD_DIR` ändern. Wenn FFmpeg nicht über `PATH` gefunden wird, setze `FFMPEG_LOCATION` auf den FFmpeg-Ordner bzw. die ausführbare Datei.

4. Installiere die Erweiterung in Chrome oder Brave:
   - Öffne `chrome://extensions` (in Brave `brave://extensions`).
   - Aktiviere **Entwicklermodus**, wähle **Entpackte Erweiterung laden** und wähle den Ordner `extension/`.
   - Öffne ein YouTube-Video oder Twitch-VOD (`/videos/…`) und anschließend das Erweiterungs-Popup.

Die Desktop-App muss laufen, damit die Erweiterung Downloads übergeben kann. Die Größe wird aus den verfügbaren yt-dlp-Formatmetadaten geschätzt und kann von der tatsächlichen Dateigröße abweichen. Twitch-Ausschnitte akzeptieren Zeitangaben im Format `MM:SS` oder `HH:MM:SS`; beide Endpunkte müssen angegeben werden. Das Schneiden verwendet FFmpeg und kann je nach Quelle die Ausgabe neu codieren.

## Tests

```bash
python -m unittest discover -s desktop/tests
```
