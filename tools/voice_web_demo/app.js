const statusEl = document.getElementById("status");
const transcriptEl = document.getElementById("transcript");
const logEl = document.getElementById("log");
const botEl = document.getElementById("bot");
const waveEl = document.getElementById("wave");
const liveTextEl = document.getElementById("liveText");
const whisperEl = document.getElementById("whisperBtn");
const micPickerEl = document.getElementById("micPicker");
let mediaRecorder = null;
let recordedChunks = [];
let whisperBusy = false;
let selectedMicId = "";

async function populateMicPicker() {
  try {
    if (!window.isSecureContext) {
      log("mic picker unavailable: use localhost or HTTPS for browser microphone access");
      return;
    }
    // Need a one-time mic permission for device labels to populate.
    try {
      const stream = await navigator.mediaDevices.getUserMedia({audio: true});
      stream.getTracks().forEach((track) => track.stop());
    } catch (_permErr) {
      // user may decline; we'll still list devices, just without labels
    }
    const devices = await navigator.mediaDevices.enumerateDevices();
    const mics = devices.filter((device) => device.kind === "audioinput");
    micPickerEl.innerHTML = "";
    const defaultOpt = document.createElement("option");
    defaultOpt.value = "";
    defaultOpt.textContent = "Default microphone";
    micPickerEl.appendChild(defaultOpt);
    mics.forEach((mic, index) => {
      const opt = document.createElement("option");
      opt.value = mic.deviceId;
      opt.textContent = mic.label || `Microphone ${index + 1}`;
      micPickerEl.appendChild(opt);
    });
    log(`mic picker: ${mics.length} input(s) found`);
  } catch (error) {
    log(`mic picker error: ${error.message || error}`);
  }
}

if (micPickerEl) {
  micPickerEl.addEventListener("change", () => {
    selectedMicId = micPickerEl.value;
    log(`mic selected: ${micPickerEl.options[micPickerEl.selectedIndex].textContent}`);
  });
  populateMicPicker();
}
const demoToken = "__CS603_VOICE_DEMO_TOKEN__";

const pixels = [
  "...eee...",
  ".eebbbee.",
  ".ebbbbbe.",
  "ebbbbbbbe",
  "ebbbmbbbe",
  "ebbbbbbbe",
  ".ebbbbbe.",
  ".eebbbee.",
  "...eee..."
];

const bars = 18;
botEl.innerHTML = pixels.flatMap((row) => row.split("")).map((cell) => {
  if (cell === "e") return "<span class='px edge'></span>";
  if (cell === "b") return "<span class='px body'></span>";
  if (cell === "m") return "<span class='px mouth'></span>";
  return "<span class='px'></span>";
}).join("");
waveEl.innerHTML = Array.from({length: bars}, () => "<span class='bar'></span>").join("");

function setMode(mode) {
  botEl.classList.toggle("active", mode === "active");
  botEl.classList.toggle("warn", mode === "warn");
  botEl.classList.toggle("thinking", mode === "thinking");
  waveEl.classList.toggle("thinking", mode === "thinking");
  waveEl.classList.toggle("idle-bars", mode !== "active" && mode !== "thinking");
}

function setStatus(text, color, animateDots) {
  statusEl.textContent = text;
  statusEl.style.color = color;
  statusEl.classList.toggle("dots", !!animateDots);
}

function setLiveText(text, locked) {
  const trimmed = (text || "").trim();
  if (!trimmed) {
    liveTextEl.textContent = liveActive ? "listening..." : "say something";
    liveTextEl.classList.remove("show", "locked");
    return;
  }
  liveTextEl.textContent = trimmed;
  liveTextEl.classList.add("show");
  liveTextEl.classList.toggle("locked", !!locked);
}

function log(line) {
  const time = new Date().toLocaleTimeString();
  logEl.textContent = `[${time}] ${line}\n` + logEl.textContent;
}

function speak(text) {
  const phrase = (text || "").trim();
  if (!phrase || !("speechSynthesis" in window)) return;
  const utterance = new SpeechSynthesisUtterance(phrase);
  utterance.rate = 1;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

async function health() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    statusEl.textContent = data.ok ? "ROS READY" : "BRIDGE ERROR";
    statusEl.style.color = data.ok ? "var(--green)" : "var(--red)";
    if (!data.ok) log(data.error || "health check failed");
  } catch (error) {
    statusEl.textContent = "OFFLINE";
    statusEl.style.color = "var(--red)";
    log(String(error));
  }
}

