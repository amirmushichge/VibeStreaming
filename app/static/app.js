const secretForm = document.querySelector("#secretForm");
const streamForm = document.querySelector("#streamForm");
const logoutBtn = document.querySelector("#logoutBtn");
const stopBtn = document.querySelector("#stopBtn");
const startBtn = document.querySelector("#startBtn");
const copyLinkBtn = document.querySelector("#copyLinkBtn");
const channelSelect = document.querySelector("#channelSelect");

const connectionPill = document.querySelector("#connectionPill");
const secretState = document.querySelector("#secretState");
const accountBox = document.querySelector("#accountBox");
const runState = document.querySelector("#runState");
const streamState = document.querySelector("#streamState");
const videoState = document.querySelector("#videoState");
const recordingState = document.querySelector("#recordingState");
const watchLink = document.querySelector("#watchLink");
const outputsState = document.querySelector("#outputsState");
const logs = document.querySelector("#logs");
const featureNotice = document.querySelector("#featureNotice");
const savedRtmpFields = ["enable_twitch", "twitch_url", "twitch_key", "enable_x", "x_url", "x_key"];

function setBusy(isBusy) {
  startBtn.disabled = isBusy;
  stopBtn.disabled = isBusy;
}

async function postForm(url, form) {
  const body = new FormData(form);
  if (form === streamForm) {
    const twitchToggle = form.elements.enable_twitch;
    const xToggle = form.elements.enable_x;
    body.set("save_recording", form.elements.save_recording.checked ? "true" : "false");
    body.set("channel_id", channelSelect.value || "");
    body.set("enable_twitch", twitchToggle && !twitchToggle.disabled && twitchToggle.checked ? "true" : "false");
    body.set("enable_x", xToggle && !xToggle.disabled && xToggle.checked ? "true" : "false");
  }
  const response = await fetch(url, {
    method: "POST",
    body,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "Request failed");
  }
  return payload;
}

function channelLabel(channel) {
  const handle = channel.customUrl ? ` (${channel.customUrl})` : "";
  return `${channel.title || channel.id}${handle}`;
}

function renderChannels(status) {
  const channels = status.channels || [];
  const previous = channelSelect.value;
  channelSelect.innerHTML = "";

  if (!channels.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No channels connected";
    channelSelect.appendChild(option);
    accountBox.textContent = status.authorized ? "YouTube connected, no channel found" : "No channel connected";
    return;
  }

  for (const channel of channels) {
    const option = document.createElement("option");
    option.value = channel.id;
    option.textContent = channelLabel(channel);
    channelSelect.appendChild(option);
  }

  const activeId = status.active_channel_id || previous || channels[0].id;
  channelSelect.value = channels.some((channel) => channel.id === activeId) ? activeId : channels[0].id;

  const active = channels.find((channel) => channel.id === channelSelect.value);
  if (active) {
    accountBox.textContent = `Selected channel: ${channelLabel(active)}, ID: ${active.id}`;
  }
}

function loadRtmpSettings() {
  for (const name of savedRtmpFields) {
    const field = streamForm.elements[name];
    if (!field) {
      continue;
    }
    if (field.disabled) {
      if (field.type === "checkbox") {
        field.checked = false;
      }
      continue;
    }
    const value = localStorage.getItem(`youtube-live-local:${name}`);
    if (value === null) {
      continue;
    }
    if (field.type === "checkbox") {
      field.checked = value === "true";
    } else {
      field.value = value;
    }
  }
}

function saveRtmpSettings() {
  for (const name of savedRtmpFields) {
    const field = streamForm.elements[name];
    if (!field) {
      continue;
    }
    if (field.disabled) {
      continue;
    }
    localStorage.setItem(
      `youtube-live-local:${name}`,
      field.type === "checkbox" ? String(field.checked) : field.value
    );
  }
}

function setupFileInputs() {
  for (const input of document.querySelectorAll('input[type="file"]')) {
    const wrapper = document.createElement("div");
    const button = document.createElement("button");
    const name = document.createElement("span");

    wrapper.className = "custom-file";
    button.type = "button";
    button.textContent = ">choose_file";
    name.textContent = "No file chosen";

    button.addEventListener("click", () => input.click());
    input.addEventListener("change", () => {
      name.textContent = input.files && input.files.length ? input.files[0].name : "No file chosen";
    });

    input.classList.add("native-file");
    input.insertAdjacentElement("afterend", wrapper);
    wrapper.append(button, name);
  }
}

function appendOutputChip(label, stateText, stateClass) {
  const chip = document.createElement("span");
  const name = document.createElement("span");
  const value = document.createElement("strong");
  chip.className = `output-chip ${stateClass}`;
  name.textContent = label;
  value.textContent = stateText;
  chip.append(name, value);
  outputsState.appendChild(chip);
}

