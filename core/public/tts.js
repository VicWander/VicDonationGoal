const statusEl = document.getElementById("status");
const unlockButton = document.getElementById("unlockButton");

let isPlaying = false;
let pollIntervalMs = 700;
let delayAfterDoneMs = 500;
let loopTimer = null;
let activeAudio = null;
let lastStopToken = null;
let controlTimer = null;
let activeStopResolver = null;
let activeTask = null;
let heartbeatTimer = null;
let lastHeartbeatError = "";

const params = new URLSearchParams(window.location.search);
if (params.get("debug") === "1") {
  document.body.classList.add("debug");
}

function setStatus(text) {
  if (statusEl) statusEl.textContent = text;
}

async function getJson(url) {
  const response = await fetch(
    url + (url.includes("?") ? "&" : "?") + "t=" + Date.now(),
    { cache: "no-store" }
  );
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(result.message || `HTTP ${response.status}`);
  }
  return result;
}

async function postJson(url, data = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
    cache: "no-store"
  });

  const result = await response.json().catch(() => ({ ok: response.ok }));
  if (!response.ok) {
    throw new Error(result.message || `HTTP ${response.status}`);
  }
  return result;
}

async function markDone(task) {
  if (!task?.id) return;
  await postJson("/api/tts/done", { id: task.id });
}

async function markFailed(task, error) {
  if (!task?.id) return;
  try {
    await postJson("/api/tts/fail", {
      id: task.id,
      error: String(error?.message || error || "Audio playback failed")
    });
  } catch (postError) {
    console.error("Failed to report TTS playback error:", postError);
  }
}

function stopActiveAudio() {
  if (!activeAudio) return;
  try {
    activeAudio.pause();
    activeAudio.src = "";
    activeAudio.load();
  } catch {
    // Nothing else to do.
  }
  activeAudio = null;
}


async function watchControlState() {
  try {
    const control = await getJson("/api/tts/control-state");
    const token = Number(control.stopToken || 0);
    if (lastStopToken === null) {
      lastStopToken = token;
      return;
    }
    if (token !== lastStopToken) {
      lastStopToken = token;
      if (activeStopResolver) {
        activeStopResolver();
      }
    }
  } catch {
    // Core may be restarting; the normal polling loop will report it.
  }
}

async function playTask(task) {
  if (!task?.audioUrl) {
    await markFailed(task, "Task has no audioUrl");
    return;
  }

  isPlaying = true;
  activeTask = task;
  await sendPlayerHeartbeat("playing");

  const audioUrl =
    task.audioUrl +
    (task.audioUrl.includes("?") ? "&" : "?") +
    "t=" +
    Date.now();

  const audio = new Audio(audioUrl);
  activeAudio = audio;
  audio.preload = "auto";

  const volume = Number(task.volume);
  audio.volume = Number.isFinite(volume)
    ? Math.max(0, Math.min(volume, 1))
    : 0.9;

  setStatus(
    `TTS: ${task.provider || "provider"} · ${task.text || task.id}`
  );

  controlTimer = setInterval(watchControlState, 400);

  try {
    const playbackResult = await new Promise((resolve, reject) => {
      let settled = false;

      const finish = (handler, value) => {
        if (settled) return;
        settled = true;
        audio.removeEventListener("ended", onEnded);
        audio.removeEventListener("error", onError);
        handler(value);
      };

      const onEnded = () => finish(resolve, "ended");
      const onError = () => {
        const mediaError = audio.error;
        const message = mediaError
          ? `MediaError code ${mediaError.code}`
          : "Unknown audio error";
        finish(reject, new Error(message));
      };

      audio.addEventListener("ended", onEnded);
      audio.addEventListener("error", onError);

      activeStopResolver = () => finish(resolve, "stopped");
      audio.play().catch((error) => finish(reject, error));
    });

    if (playbackResult === "stopped") {
      stopActiveAudio();
      await postJson("/api/tts/skip", { id: task.id });
      setStatus("TTS stopped");
    } else {
      await markDone(task);
      setStatus("TTS completed");
    }
  } catch (error) {
    console.error("TTS playback failed:", error, task);
    setStatus(`TTS playback failed: ${error.message || error}`);
    await markFailed(task, error);
  } finally {
    if (controlTimer) {
      clearInterval(controlTimer);
      controlTimer = null;
    }
    activeStopResolver = null;
    activeTask = null;
    await sendPlayerHeartbeat("waiting");
    stopActiveAudio();
    isPlaying = false;
  }
}

async function sendPlayerHeartbeat(state = "waiting") {
  try {
    await postJson("/api/tts/player-heartbeat", {
      state,
      page: "tts.html",
      visible: document.visibilityState === "visible",
      debug: document.body.classList.contains("debug"),
      currentJobId: activeTask?.id || "",
      currentProvider: activeTask?.provider || "",
      userAgent: navigator.userAgent
    });
    lastHeartbeatError = "";
  } catch (error) {
    lastHeartbeatError = String(error?.message || error || "heartbeat failed");
  }
}

async function pollOnce() {
  if (isPlaying) return;

  try {
    const result = await getJson("/api/tts/next");

    if (result.config) {
      pollIntervalMs =
        Number(result.config.pollIntervalMs) || pollIntervalMs;
      delayAfterDoneMs =
        Number(result.config.delayAfterDoneMs) || delayAfterDoneMs;
    }

    if (!result.ok || !result.task) {
      setStatus(
        result.message ||
          `TTS waiting · ${result.config?.provider || "provider"}`
      );
      return;
    }

    await playTask(result.task);

    if (delayAfterDoneMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, delayAfterDoneMs));
    }
  } catch (error) {
    setStatus(`TTS API unavailable: ${error.message || error}`);
    console.error("TTS poll error:", error);
  }
}

async function loop() {
  clearTimeout(loopTimer);
  await pollOnce();
  loopTimer = setTimeout(loop, Math.max(250, pollIntervalMs));
}

async function unlockAudio() {
  try {
    const context = new (window.AudioContext || window.webkitAudioContext)();
    await context.resume();
    await context.close();
    setStatus("Audio playback unlocked");
    if (unlockButton) unlockButton.hidden = true;
  } catch (error) {
    setStatus(`Audio unlock failed: ${error.message || error}`);
  }
}

if (unlockButton) {
  unlockButton.addEventListener("click", unlockAudio);
}

window.addEventListener("beforeunload", stopActiveAudio);
heartbeatTimer = setInterval(() => sendPlayerHeartbeat(isPlaying ? "playing" : "waiting"), 3000);
sendPlayerHeartbeat("started");
watchControlState();
loop();