async function whisperStart() {
  if (whisperBusy || (mediaRecorder && mediaRecorder.state === "recording")) return;
  try {
    if (!window.isSecureContext) {
      throw new Error("browser microphone requires localhost or HTTPS");
    }
    const audioConstraint = selectedMicId ? {deviceId: {exact: selectedMicId}} : true;
    const stream = await navigator.mediaDevices.getUserMedia({audio: audioConstraint});
    recordedChunks = [];
    const opts = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? {mimeType: "audio/webm;codecs=opus"}
      : (MediaRecorder.isTypeSupported("audio/webm") ? {mimeType: "audio/webm"} : {});
    mediaRecorder = new MediaRecorder(stream, opts);
    mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) recordedChunks.push(event.data);
    };
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach((track) => track.stop());
      const mime = mediaRecorder.mimeType || "audio/webm";
      const blob = new Blob(recordedChunks, {type: mime});
      recordedChunks = [];
      await whisperUpload(blob, mime);
    };
    mediaRecorder.start();
    whisperEl.classList.add("on");
    whisperEl.textContent = "Whisper: recording - tap to stop";
    setStatus("RECORDING", "var(--yellow)", true);
    setMode("active");
    setLiveText("", false);
    log("whisper recording started");
  } catch (error) {
    log(`mic error: ${error.message || error}`);
    setStatus("MIC BLOCKED", "var(--red)", false);
    setMode("warn");
  }
}

function whisperStop() {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
  }
}

async function whisperUpload(blob, mime) {
  whisperBusy = true;
  whisperEl.classList.remove("on");
  whisperEl.textContent = "Whisper: transcribing...";
  whisperEl.disabled = true;
  setStatus("TRANSCRIBING", "var(--cyan)", true);
  setMode("thinking");
  try {
    const res = await fetch("/api/transcribe", {
      method: "POST",
      headers: {
        "Content-Type": mime || "audio/webm",
        "X-CS603-Voice-Token": demoToken
      },
      body: blob
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "whisper failed");
    const transcript = (data.transcript || "").trim();
    transcriptEl.value = transcript;
    if (!transcript) {
      setLiveText("(no speech detected)", false);
      setStatus("EMPTY", "var(--yellow)", false);
      setMode("warn");
    } else {
      setLiveText(transcript, true);
      if (data.intent) {
        setStatus(data.intent, "var(--green)", false);
        setMode("active");
        speak(data.speech);
        log(`whisper: ${JSON.stringify(transcript)} -> ${data.intent}`);
      } else {
        setStatus("DONE", "var(--green)", false);
        log(`whisper: ${JSON.stringify(transcript)}`);
      }
      setTimeout(() => {
        setMode("idle");
        setLiveText("", false);
      }, 1800);
    }
  } catch (error) {
    log(`whisper error: ${error.message || error}`);
    setStatus("WHISPER ERR", "var(--red)", false);
    setMode("warn");
  } finally {
    whisperBusy = false;
    whisperEl.disabled = false;
    whisperEl.textContent = "Whisper: tap to record";
  }
}

if (whisperEl) {
  whisperEl.addEventListener("click", () => {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      whisperStop();
    } else {
      whisperStart();
    }
  });
}

// ---- Live VAD mode (continuous mic + auto-send on 1s silence) ----
const liveEl = document.getElementById("liveBtn");
const SPEECH_THRESHOLD = 22;     // 0-255 byte average; tuned to ignore light room noise.
const SILENCE_MS = 1000;         // 1s of silence ends an utterance
const MIN_UTTERANCE_MS = 1200;   // Very short clips produce unreliable transcripts.
const POLL_INTERVAL_MS = 100;
let liveActive = false;
let liveStream = null;
let liveAudioCtx = null;
let liveAnalyser = null;
let liveRecorder = null;
let liveChunks = [];
let liveLoopHandle = null;
let liveSilenceMs = 0;
let liveHadSpeech = false;
let liveUtteranceStart = 0;

async function liveStart() {
  if (liveActive) return;
  try {
    if (!window.isSecureContext) {
      throw new Error("browser microphone requires localhost or HTTPS");
    }
    const audioConstraint = selectedMicId ? {deviceId: {exact: selectedMicId}} : true;
    liveStream = await navigator.mediaDevices.getUserMedia({audio: audioConstraint});
    liveAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const source = liveAudioCtx.createMediaStreamSource(liveStream);
    liveAnalyser = liveAudioCtx.createAnalyser();
    liveAnalyser.fftSize = 1024;
    source.connect(liveAnalyser);
    liveActive = true;
    liveEl.classList.add("on");
    liveEl.textContent = "Live: listening - tap to stop";
    setStatus("LIVE", "var(--yellow)", true);
    setMode("active");
    setLiveText("", false);
    log("live VAD started");
    startLiveUtterance();
    liveLoopHandle = setInterval(monitorLiveLevel, POLL_INTERVAL_MS);
  } catch (error) {
    log(`live mic error: ${error.message || error}`);
    setStatus("MIC BLOCKED", "var(--red)", false);
    setMode("warn");
    liveActive = false;
  }
}