function renderOutputs(current) {
  outputsState.textContent = "";
  const outputs = current.outputs || [];
  const visibleOutputIds = new Set();

  for (const output of outputs) {
    visibleOutputIds.add(output.id);
    const status = (current.output_statuses || {})[output.id] || {};
    appendOutputChip(output.label, status.running ? "RUNNING" : "STOPPED", status.running ? "running" : "stopped");
  }

  if (!visibleOutputIds.has("twitch")) {
    appendOutputChip("TWITCH", "SOON", "soon");
  }
  if (!visibleOutputIds.has("x")) {
    appendOutputChip("X/TWITTER", "SOON", "soon");
  }
}

async function refreshStatus() {
  const response = await fetch("/api/status");
  const status = await response.json();
  const multistreamReady = Boolean(status.features && status.features.multistream);
  if (featureNotice) {
    featureNotice.textContent = multistreamReady
      ? ""
      : "Twitch/X files are present, but they become available after restarting the app. The current stream was not stopped.";
    featureNotice.className = multistreamReady ? "feature-note" : "feature-note visible";
  }

  secretState.textContent = status.client_secret ? "JSON loaded" : "Not configured";
  if (status.channel_error) {
    accountBox.textContent = `Could not read channel: ${status.channel_error}`;
  } else {
    renderChannels(status);
  }

  if (status.authorized) {
    connectionPill.textContent = "YouTube connected";
    connectionPill.className = "status-pill ok";
  } else if (status.client_secret) {
    connectionPill.textContent = "Login required";
    connectionPill.className = "status-pill warn";
  } else {
    connectionPill.textContent = "OAuth JSON required";
    connectionPill.className = "status-pill warn";
  }

  const stream = status.stream;
  const current = stream.current || {};
  runState.textContent = stream.running ? "Live" : "Stopped";
  streamState.textContent = stream.running ? "ffmpeg running" : "Not running";
  videoState.textContent = current.video_path || "None";
  recordingState.textContent =
    current.save_recording === undefined ? "-" : current.save_recording ? "Yes" : "No";
  renderOutputs(current);

  if (current.broadcast_url) {
    watchLink.href = current.broadcast_url;
    watchLink.textContent = current.broadcast_url;
    copyLinkBtn.disabled = false;
  } else {
    watchLink.href = "#";
    watchLink.textContent = "Stream link will appear after launch";
    copyLinkBtn.disabled = true;
  }

  logs.textContent = (stream.logs || []).join("\n");
  logs.scrollTop = logs.scrollHeight;
}

secretForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await postForm("/api/client-secret", secretForm);
    await refreshStatus();
    alert("OAuth JSON loaded. Now click 'Add channel'.");
  } catch (error) {
    alert(error.message);
  }
});

for (const name of savedRtmpFields) {
  const field = streamForm.elements[name];
  if (field) {
    field.addEventListener("change", saveRtmpSettings);
    field.addEventListener("input", saveRtmpSettings);
  }
}

channelSelect.addEventListener("change", async () => {
  if (!channelSelect.value) {
    return;
  }
  const body = new FormData();
  body.set("channel_id", channelSelect.value);
  const response = await fetch("/api/active-channel", {
    method: "POST",
    body,
  });
  const payload = await response.json();
  if (!response.ok) {
    alert(payload.detail || "Could not select channel");
  }
  await refreshStatus();
});

streamForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setBusy(true);
  try {
    const payload = await postForm("/api/start", streamForm);
    await refreshStatus();
    if (payload.broadcast_url) {
      window.open(payload.broadcast_url, "_blank", "noopener,noreferrer");
    }
  } catch (error) {
    alert(error.message);
  } finally {
    setBusy(false);
  }
});

stopBtn.addEventListener("click", async () => {
  setBusy(true);
  try {
    const response = await fetch("/api/stop", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Could not stop stream");
    }
    await refreshStatus();
  } catch (error) {
    alert(error.message);
  } finally {
    setBusy(false);
  }
});

logoutBtn.addEventListener("click", async () => {
  const selected = channelSelect.options[channelSelect.selectedIndex]?.textContent || "selected channel";
  if (!confirm(`Remove connection: ${selected}?`)) {
    return;
  }
  await fetch("/api/logout", { method: "POST" });
  await refreshStatus();
});

copyLinkBtn.addEventListener("click", async () => {
  const href = watchLink.getAttribute("href");
  if (!href || href === "#") {
    return;
  }
  await navigator.clipboard.writeText(href);
  copyLinkBtn.textContent = "Copied";
  setTimeout(() => {
    copyLinkBtn.textContent = "Copy";
  }, 1200);
});

setupFileInputs();
loadRtmpSettings();
refreshStatus();
setInterval(refreshStatus, 2500);
