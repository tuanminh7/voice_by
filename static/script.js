const chatLog = document.getElementById("chatLog");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const voiceBtn = document.getElementById("voiceBtn");
const clearSpeechBtn = document.getElementById("clearSpeechBtn");
const installAppBtn = document.getElementById("installAppBtn");
const installHint = document.getElementById("installHint");
const statusText = document.getElementById("statusText");
const avatarFrame = document.getElementById("avatarFrame");

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let isWaitingForReply = false;
let availableVoices = [];
let preferredVietnameseVoice = null;
let missingVietnameseVoiceNotified = false;
let activeRecognition = null;
let deferredInstallPrompt = null;

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

function setInstallHint(message = "") {
  if (!installHint) {
    return;
  }

  installHint.textContent = message;
  installHint.hidden = !message;
}

function isStandaloneMode() {
  return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

function isIosDevice() {
  return /iPad|iPhone|iPod/.test(window.navigator.userAgent)
    || (window.navigator.platform === "MacIntel" && window.navigator.maxTouchPoints > 1);
}

function isAndroidDevice() {
  return /Android/i.test(window.navigator.userAgent);
}

function isInAppBrowser() {
  return /Zalo|FBAN|FBAV|Instagram|Line|; wv\)|\bwv\b/i.test(window.navigator.userAgent);
}

function isSafariBrowser() {
  const userAgent = window.navigator.userAgent;
  return /Safari/i.test(userAgent) && !/CriOS|FxiOS|EdgiOS|OPiOS|Zalo|FBAN|FBAV|Instagram/i.test(userAgent);
}

function updateInstallButton() {
  if (!installAppBtn) {
    return;
  }

  if (isStandaloneMode()) {
    installAppBtn.hidden = true;
    setInstallHint("Ứng dụng đã được cài trên thiết bị này.");
    return;
  }

  installAppBtn.hidden = false;
  installAppBtn.disabled = false;
  installAppBtn.textContent = "Cài app";

  if (deferredInstallPrompt) {
    setInstallHint("Thiết bị này hỗ trợ cài nhanh. Bạn bấm Cài app để thêm ra màn hình chính.");
    return;
  }

  setInstallHint("");
}

async function handleInstallApp() {
  if (isStandaloneMode()) {
    setInstallHint("Ứng dụng đã được cài trên thiết bị này.");
    return;
  }

  if (deferredInstallPrompt) {
    deferredInstallPrompt.prompt();
    const choiceResult = await deferredInstallPrompt.userChoice;
    deferredInstallPrompt = null;
    updateInstallButton();

    if (choiceResult.outcome === "accepted") {
      setInstallHint("Đang thêm ứng dụng vào màn hình chính của bạn.");
    } else {
      setInstallHint("Bạn có thể bấm lại Cài app bất cứ lúc nào khi muốn.");
    }
    return;
  }

  if (isInAppBrowser()) {
    setInstallHint("Bạn đang mở trong trình duyệt tích hợp của ứng dụng khác. Hãy mở link này bằng Chrome hoặc Safari rồi bấm Cài app.");
    return;
  }

  if (isIosDevice()) {
    if (isSafariBrowser()) {
      setInstallHint("Trên iPhone hoặc iPad, hãy bấm Chia sẻ rồi chọn Thêm vào Màn hình chính.");
    } else {
      setInstallHint("Trên iPhone hoặc iPad, hãy mở link này bằng Safari rồi chọn Chia sẻ và Thêm vào Màn hình chính.");
    }
    return;
  }

  if (isAndroidDevice()) {
    setInstallHint("Nếu chưa thấy cửa sổ cài đặt, bạn mở menu trình duyệt rồi chọn Add to Home screen hoặc Install app.");
    return;
  }

  setInstallHint("Trình duyệt này chưa hiện cửa sổ cài tự động. Bạn thử menu của trình duyệt để tìm mục Install app hoặc Add to Home Screen.");
}

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredInstallPrompt = event;
  updateInstallButton();
});

window.addEventListener("appinstalled", () => {
  deferredInstallPrompt = null;
  updateInstallButton();
  setInstallHint("Đã cài ứng dụng thành công. Bạn có thể mở từ màn hình chính.");
});

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
    setStatus("Trình duyệt này chưa hỗ trợ nhận giọng nói. Trên điện thoại, bạn nên thử Chrome Android.");
    return;
  }

  if (activeRecognition) {
    activeRecognition.abort();
    activeRecognition = null;
  }

  window.speechSynthesis.cancel();

  const recognition = new SpeechRecognition();
  let transcript = "";
  let submitted = false;

  activeRecognition = recognition;
  recognition.lang = "vi-VN";
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  setStatus("Đang nghe giọng nói của bạn...");
  setAvatarState("listening");

  recognition.onresult = (event) => {
    transcript = Array.from(event.results)
      .map((result) => result[0]?.transcript || "")
      .join(" ")
      .trim();

    if (!transcript || submitted) {
      return;
    }

    messageInput.value = transcript;
    submitted = true;
    setStatus("Đã nhận giọng nói, đang gửi lên server...");
    setAvatarState("");
    sendMessage(transcript);
  };

  recognition.onnomatch = () => {
    setStatus("Tôi chưa nhận ra câu nói rõ ràng. Bạn thử nói chậm và gần micro hơn nhé.");
    setAvatarState("");
  };

  recognition.onerror = (event) => {
    const errorMessages = {
      "audio-capture": "Điện thoại chưa dùng được micro. Bạn kiểm tra quyền micro giúp tôi nhé.",
      "network": "Trình duyệt không gửi được giọng nói lên dịch vụ nhận diện. Bạn kiểm tra mạng rồi thử lại nhé.",
      "no-speech": "Tôi chưa nghe thấy tiếng nói rõ ràng. Bạn thử nói lại giúp tôi nhé.",
      "not-allowed": "Trình duyệt đang chặn quyền micro. Bạn hãy bật quyền micro cho trang này.",
      "service-not-allowed": "Thiết bị hoặc trình duyệt này không cho dùng nhận giọng nói từ web.",
      "aborted": "Đã dừng nghe giọng nói."
    };

    setStatus(errorMessages[event.error] || "Không thể nhận giọng nói trên trình duyệt này. Bạn thử Chrome trên Android hoặc nhập tay.");
    setAvatarState("");
  };

  recognition.onend = () => {
    if (activeRecognition === recognition) {
      activeRecognition = null;
    }

    if (!submitted && transcript.trim()) {
      submitted = true;
      messageInput.value = transcript.trim();
      setStatus("Đã nhận giọng nói, đang gửi lên server...");
      sendMessage(transcript.trim());
      return;
    }

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
installAppBtn.addEventListener("click", () => {
  handleInstallApp().catch(() => {
    setInstallHint("Chưa thể mở hộp cài ứng dụng trên thiết bị này. Bạn thử lại hoặc mở bằng Chrome hay Safari.");
  });
});
clearSpeechBtn.addEventListener("click", () => {
  window.speechSynthesis.cancel();
  setStatus("Đã dừng đọc văn bản.");
  setAvatarState("");
});

createMessage(
  "assistant",
  "Dạ, tôi đã sẵn sàng. Bạn có thể gõ tin nhắn hoặc bấm nút Nói để bắt đầu."
);

updateInstallButton();
