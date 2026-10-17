const API = "http://127.0.0.1:8765";
const state = { url: "", platform: "", info: null };

const message = document.querySelector("#message");
const form = document.querySelector("#download-form");
const format = document.querySelector("#format");
const quality = document.querySelector("#quality");
const qualityField = document.querySelector("#quality-field");
const estimate = document.querySelector("#estimate");
const button = document.querySelector("#download");

function showMessage(text, isError = false) {
  message.textContent = text;
  message.classList.toggle("error", isError);
}

function supportedPage(url) {
  let page;
  try {
    page = new URL(url);
  } catch {
    return null;
  }
  if (page.protocol !== "https:") return null;
  const host = page.hostname.toLowerCase();
  if (["youtube.com", "www.youtube.com", "m.youtube.com"].includes(host)) {
    if (
      (page.pathname === "/watch" && page.searchParams.has("v")) ||
      /^\/(shorts|live|embed)\/[^/]+\/?$/.test(page.pathname)
    ) return "youtube";
  }
  if (["youtu.be", "www.youtu.be"].includes(host) && page.pathname.length > 1) {
    return "youtube";
  }
  if (
    ["twitch.tv", "www.twitch.tv", "m.twitch.tv"].includes(host) &&
    /^\/videos\/\d+\/?$/.test(page.pathname)
  ) return "twitch";
  return null;
}

function formatEstimate() {
  if (!state.info) return;
  const size = format.value === "mp3"
    ? state.info.mp3_size_mb
    : state.info.qualities.find((item) => item.value === quality.value)?.size_mb;
  estimate.textContent = size == null
    ? "Dateigröße nicht verfügbar"
    : `Geschätzte Dateigröße: ca. ${size} MB`;
  qualityField.hidden = format.value === "mp3";
}

async function loadCurrentVideo() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  state.url = tab?.url || "";
  state.platform = supportedPage(state.url);
  if (!state.platform) {
    showMessage("Öffne ein YouTube-Video oder ein Twitch-VOD unter /videos/.");
    document.querySelector("#connection").textContent = "nicht verbunden";
    return;
  }
  document.querySelector("#video-url").value = state.url;
  document.querySelector("#clip-fields").hidden = state.platform !== "twitch";
  try {
    const response = await fetch(`${API}/api/info?url=${encodeURIComponent(state.url)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Video-Metadaten konnten nicht geladen werden.");
    state.info = data;
    document.querySelector("#video-title").textContent = data.title;
    format.querySelector('option[value="mp4"]').disabled = !data.mp4_available;
    if (!data.mp4_available) format.value = "mp3";
    quality.replaceChildren(...data.qualities.map((item) => {
      const option = document.createElement("option");
      option.value = item.value;
      option.textContent = item.label;
      return option;
    }));
    form.hidden = false;
    document.querySelector("#connection").textContent = "verbunden";
    showMessage(
      data.mp4_available
        ? "Video erkannt. Format und Qualität auswählen."
        : "Für dieses Video ist nur MP3 verfügbar.",
    );
    formatEstimate();
  } catch (error) {
    document.querySelector("#connection").textContent = "nicht erreichbar";
    showMessage(
      error instanceof TypeError
        ? "Desktop-App nicht erreichbar. Starte die LeonTV-Desktop-App und öffne das Popup erneut."
        : error.message,
      true,
    );
  }
}

format.addEventListener("change", formatEstimate);
quality.addEventListener("change", formatEstimate);
button.addEventListener("click", async () => {
  const start = document.querySelector("#clip-start").value.trim();
  const end = document.querySelector("#clip-end").value.trim();
  if (state.platform === "twitch" && Boolean(start) !== Boolean(end)) {
    showMessage("Für einen Ausschnitt müssen Start- und Endzeit angegeben werden.", true);
    return;
  }
  button.disabled = true;
  showMessage("Download wird an die Desktop-App übergeben…");
  const payload = {
    url: state.url,
    format: format.value,
    quality: quality.value,
    ...(start && end ? { start, end } : {}),
  };
  try {
    const response = await fetch(`${API}/api/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Download konnte nicht gestartet werden.");
    showMessage(`Download gestartet (${format.value.toUpperCase()}). Die App zeigt den Fortschritt an.`);
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    button.disabled = false;
  }
});

loadCurrentVideo().catch((error) => showMessage(error.message, true));