function startLiveUtterance() {
  if (!liveStream || !liveActive) return;
  liveChunks = [];
  liveSilenceMs = 0;
  liveHadSpeech = false;
  liveUtteranceStart = Date.now();
  const opts = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
    ? {mimeType: "audio/webm;codecs=opus"}
    : (MediaRecorder.isTypeSupported("audio/webm") ? {mimeType: "audio/webm"} : {});
  liveRecorder = new MediaRecorder(liveStream, opts);
  liveRecorder.ondataavailable = (event) => {
    if (event.data && event.data.size > 0) liveChunks.push(event.data);
  };
  liveRecorder.onstop = async () => {
    const duration = Date.now() - liveUtteranceStart;
    const mime = liveRecorder.mimeType || "audio/webm";
    const blob = new Blob(liveChunks, {type: mime});
    liveChunks = [];
    if (liveActive && liveHadSpeech && duration >= MIN_UTTERANCE_MS && blob.size > 0) {
      liveTranscribeChunk(blob, mime);
    }
    if (liveActive) startLiveUtterance();
  };
  liveRecorder.start();
}

function monitorLiveLevel() {
  if (!liveAnalyser || !liveActive) return;
  const buf = new Uint8Array(liveAnalyser.frequencyBinCount);
  liveAnalyser.getByteFrequencyData(buf);
  let sum = 0;
  for (let i = 0; i < buf.length; i += 1) sum += buf[i];
  const avg = sum / buf.length;
  if (avg > SPEECH_THRESHOLD) {
    liveSilenceMs = 0;
    if (!liveHadSpeech) {
      liveHadSpeech = true;
      liveUtteranceStart = Date.now();
    }
  } else {
    liveSilenceMs += POLL_INTERVAL_MS;
    if (liveHadSpeech && liveSilenceMs >= SILENCE_MS &&
        liveRecorder && liveRecorder.state === "recording") {
      liveRecorder.stop();
    }
  }
}

async function liveTranscribeChunk(blob, mime) {
  setStatus("TRANSCRIBING", "var(--cyan)", true);
  setMode("thinking");
  try {
    const res = await fetch("/api/transcribe", {
      method: "POST",
      headers: {
        "Content-Type": mime,
        "X-CS603-Voice-Token": demoToken
      },
      body: blob
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "whisper failed");
    const transcript = (data.transcript || "").trim();
    if (transcript) {
      transcriptEl.value = transcript;
      setLiveText(transcript, true);
      if (data.intent) {
        setStatus(data.intent, "var(--green)", false);
        speak(data.speech);
        log(`live: ${JSON.stringify(transcript)} -> ${data.intent}`);
      } else {
        setStatus("DONE", "var(--green)", false);
        log(`live: ${JSON.stringify(transcript)}`);
      }
      setMode("active");
    } else {
      log("live: (empty transcript)");
    }
    if (liveActive) {
      setTimeout(() => {
        if (liveActive) {
          setStatus("LIVE", "var(--yellow)", true);
          setMode("active");
        }
      }, 900);
    }
  } catch (error) {
    log(`live transcribe error: ${error.message || error}`);
    setStatus("ERR", "var(--red)", false);
    setMode("warn");
  }
}

function liveStop() {
  liveActive = false;
  if (liveLoopHandle) { clearInterval(liveLoopHandle); liveLoopHandle = null; }
  if (liveRecorder && liveRecorder.state === "recording") {
    try { liveRecorder.stop(); } catch (_err) { /* ignore */ }
  }
  liveRecorder = null;
  if (liveStream) {
    liveStream.getTracks().forEach((track) => track.stop());
    liveStream = null;
  }
  if (liveAudioCtx) {
    try { liveAudioCtx.close(); } catch (_err) { /* ignore */ }
    liveAudioCtx = null;
  }
  liveAnalyser = null;
  liveEl.classList.remove("on");
  liveEl.textContent = "Live: tap to start";
  setStatus("READY", "var(--green)", false);
  setMode("idle");
  setLiveText("", false);
  log("live VAD stopped");
}

if (liveEl) {
  liveEl.addEventListener("click", () => {
    if (liveActive) liveStop(); else liveStart();
  });
}

health();
