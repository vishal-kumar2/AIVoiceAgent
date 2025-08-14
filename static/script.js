// ---------- Utility: session id in URL ----------
function getSessionId() {
  const url = new URL(window.location.href);
  let sid = url.searchParams.get("session_id");
  if (!sid) {
    sid = crypto.randomUUID();
    url.searchParams.set("session_id", sid);
    window.history.replaceState({}, "", url.toString());
  }
  return sid;
}
const SESSION_ID = getSessionId();
document.getElementById("sessionIdLabel").textContent = `Session: ${SESSION_ID.slice(0,8)}…`;

// ---------- UI refs ----------
const recordBtn = document.getElementById("recordBtn");
const micLabel = document.getElementById("micLabel");
const statusText = document.getElementById("statusText");
const statusDot = document.getElementById("agentStatus");
const convo = document.getElementById("conversationLog");
const replyAudio = document.getElementById("replyAudio");

// ---------- MediaRecorder state ----------
let mediaRecorder = null;
let chunks = [];

// ---------- Conversation helpers ----------
function appendMessage(role, text) {
  const wrapper = document.createElement("div");
  wrapper.className = `msg ${role}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  wrapper.appendChild(bubble);
  convo.appendChild(wrapper);
  convo.scrollTop = convo.scrollHeight;
}

function setStatus(state, label) {
  statusText.textContent = label;
  statusDot.classList.remove("idle", "recording", "playing");
  if (state === "recording") statusDot.classList.add("recording");
  else if (state === "playing") statusDot.classList.add("playing");
}

// ---------- Recording control ----------
async function startRecording() {
  if (mediaRecorder && mediaRecorder.state === "recording") return;

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    chunks = [];

    mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
    mediaRecorder.onstop = async () => {
      const blob = new Blob(chunks, { type: "audio/webm" });

      // build formdata
      const formData = new FormData();
      formData.append("audio_file", blob, `utterance_${Date.now()}.webm`);

      setStatus("idle", "Processing…");
      try {
        const res = await fetch(`/agent/chat/${SESSION_ID}`, { method: "POST", body: formData });

        if (!res.ok) {
          // Try to parse JSON error
          let msg = `Server error: ${res.status}`;
          try { const j = await res.json(); if (j.error) msg = j.error; } catch {}
          throw new Error(msg);
        }

        const data = await res.json();

        // update transcript and history
        if (data.transcription) appendMessage("user", data.transcription);
        if (data.llm_text) appendMessage("assistant", data.llm_text);

        // Play server audio (preferred)
        if (data.audio_url) {
          replyAudio.src = data.audio_url;
          replyAudio.onended = () =>{ // restart recording after playback
          recordBtn.disabled = false;
          recordBtn.classList.remove("recording");
          micLabel.textContent="Start Recording";
          setStatus("idle","Ready");
          };
          setStatus("Playing","Playing reply...");
          await replyAudio.play();
          return;
        }

        // Fallback audio from server
        if (data.fallback_audio_url) {
          replyAudio.src = data.fallback_audio_url;
          replyAudio.onended=()=>{
          recordBtn.disabled = false;
          recordBtn.classList.remove("recording");
          micLabel.textContent="Start Recording";
          setStatus("idle","Ready");
        };
          setStatus("Playing","Playing fallback...")
          await replyAudio.play();
          return;
        }

        // Final fallback: speak plain text with Web Speech if available
        const fbText = data.fallback_text || "I'm having trouble connecting right now.";
        if ("speechSynthesis" in window) {
          const u = new SpeechSynthesisUtterance(fbText);
           u.onend = () => {
            recordBtn.disabled = false;
            recordBtn.classList.remove("recording");
            micLabel.textContent = "Start Recording";
            setStatus("idle", "Ready");
          };
          setStatus("Playing","Speaking fallback...");
          window.speechSynthesis.speak(u);
        } else {
          setStatus("idle", "Fallback message shown.");
          appendMessage("assistant", fbText);
        }
      } catch (err) {
        console.error(err);
        appendMessage("assistant", "⚠️ I'm having trouble connecting right now.");
        // Try local speech fallback
        if ("speechSynthesis" in window) {
          const u = new SpeechSynthesisUtterance("I'm having trouble connecting right now.");
          u.onend = () => toggleRecording(true);
          setStatus("playing", "Speaking fallback…");
          window.speechSynthesis.speak(u);
        } else {
          setStatus("idle", "Error occurred.");
          // Give user control again
          recordBtn.disabled = false;
          recordBtn.classList.remove("recording");
          micLabel.textContent = "Start Recording";
        }
      }
    };

    mediaRecorder.start();
    // UI state
    recordBtn.classList.add("recording");
    recordBtn.setAttribute("aria-pressed", "true");
    micLabel.textContent = "Stop Recording";
    setStatus("recording", "Listening…");
  } catch (err) {
    console.error("Mic error:", err);
    setStatus("idle", "Mic access denied.");
    recordBtn.classList.remove("recording");
    recordBtn.setAttribute("aria-pressed", "false");
    micLabel.textContent = "Start Recording";
    appendMessage("assistant", "⚠️ I can't access your microphone.");
  }
}

function stopRecording() {
  if (!mediaRecorder) return;
  if (mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    recordBtn.classList.remove("recording");
    recordBtn.setAttribute("aria-pressed", "false");
    micLabel.textContent = "Start Recording";
    setStatus("idle", "Processing…");
  }
}

// Toggle helper: if forceStart=true, always start
function toggleRecording(forceStart = false) {
  if (forceStart) {
    startRecording();
    return;
  }
  if (!mediaRecorder || mediaRecorder.state !== "recording") startRecording();
  else stopRecording();
}

// Wire up button
recordBtn.addEventListener("click", () => toggleRecording());

// Optional: start with a friendly prompt in the log
appendMessage("assistant", "Hi! Tap the mic to talk. I’ll reply and keep the conversation going.");
