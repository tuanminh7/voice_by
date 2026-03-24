const chatLog = document.getElementById("chatLog");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const voiceBtn = document.getElementById("voiceBtn");
const clearSpeechBtn = document.getElementById("clearSpeechBtn");
const statusText = document.getElementById("statusText");
const avatarFrame = document.getElementById("avatarFrame");

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let isWaitingForReply = false;
let availableVoices = [];
let preferredVietnameseVoice = null;
let missingVietnameseVoiceNotified = false;

function normalizeVoiceLang(lang = "") {
  return lang.toLowerCase().replace(/_/g, "-");
}

function isVietnameseVoice(voice) {
  const lang = normalizeVoiceLang(voice?.lang);
  return lang === "vi-vn" || lang.startsWith("vi");
}

function scoreVietnameseVoice(voice) {
  const lang = normalizeVoiceLang(voice.lang);
  const name = (voice.name || "").toLowerCase();
  let score = 0;

  if (lang === "vi-vn") {
    score += 4;
  } else if (lang.startsWith("vi")) {
    score += 2;
  }

  if (voice.localService) {
    score += 2;
  }

  if (name.includes("vietnam") || name.includes("viet")) {
    score += 1;
  }

  return score;
}

function refreshSpeechVoices() {
  if (!("speechSynthesis" in window)) {
    availableVoices = [];
    preferredVietnameseVoice = null;
    return;
  }

  availableVoices = window.speechSynthesis.getVoices();
  preferredVietnameseVoice = availableVoices
    .filter(isVietnameseVoice)
    .sort((left, right) => scoreVietnameseVoice(right) - scoreVietnameseVoice(left))[0] || null;

  if (preferredVietnameseVoice) {
    missingVietnameseVoiceNotified = false;
  }
}

function waitForVoices(timeoutMs = 1500) {
  return new Promise((resolve) => {
    if (!("speechSynthesis" in window)) {
      resolve(null);
      return;
    }

    refreshSpeechVoices();
    if (preferredVietnameseVoice || availableVoices.length > 0) {
      resolve(preferredVietnameseVoice);
      return;
    }

    let finished = false;
    let previousHandler = null;

    const finish = () => {
      if (finished) {
        return;
      }

      finished = true;
      window.clearTimeout(timerId);

      if (typeof window.speechSynthesis.removeEventListener === "function") {
        window.speechSynthesis.removeEventListener("voiceschanged", handleVoicesChanged);
      } else if (window.speechSynthesis.onvoiceschanged === handleVoicesChanged) {
        window.speechSynthesis.onvoiceschanged = previousHandler;
      }

      refreshSpeechVoices();
      resolve(preferredVietnameseVoice);
    };

    const handleVoicesChanged = () => {
      finish();
    };

    const timerId = window.setTimeout(finish, timeoutMs);

    if (typeof window.speechSynthesis.addEventListener === "function") {
      window.speechSynthesis.addEventListener("voiceschanged", handleVoicesChanged);
    } else {
      previousHandler = window.speechSynthesis.onvoiceschanged;
      window.speechSynthesis.onvoiceschanged = (...args) => {
        if (typeof previousHandler === "function") {
          previousHandler.apply(window.speechSynthesis, args);
        }
        handleVoicesChanged();
      };
    }
  });
}

if ("speechSynthesis" in window) {
  refreshSpeechVoices();

  if (typeof window.speechSynthesis.addEventListener === "function") {
    window.speechSynthesis.addEventListener("voiceschanged", refreshSpeechVoices);
  } else {
    window.speechSynthesis.onvoiceschanged = refreshSpeechVoices;
  }
}

function setStatus(message) {
  statusText.textContent = message;
}

function setAvatarState(state) {
  avatarFrame.classList.remove("is-listening", "is-speaking");
  voiceBtn.classList.remove("is-listening");

  if (state === "listening") {
    avatarFrame.classList.add("is-listening");
    voiceBtn.classList.add("is-listening");
  }

  if (state === "speaking") {
    avatarFrame.classList.add("is-speaking");
  }
}

function createMessage(role, text) {
  const wrapper = document.createElement("article");
  wrapper.className = `message ${role}`;

  const meta = document.createElement("span");
  meta.className = "meta";
  meta.textContent = role === "user" ? "Bạn" : "Trợ lý";

  const body = document.createElement("div");
  body.className = "body";
  body.textContent = text;

  wrapper.append(meta, body);
  chatLog.appendChild(wrapper);

  while (chatLog.children.length > 2) {
    chatLog.removeChild(chatLog.firstElementChild);
  }

  chatLog.scrollTop = chatLog.scrollHeight;
  return body;
}

function setComposerDisabled(disabled) {
  isWaitingForReply = disabled;
  sendBtn.disabled = disabled;
  voiceBtn.disabled = disabled;
  messageInput.disabled = disabled;
}

