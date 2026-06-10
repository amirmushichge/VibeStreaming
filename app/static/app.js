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

const destinationPreset = document.querySelector("#destinationPreset");
const destinationLabel = document.querySelector("#destinationLabel");
const destinationUrl = document.querySelector("#destinationUrl");
const destinationKey = document.querySelector("#destinationKey");
const destinationEnabled = document.querySelector("#destinationEnabled");
const saveDestinationBtn = document.querySelector("#saveDestinationBtn");
const clearDestinationBtn = document.querySelector("#clearDestinationBtn");
const destinationList = document.querySelector("#destinationList");

let rtmpPresets = [];
let rtmpDestinations = [];
let editingDestinationId = "";

function setBusy(isBusy) {
  startBtn.disabled = isBusy;
  stopBtn.disabled = isBusy;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "Request failed");
  }
  return payload;
}

async function postForm(url, form) {
  const body = new FormData(form);
  if (form === streamForm) {
    body.set("save_recording", form.elements.save_recording.checked ? "true" : "false");
    body.set("channel_id", channelSelect.value || "");
    body.set("enable_twitch", "false");
    body.set("enable_x", "false");
  }
  return requestJson(url, {
    method: "POST",
    body,
  });
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

function setupFileInputs() {
  for (const input of document.querySelectorAll('input[type="file"]')) {
    if (input.dataset.customized === "true") {
      continue;
    }
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

    input.dataset.customized = "true";
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

function renderOutputs(current, streamRunning) {
  outputsState.textContent = "";
  const outputs = current.outputs || [];

  if (outputs.length) {
    for (const output of outputs) {
      const status = (current.output_statuses || {})[output.id] || {};
      appendOutputChip(output.label, status.running ? "RUNNING" : "STOPPED", status.running ? "running" : "stopped");
    }
    return;
  }

  appendOutputChip("YOUTUBE", streamRunning ? "RUNNING" : "READY", streamRunning ? "running" : "stopped");
  for (const destination of rtmpDestinations) {
    appendOutputChip(destination.label, destination.enabled ? "READY" : "OFF", destination.enabled ? "ready" : "stopped");
  }
}

function presetLabel(preset) {
  return preset.label || preset.platform || "Custom RTMP";
}

function renderPresetOptions() {
  const previous = destinationPreset.value;
  destinationPreset.innerHTML = "";
  for (const preset of rtmpPresets) {
    const option = document.createElement("option");
    option.value = preset.platform;
    option.textContent = presetLabel(preset);
    destinationPreset.appendChild(option);
  }
  if (rtmpPresets.some((preset) => preset.platform === previous)) {
    destinationPreset.value = previous;
  }
}

function selectedPreset() {
  return rtmpPresets.find((preset) => preset.platform === destinationPreset.value) || rtmpPresets[0] || null;
}

function clearDestinationEditor() {
  editingDestinationId = "";
  const preset = selectedPreset();
  destinationLabel.value = preset ? preset.label : "";
  destinationUrl.value = preset ? preset.server_url : "";
  destinationKey.value = "";
  destinationEnabled.checked = true;
  saveDestinationBtn.textContent = ">save_destination";
}

function editDestination(destination) {
  editingDestinationId = destination.id;
  destinationPreset.value = destination.platform || "custom";
  destinationLabel.value = destination.label || "";
  destinationUrl.value = destination.server_url || "";
  destinationKey.value = "";
  destinationEnabled.checked = Boolean(destination.enabled);
  saveDestinationBtn.textContent = ">update_destination";
}

async function setDestinationEnabled(destination, enabled) {
  await requestJson(`/api/rtmp-destinations/${encodeURIComponent(destination.id)}/enabled`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  await loadDestinations();
  await refreshStatus();
}

function renderDestinationList() {
  destinationList.textContent = "";
  if (!rtmpDestinations.length) {
    const empty = document.createElement("div");
    empty.className = "destination-empty";
    empty.textContent = "No RTMP destinations saved";
    destinationList.appendChild(empty);
    return;
  }

  for (const destination of rtmpDestinations) {
    const item = document.createElement("div");
    const meta = document.createElement("div");
    const title = document.createElement("strong");
    const url = document.createElement("span");
    const key = document.createElement("span");
    const controls = document.createElement("div");
    const toggleLabel = document.createElement("label");
    const toggle = document.createElement("input");
    const toggleText = document.createElement("span");
    const editBtn = document.createElement("button");
    const deleteBtn = document.createElement("button");

    item.className = "destination-item";
    meta.className = "destination-meta";
    controls.className = "destination-controls";
    toggleLabel.className = "check mini-check";

    title.textContent = destination.label;
    url.textContent = destination.server_url;
    key.textContent = destination.has_stream_key ? "Stream key saved" : "Stream key missing";

    toggle.type = "checkbox";
    toggle.checked = Boolean(destination.enabled);
    toggleText.textContent = destination.enabled ? "ON" : "OFF";
    toggle.addEventListener("change", async () => {
      try {
        await setDestinationEnabled(destination, toggle.checked);
      } catch (error) {
        alert(error.message);
        toggle.checked = !toggle.checked;
      }
    });

    editBtn.type = "button";
    editBtn.className = "ghost small";
    editBtn.textContent = ">edit";
    editBtn.addEventListener("click", () => editDestination(destination));

    deleteBtn.type = "button";
    deleteBtn.className = "ghost small";
    deleteBtn.textContent = ">delete";
    deleteBtn.addEventListener("click", async () => {
      if (!confirm(`Delete RTMP destination: ${destination.label}?`)) {
        return;
      }
      try {
        await requestJson(`/api/rtmp-destinations/${encodeURIComponent(destination.id)}`, { method: "DELETE" });
        if (editingDestinationId === destination.id) {
          clearDestinationEditor();
        }
        await loadDestinations();
      } catch (error) {
        alert(error.message);
      }
    });

    meta.append(title, url, key);
    toggleLabel.append(toggle, toggleText);
    controls.append(toggleLabel, editBtn, deleteBtn);
    item.append(meta, controls);
    destinationList.appendChild(item);
  }
}

async function loadDestinations() {
  const payload = await requestJson("/api/rtmp-destinations");
  rtmpPresets = payload.presets || [];
  rtmpDestinations = payload.destinations || [];
  renderPresetOptions();
  if (!editingDestinationId) {
    clearDestinationEditor();
  }
  renderDestinationList();
}

async function refreshStatus() {
  const status = await requestJson("/api/status");
  const multistreamReady = Boolean(status.features && status.features.multistream && status.features.custom_rtmp);
  if (featureNotice) {
    featureNotice.textContent = multistreamReady
      ? ""
      : "Custom RTMP becomes available after restarting the app. The current stream was not stopped.";
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
  renderOutputs(current, stream.running);

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

destinationPreset.addEventListener("change", () => {
  if (editingDestinationId) {
    return;
  }
  clearDestinationEditor();
});

clearDestinationBtn.addEventListener("click", clearDestinationEditor);

saveDestinationBtn.addEventListener("click", async () => {
  const payload = {
    id: editingDestinationId,
    platform: destinationPreset.value,
    label: destinationLabel.value,
    server_url: destinationUrl.value,
    stream_key: destinationKey.value,
    enabled: destinationEnabled.checked,
  };
  try {
    await requestJson("/api/rtmp-destinations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    clearDestinationEditor();
    await loadDestinations();
    await refreshStatus();
  } catch (error) {
    alert(error.message);
  }
});

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
    await requestJson("/api/stop", { method: "POST" });
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
loadDestinations()
  .then(refreshStatus)
  .catch((error) => alert(error.message));
setInterval(refreshStatus, 2500);