async function sendMessage(text) {
  const content = text.trim();
  if (!content || isWaitingForReply) {
    return;
  }

  createMessage("user", content);
  const assistantBody = createMessage("assistant", "Đang soạn phản hồi...");
  setComposerDisabled(true);
  setStatus("Đang kết nối Gemini và nhận câu trả lời...");
  setAvatarState("");

  try {
    const response = await fetch("/chat_stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: content })
    });

    if (!response.ok) {
      let errorMessage = "Không gửi được câu hỏi.";
      try {
        const data = await response.json();
        errorMessage = data.error || errorMessage;
      } catch (error) {
        // Keep default error message when body is not JSON.
      }
      assistantBody.textContent = errorMessage;
      setStatus("Co loi khi gui du lieu.");
      return;
    }

    if (!response.body) {
      const plainText = await response.text();
      assistantBody.textContent = plainText.trim() || "Tôi chưa nhận được nội dung phản hồi.";
      setStatus("Đã nhận xong câu trả lời.");
      window.setTimeout(() => speak(assistantBody.textContent), 500);
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let fullText = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      fullText += decoder.decode(value, { stream: true });
      assistantBody.textContent = fullText.trim() || "Đang soạn phản hồi...";
      chatLog.scrollTop = chatLog.scrollHeight;
    }

    fullText += decoder.decode();
    assistantBody.textContent = fullText.trim() || "Tôi chưa nhận được nội dung phản hồi.";
    setStatus("Đã nhận xong câu trả lời.");

    if (assistantBody.textContent.trim()) {
      window.setTimeout(() => speak(assistantBody.textContent), 500);
    }
  } catch (error) {
    assistantBody.textContent = "Có lỗi kết nối đến server. Bạn thử tải lại trang hoặc kiểm tra backend nhé.";
    setStatus("Mất kết nối đến server.");
  } finally {
    setComposerDisabled(false);
    messageInput.value = "";
    messageInput.focus();
  }
}

function startVoice() {
  if (!SpeechRecognition) {
    setStatus("Trình duyệt này chưa hỗ trợ nhận giọng nói.");
    return;
  }

  const recognition = new SpeechRecognition();
  recognition.lang = "vi-VN";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  setStatus("Đang nghe giọng nói của bạn...");
  setAvatarState("listening");

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    messageInput.value = transcript;
    setStatus("Đã nhận giọng nói, đang gửi lên server...");
    setAvatarState("");
    sendMessage(transcript);
  };

  recognition.onerror = () => {
    setStatus("Không nghe rõ gì, bạn thử nói lại giúp tôi nhé.");
    setAvatarState("");
  };

  recognition.onend = () => {
    setAvatarState("");
    if (!isWaitingForReply) {
      setStatus("Sẵn sàng trò chuyện.");
    }
  };

  recognition.start();
}

async function speak(text) {
  if (!("speechSynthesis" in window) || !text.trim()) {
    return;
  }

  await waitForVoices();
  window.speechSynthesis.cancel();
  setAvatarState("speaking");

  if (!preferredVietnameseVoice && !missingVietnameseVoiceNotified) {
    setStatus("Thiết bị chưa có giọng đọc tiếng Việt, ứng dụng đang dùng giọng mặc định.");
    missingVietnameseVoiceNotified = true;
  }

  const sentences = text
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);

  let index = 0;

  function speakNext() {
    if (index >= sentences.length) {
      setAvatarState("");
      if (missingVietnameseVoiceNotified && !preferredVietnameseVoice) {
        setStatus("Máy chưa có voice tiếng Việt nên âm đọc có thể chưa chuẩn.");
      }
      return;
    }

    const utterance = new SpeechSynthesisUtterance(sentences[index]);
    utterance.lang = preferredVietnameseVoice?.lang || "vi-VN";
    if (preferredVietnameseVoice) {
      utterance.voice = preferredVietnameseVoice;
    }
    utterance.rate = 0.88;
    utterance.pitch = 1;
    utterance.onerror = () => {
      setAvatarState("");
      setStatus("Không phát được giọng đọc. Bạn thử tải lại trang giúp tôi nhé.");
    };
    utterance.onend = () => {
      index += 1;
      speakNext();
    };
    window.speechSynthesis.speak(utterance);
  }

  speakNext();
}

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(messageInput.value);
});

voiceBtn.addEventListener("click", startVoice);
clearSpeechBtn.addEventListener("click", () => {
  window.speechSynthesis.cancel();
  setStatus("Đã dừng đọc văn bản.");
  setAvatarState("");
});

createMessage(
  "assistant",
  "Dạ, tôi đã sẵn sàng. Bạn có thể gõ tin nhắn hoặc bấm nút Nói để bắt đầu."
);
