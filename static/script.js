const PIN_TOKEN_KEY = "ut_nguyen_pin_token";
const DEVICE_ID_KEY = "ut_nguyen_device_id";

const views = {
  auth: document.getElementById("authView"),
  pinSetup: document.getElementById("pinSetupView"),
  pinUnlock: document.getElementById("pinUnlockView"),
  app: document.getElementById("appView")
};

const banner = document.getElementById("messageBanner");
const welcomeName = document.getElementById("welcomeName");
const pinUnlockName = document.getElementById("pinUnlockName");
const installAppBtn = document.getElementById("installAppBtn");

const authTabButtons = [...document.querySelectorAll("[data-auth-tab]")];
const authPanels = [...document.querySelectorAll("[data-auth-panel]")];
const sectionTabs = [...document.querySelectorAll(".section-tab")];

const sections = {
  chat: document.getElementById("chatSection"),
  family: document.getElementById("familySection"),
  account: document.getElementById("accountSection")
};

const authForms = {
  login: document.getElementById("loginForm"),
  register: document.getElementById("registerForm"),
  forgot: document.getElementById("forgotForm"),
  reset: document.getElementById("resetForm")
};

const pinSetupForm = document.getElementById("pinSetupForm");
const pinUnlockForm = document.getElementById("pinUnlockForm");
const profileForm = document.getElementById("profileForm");
const changePasswordForm = document.getElementById("changePasswordForm");
const createFamilyForm = document.getElementById("createFamilyForm");
const renameFamilyForm = document.getElementById("renameFamilyForm");
const inviteFamilyForm = document.getElementById("inviteFamilyForm");
const logoutBtn = document.getElementById("logoutBtn");

const familySummaryText = document.getElementById("familySummaryText");
const familyMembersList = document.getElementById("familyMembersList");
const familyInvitationsList = document.getElementById("familyInvitationsList");
const renameFamilyInput = document.getElementById("renameFamilyInput");

const chatLog = document.getElementById("chatLog");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const voiceBtn = document.getElementById("voiceBtn");
const clearSpeechBtn = document.getElementById("clearSpeechBtn");
const statusText = document.getElementById("statusText");
const avatarFrame = document.getElementById("avatarFrame");

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

const state = {
  bootstrap: null,
  me: null,
  family: null,
  invitations: [],
  activeSection: "chat",
  isWaitingForReply: false
};

let deferredInstallPrompt = null;
let activeRecognition = null;
let availableVoices = [];
let preferredVietnameseVoice = null;
let missingVietnameseVoiceNotified = false;
let protectedStateRefreshTimer = null;
let isRefreshingProtectedState = false;

function getDeviceId() {
  let deviceId = window.localStorage.getItem(DEVICE_ID_KEY);
  if (!deviceId) {
    deviceId = window.crypto?.randomUUID?.() || `device-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    window.localStorage.setItem(DEVICE_ID_KEY, deviceId);
  }
  return deviceId;
}

function getDeviceName() {
  const platform = window.navigator.platform || "Thiết bị";
  return `${platform} - ${window.navigator.userAgent.slice(0, 60)}`;
}

function getPinToken() {
  return window.sessionStorage.getItem(PIN_TOKEN_KEY) || "";
}

function setPinToken(token) {
  if (!token) {
    window.sessionStorage.removeItem(PIN_TOKEN_KEY);
    return;
  }
  window.sessionStorage.setItem(PIN_TOKEN_KEY, token);
}

function showBanner(message, type = "info") {
  if (!message) {
    banner.textContent = "";
    banner.classList.add("hidden");
    banner.classList.remove("is-error");
    return;
  }

  banner.textContent = message;
  banner.classList.remove("hidden");
  banner.classList.toggle("is-error", type === "error");
}

function setStatus(message) {
  statusText.textContent = message;
}

function setAvatarState(stateName) {
  avatarFrame.classList.remove("is-listening", "is-speaking");
  voiceBtn.classList.remove("is-listening");

  if (stateName === "listening") {
    avatarFrame.classList.add("is-listening");
    voiceBtn.classList.add("is-listening");
  }

  if (stateName === "speaking") {
    avatarFrame.classList.add("is-speaking");
  }
}

function setComposerDisabled(disabled) {
  state.isWaitingForReply = disabled;
  sendBtn.disabled = disabled;
  voiceBtn.disabled = disabled;
  messageInput.disabled = disabled;
}

function showView(viewName) {
  Object.entries(views).forEach(([key, element]) => {
    element.classList.toggle("hidden", key !== viewName);
  });
}

function setAuthTab(tabName) {
  authTabButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.authTab === tabName);
  });

  authPanels.forEach((panel) => {
    panel.classList.toggle("hidden", panel.dataset.authPanel !== tabName);
  });
}

function setSection(sectionName) {
  state.activeSection = sectionName;
  sectionTabs.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.section === sectionName);
  });

  Object.entries(sections).forEach(([key, element]) => {
    element.classList.toggle("hidden", key !== sectionName);
  });
}

function normalizeErrorMessage(error, fallback) {
  return error?.message || fallback;
}

async function requestJson(url, options = {}, authMode = "pin") {
  const headers = {
    ...(options.headers || {})
  };

  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  if (authMode === "pin") {
    const pinToken = getPinToken();
    if (pinToken) {
      headers["X-PIN-Token"] = pinToken;
    }
  }

  const response = await fetch(url, { ...options, headers });
  let data = null;

  try {
    data = await response.json();
  } catch (error) {
    data = null;
  }

  if (!response.ok) {
    const err = new Error(data?.error || "Yêu cầu chưa thành công.");
    err.code = data?.code || "";
    err.status = response.status;
    throw err;
  }

  return data;
}

async function handleProtectedError(error) {
  if (error?.code === "pin_required") {
    setPinToken("");
    showView("pinUnlock");
    showBanner("Bạn hãy nhập PIN để tiếp tục.", "error");
    return true;
  }

  if (error?.code === "pin_not_configured") {
    setPinToken("");
    showView("pinSetup");
    showBanner("Thiết bị này chưa có PIN. Bạn hãy tạo PIN 4 số trước nhé.", "error");
    return true;
  }

  if (error?.code === "auth_required") {
    setPinToken("");
    showView("auth");
    showBanner("Phiên đăng nhập đã hết hoặc đã bị thu hồi.", "error");
    return true;
  }

  return false;
}

function applyBootstrap(bootstrap) {
  state.bootstrap = bootstrap;
  if (bootstrap?.user?.full_name) {
    welcomeName.textContent = bootstrap.user.full_name;
    pinUnlockName.textContent = `${bootstrap.user.full_name}, bạn hãy nhập PIN để vào app.`;
  }
}

function fillProfile(user) {
  if (!user) {
    return;
  }

  document.getElementById("profileFullName").value = user.full_name || "";
  document.getElementById("profileAge").value = user.age || "";
  document.getElementById("profileEmail").value = user.email || "";
  document.getElementById("profilePhone").value = user.phone_number || "";
}

function renderFamilyState() {
  const family = state.family;
  const invitations = state.invitations || [];
  const isAdmin = family?.role === "admin";

  familySummaryText.textContent = family
    ? `${family.family_name} • Vai trò của bạn: ${family.role === "admin" ? "admin" : "thành viên"}`
    : "Bạn chưa tham gia nhóm gia đình nào.";

  createFamilyForm.classList.toggle("hidden", Boolean(family));
  renameFamilyForm.classList.toggle("hidden", !family || !isAdmin);
  inviteFamilyForm.classList.toggle("hidden", !family || !isAdmin);

  if (family) {
    renameFamilyInput.value = family.family_name || "";
  }

  if (!family || !family.members?.length) {
    familyMembersList.className = "list-stack empty-state";
    familyMembersList.textContent = family ? "Nhóm này chưa có thành viên nào." : "Tạo hoặc tham gia nhóm gia đình để thấy danh sách thành viên.";
  } else {
    familyMembersList.className = "list-stack";
    familyMembersList.innerHTML = family.members.map((member) => {
      const roleLabel = member.role === "admin" ? "Admin" : "Thành viên";
      const currentUser = state.me?.user?.id === member.user_id;
      const roleAction = isAdmin
        ? `<button class="inline-btn" data-action="toggle-role" data-member-id="${member.membership_id}" data-role="${member.role === "admin" ? "member" : "admin"}">${member.role === "admin" ? "Hạ xuống member" : "Nâng lên admin"}</button>`
        : "";
      const removeAction = (isAdmin || currentUser)
        ? `<button class="inline-btn danger" data-action="remove-member" data-member-id="${member.membership_id}">${currentUser ? "Rời nhóm" : "Xóa khỏi nhóm"}</button>`
        : "";

      return `
        <article class="list-item">
          <div>
            <strong>${member.full_name}</strong>
            <div class="muted-text">${roleLabel} • ${member.email} • ${member.phone_number}</div>
          </div>
          <div class="list-actions">${roleAction}${removeAction}</div>
        </article>
      `;
    }).join("");
  }

  if (!invitations.length) {
    familyInvitationsList.className = "list-stack empty-state";
    familyInvitationsList.textContent = "Bạn chưa có lời mời nào.";
  } else {
    familyInvitationsList.className = "list-stack";
    familyInvitationsList.innerHTML = invitations.map((invitation) => `
      <article class="list-item">
        <div>
          <strong>${invitation.family_name}</strong>
          <div class="muted-text">Mời bởi ${invitation.invited_by_name}</div>
        </div>
        <div class="list-actions">
          <button class="inline-btn" data-action="respond-invite" data-invitation-id="${invitation.id}" data-response="accept">Chấp nhận</button>
          <button class="inline-btn danger" data-action="respond-invite" data-invitation-id="${invitation.id}" data-response="decline">Từ chối</button>
        </div>
      </article>
    `).join("");
  }
}

function ensureInitialMessage() {
  if (chatLog.children.length) {
    return;
  }

  createMessage("assistant", "Dạ, tôi đã sẵn sàng. Bạn có thể gõ tin nhắn hoặc bấm nút Nói để bắt đầu.");
}

async function loadProtectedState() {
  if (isRefreshingProtectedState) {
    return;
  }

  isRefreshingProtectedState = true;
  try {
    const data = await requestJson("/api/me", { method: "GET" }, "pin");
    state.me = data;
    state.family = data.family;
    state.invitations = data.invitations || [];
    welcomeName.textContent = data.user.full_name || "Người dùng";
    fillProfile(data.user);
    renderFamilyState();
    ensureInitialMessage();
  } catch (error) {
    if (await handleProtectedError(error)) {
      return;
    }
    showBanner(normalizeErrorMessage(error, "Không tải được dữ liệu tài khoản."), "error");
  } finally {
    isRefreshingProtectedState = false;
  }
}

function startProtectedStatePolling() {
  stopProtectedStatePolling();
  protectedStateRefreshTimer = window.setInterval(() => {
    if (document.visibilityState !== "visible" || views.app.classList.contains("hidden")) {
      return;
    }

    loadProtectedState().catch(() => {});
  }, 5000);
}

function stopProtectedStatePolling() {
  if (!protectedStateRefreshTimer) {
    return;
  }

  window.clearInterval(protectedStateRefreshTimer);
  protectedStateRefreshTimer = null;
}

async function bootstrapSession() {
  showBanner("");
  stopProtectedStatePolling();

  try {
    const bootstrap = await requestJson("/api/bootstrap", { method: "GET" }, "none");
    applyBootstrap(bootstrap);

    if (!bootstrap.authenticated) {
      showView("auth");
      setAuthTab("login");
      setPinToken("");
      return;
    }

    if (!bootstrap.pin_configured) {
      showView("pinSetup");
      return;
    }

    if (!getPinToken()) {
      showView("pinUnlock");
      return;
    }

    showView("app");
    setSection(state.activeSection);
    await loadProtectedState();
    startProtectedStatePolling();
  } catch (error) {
    showView("auth");
    setAuthTab("login");
    showBanner(normalizeErrorMessage(error, "Không kết nối được đến hệ thống."), "error");
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
  chatLog.scrollTop = chatLog.scrollHeight;
  return body;
}

function simplifyClientText(value) {
  return (value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function looksLikeCallIntent(text) {
  const simplified = simplifyClientText(text);
  if (!simplified) {
    return false;
  }

  const callKeywords = ["goi", "lien lac", "call"];
  const roleAliases = [
    "con trai",
    "con gai",
    "chau",
    "vo",
    "chong",
    "anh trai",
    "em trai",
    "chi gai",
    "em gai",
    "nguoi nha",
    "nguoi than",
    "gia dinh",
    "chu",
    "bac",
    "co",
    "di",
    "cau",
    "mo",
    "thim"
  ];

  return callKeywords.some((keyword) => simplified.includes(keyword))
    && roleAliases.some((alias) => simplified.includes(alias));
}

async function tryCreateVoiceCall(transcriptText) {
  return requestJson("/api/calls/voice-intent", {
    method: "POST",
    body: JSON.stringify({ transcript_text: transcriptText })
  });
}

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

async function waitForVoices(timeoutMs = 1500) {
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
    const timerId = window.setTimeout(finish, timeoutMs);

    function finish() {
      if (finished) {
        return;
      }

      finished = true;
      window.clearTimeout(timerId);
      if (typeof window.speechSynthesis.removeEventListener === "function") {
        window.speechSynthesis.removeEventListener("voiceschanged", finish);
      }
      refreshSpeechVoices();
      resolve(preferredVietnameseVoice);
    }

    if (typeof window.speechSynthesis.addEventListener === "function") {
      window.speechSynthesis.addEventListener("voiceschanged", finish);
    }
  });
}

if ("speechSynthesis" in window) {
  refreshSpeechVoices();
  if (typeof window.speechSynthesis.addEventListener === "function") {
    window.speechSynthesis.addEventListener("voiceschanged", refreshSpeechVoices);
  }
}

async function speak(text) {
  if (!("speechSynthesis" in window) || !text.trim()) {
    return;
  }

  await waitForVoices();
  window.speechSynthesis.cancel();
  setAvatarState("speaking");

  if (!preferredVietnameseVoice && !missingVietnameseVoiceNotified) {
    setStatus("Thiết bị chưa có giọng đọc tiếng Việt, ứng dụng sẽ dùng giọng mặc định.");
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
      return;
    }

    const utterance = new SpeechSynthesisUtterance(sentences[index]);
    utterance.lang = preferredVietnameseVoice?.lang || "vi-VN";
    if (preferredVietnameseVoice) {
      utterance.voice = preferredVietnameseVoice;
    }
    utterance.rate = 0.9;
    utterance.onend = () => {
      index += 1;
      speakNext();
    };
    utterance.onerror = () => {
      setAvatarState("");
      setStatus("Không phát được giọng đọc. Bạn thử lại giúp tôi nhé.");
    };
    window.speechSynthesis.speak(utterance);
  }

  speakNext();
}

async function sendMessage(text) {
  const content = text.trim();
  if (!content || state.isWaitingForReply) {
    return;
  }

  createMessage("user", content);
  const assistantBody = createMessage("assistant", "Đang soạn phản hồi...");
  setComposerDisabled(true);
  setStatus("Đang kết nối Gemini và nhận câu trả lời...");
  setAvatarState("");

  try {
    if (looksLikeCallIntent(content)) {
      setStatus("Đang xử lý lệnh gọi...");

      try {
        const callData = await tryCreateVoiceCall(content);
        if (callData?.action === "calling") {
          assistantBody.textContent = callData.message || "Đang thực hiện cuộc gọi cho bác.";
          setStatus("Đã tạo cuộc gọi.");
          await loadProtectedState();
          if (assistantBody.textContent.trim()) {
            window.setTimeout(() => speak(assistantBody.textContent), 300);
          }
          return;
        }

        if (callData?.action === "confirm") {
          assistantBody.textContent = callData.question || "Bác muốn gọi ai ạ?";
          setStatus("Bạn hãy xác nhận người cần gọi.");
          if (assistantBody.textContent.trim()) {
            window.setTimeout(() => speak(assistantBody.textContent), 300);
          }
          return;
        }
      } catch (error) {
        if (error?.code && error.code !== "call_target_not_found") {
          throw error;
        }

        assistantBody.textContent = normalizeErrorMessage(error, "Tôi chưa tạo được cuộc gọi này.");
        setStatus("Lệnh gọi chưa thực hiện được.");
        if (assistantBody.textContent.trim()) {
          window.setTimeout(() => speak(assistantBody.textContent), 300);
        }
        return;
      }
    }

    const response = await fetch("/chat_stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-PIN-Token": getPinToken()
      },
      body: JSON.stringify({ message: content })
    });

    if (!response.ok) {
      let errorData = null;
      try {
        errorData = await response.json();
      } catch (error) {
        errorData = null;
      }

      const err = new Error(errorData?.error || "Không gửi được câu hỏi.");
      err.code = errorData?.code || "";
      if (await handleProtectedError(err)) {
        assistantBody.textContent = "Phiên mở khóa đã hết. Bạn nhập lại PIN rồi thử tiếp nhé.";
        return;
      }
      assistantBody.textContent = err.message;
      return;
    }

    const reader = response.body?.getReader();
    if (!reader) {
      assistantBody.textContent = "Tôi chưa nhận được nội dung phản hồi.";
      return;
    }

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
      window.setTimeout(() => speak(assistantBody.textContent), 300);
    }
  } catch (error) {
    assistantBody.textContent = normalizeErrorMessage(error, "Có lỗi kết nối đến server.");
    setStatus("Mất kết nối đến server.");
  } finally {
    setComposerDisabled(false);
    messageInput.value = "";
    messageInput.focus();
  }
}

function startVoice() {
  if (!SpeechRecognition) {
    setStatus("Trình duyệt này chưa hỗ trợ nhận giọng nói. Bạn nên thử Chrome trên Android.");
    return;
  }

  if (activeRecognition) {
    activeRecognition.abort();
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

  recognition.onerror = () => {
    setStatus("Tôi chưa nghe được rõ. Bạn thử nói chậm và gần micro hơn nhé.");
    setAvatarState("");
  };

  recognition.onend = () => {
    if (activeRecognition === recognition) {
      activeRecognition = null;
    }
    setAvatarState("");
    if (!state.isWaitingForReply) {
      setStatus("Sẵn sàng trò chuyện.");
    }
  };

  recognition.start();
}

function isStandaloneMode() {
  return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

function updateInstallButton() {
  if (isStandaloneMode()) {
    installAppBtn.classList.add("hidden");
    return;
  }
  installAppBtn.classList.remove("hidden");
}

async function handleInstallApp() {
  if (deferredInstallPrompt) {
    deferredInstallPrompt.prompt();
    await deferredInstallPrompt.userChoice;
    deferredInstallPrompt = null;
    updateInstallButton();
    return;
  }

  showBanner("Nếu trình duyệt chưa hiện hộp cài đặt, bạn hãy mở menu rồi chọn Add to Home Screen hoặc Install app.");
}

async function submitLogin(event) {
  event.preventDefault();
  showBanner("");

  const payload = {
    identifier: document.getElementById("loginIdentifier").value.trim(),
    password: document.getElementById("loginPassword").value,
    device_id: getDeviceId(),
    device_name: getDeviceName()
  };

  try {
    const data = await requestJson("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(payload)
    }, "none");
    applyBootstrap(data.bootstrap);
    setPinToken("");
    showBanner(data.message);
    showView(data.bootstrap.pin_configured ? "pinUnlock" : "pinSetup");
    authForms.login.reset();
  } catch (error) {
    showBanner(normalizeErrorMessage(error, "Đăng nhập chưa thành công."), "error");
  }
}

async function submitRegister(event) {
  event.preventDefault();
  showBanner("");

  const payload = {
    full_name: document.getElementById("registerFullName").value.trim(),
    age: document.getElementById("registerAge").value.trim(),
    email: document.getElementById("registerEmail").value.trim(),
    phone_number: document.getElementById("registerPhone").value.trim(),
    password: document.getElementById("registerPassword").value,
    device_id: getDeviceId(),
    device_name: getDeviceName()
  };

  try {
    const data = await requestJson("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(payload)
    }, "none");
    applyBootstrap(data.bootstrap);
    setPinToken("");
    showBanner(data.message);
    showView("pinSetup");
    authForms.register.reset();
  } catch (error) {
    showBanner(normalizeErrorMessage(error, "Tạo tài khoản chưa thành công."), "error");
  }
}

async function submitForgotPassword(event) {
  event.preventDefault();
  showBanner("");

  try {
    const data = await requestJson("/api/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email: document.getElementById("forgotEmail").value.trim() })
    }, "none");

    if (data.reset_token) {
      document.getElementById("resetToken").value = data.reset_token;
      setAuthTab("reset");
      showBanner(`${data.message} Mã reset: ${data.reset_token}`);
    } else {
      showBanner(data.message);
    }
  } catch (error) {
    showBanner(normalizeErrorMessage(error, "Không tạo được mã đặt lại."), "error");
  }
}

async function submitResetPassword(event) {
  event.preventDefault();
  showBanner("");

  try {
    const data = await requestJson("/api/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({
        token: document.getElementById("resetToken").value.trim(),
        new_password: document.getElementById("resetPassword").value
      })
    }, "none");
    showBanner(data.message);
    setAuthTab("login");
    authForms.reset.reset();
  } catch (error) {
    showBanner(normalizeErrorMessage(error, "Đặt lại mật khẩu chưa thành công."), "error");
  }
}

async function submitPinSetup(event) {
  event.preventDefault();
  showBanner("");

  try {
    const data = await requestJson("/api/auth/pin/setup", {
      method: "POST",
      body: JSON.stringify({
        pin: document.getElementById("pinSetupValue").value,
        confirm_pin: document.getElementById("pinSetupConfirm").value
      })
    }, "none");
    setPinToken(data.pin_token);
    applyBootstrap(data.bootstrap);
    pinSetupForm.reset();
    showView("app");
    setSection(state.activeSection);
    showBanner(data.message);
    await loadProtectedState();
    startProtectedStatePolling();
  } catch (error) {
    showBanner(normalizeErrorMessage(error, "Thiết lập PIN chưa thành công."), "error");
  }
}

async function submitPinUnlock(event) {
  event.preventDefault();
  showBanner("");

  try {
    const data = await requestJson("/api/auth/pin/verify", {
      method: "POST",
      body: JSON.stringify({ pin: document.getElementById("pinUnlockValue").value })
    }, "none");
    setPinToken(data.pin_token);
    pinUnlockForm.reset();
    showView("app");
    setSection(state.activeSection);
    showBanner(data.message);
    await loadProtectedState();
    startProtectedStatePolling();
  } catch (error) {
    showBanner(normalizeErrorMessage(error, "PIN chưa đúng."), "error");
  }
}

async function submitProfile(event) {
  event.preventDefault();
  showBanner("");

  try {
    const data = await requestJson("/api/me", {
      method: "PATCH",
      body: JSON.stringify({
        full_name: document.getElementById("profileFullName").value.trim(),
        age: document.getElementById("profileAge").value.trim(),
        email: document.getElementById("profileEmail").value.trim(),
        phone_number: document.getElementById("profilePhone").value.trim()
      })
    });
    state.me = { ...state.me, user: data.user };
    welcomeName.textContent = data.user.full_name;
    showBanner(data.message);
  } catch (error) {
    if (await handleProtectedError(error)) {
      return;
    }
    showBanner(normalizeErrorMessage(error, "Không cập nhật được hồ sơ."), "error");
  }
}

async function submitChangePassword(event) {
  event.preventDefault();
  showBanner("");

  try {
    const data = await requestJson("/api/me/change-password", {
      method: "POST",
      body: JSON.stringify({
        new_password: document.getElementById("changePasswordValue").value,
        confirm_password: document.getElementById("changePasswordConfirm").value
      })
    });
    changePasswordForm.reset();
    showBanner(data.message);
  } catch (error) {
    if (await handleProtectedError(error)) {
      return;
    }
    showBanner(normalizeErrorMessage(error, "Không đổi được mật khẩu."), "error");
  }
}

async function submitCreateFamily(event) {
  event.preventDefault();
  showBanner("");

  try {
    const data = await requestJson("/api/families", {
      method: "POST",
      body: JSON.stringify({ family_name: document.getElementById("familyNameInput").value.trim() })
    });
    state.family = data.family;
    state.invitations = [];
    createFamilyForm.reset();
    renderFamilyState();
    showBanner(data.message);
  } catch (error) {
    if (await handleProtectedError(error)) {
      return;
    }
    showBanner(normalizeErrorMessage(error, "Không tạo được nhóm gia đình."), "error");
  }
}

async function submitRenameFamily(event) {
  event.preventDefault();
  showBanner("");

  try {
    const data = await requestJson("/api/families/current", {
      method: "PATCH",
      body: JSON.stringify({ family_name: renameFamilyInput.value.trim() })
    });
    state.family = data.family;
    renderFamilyState();
    showBanner(data.message);
  } catch (error) {
    if (await handleProtectedError(error)) {
      return;
    }
    showBanner(normalizeErrorMessage(error, "Không đổi được tên nhóm."), "error");
  }
}

async function submitInviteFamily(event) {
  event.preventDefault();
  showBanner("");

  try {
    const data = await requestJson("/api/families/current/invitations", {
      method: "POST",
      body: JSON.stringify({ identifier: document.getElementById("inviteIdentifier").value.trim() })
    });
    inviteFamilyForm.reset();
    showBanner(data.message);
    await loadProtectedState();
  } catch (error) {
    if (await handleProtectedError(error)) {
      return;
    }
    showBanner(normalizeErrorMessage(error, "Không gửi được lời mời."), "error");
  }
}

async function handleFamilyAction(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) {
    return;
  }

  const action = button.dataset.action;
  showBanner("");

  try {
    if (action === "respond-invite") {
      const data = await requestJson(`/api/families/invitations/${button.dataset.invitationId}/respond`, {
        method: "POST",
        body: JSON.stringify({ action: button.dataset.response })
      });
      showBanner(data.message);
      await loadProtectedState();
      return;
    }

    if (action === "toggle-role") {
      const data = await requestJson(`/api/families/current/members/${button.dataset.memberId}/role`, {
        method: "PATCH",
        body: JSON.stringify({ role: button.dataset.role })
      });
      state.family = data.family;
      renderFamilyState();
      showBanner(data.message);
      return;
    }

    if (action === "remove-member") {
      const data = await requestJson(`/api/families/current/members/${button.dataset.memberId}`, {
        method: "DELETE"
      });
      state.family = data.family;
      renderFamilyState();
      showBanner(data.message);
      await loadProtectedState();
    }
  } catch (error) {
    if (await handleProtectedError(error)) {
      return;
    }
    showBanner(normalizeErrorMessage(error, "Thao tác gia đình chưa thành công."), "error");
  }
}

async function logout() {
  if (!window.confirm("Bạn có chắc muốn đăng xuất khỏi thiết bị này không?")) {
    return;
  }

  try {
    const data = await requestJson("/api/auth/logout", { method: "POST" }, "none");
    stopProtectedStatePolling();
    setPinToken("");
    state.me = null;
    state.family = null;
    state.invitations = [];
    showView("auth");
    setAuthTab("login");
    showBanner(data.message);
  } catch (error) {
    showBanner(normalizeErrorMessage(error, "Đăng xuất chưa thành công."), "error");
  }
}

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredInstallPrompt = event;
  updateInstallButton();
});

window.addEventListener("appinstalled", () => {
  deferredInstallPrompt = null;
  updateInstallButton();
});

authTabButtons.forEach((button) => {
  button.addEventListener("click", () => setAuthTab(button.dataset.authTab));
});

sectionTabs.forEach((button) => {
  button.addEventListener("click", () => setSection(button.dataset.section));
});

authForms.login.addEventListener("submit", submitLogin);
authForms.register.addEventListener("submit", submitRegister);
authForms.forgot.addEventListener("submit", submitForgotPassword);
authForms.reset.addEventListener("submit", submitResetPassword);
pinSetupForm.addEventListener("submit", submitPinSetup);
pinUnlockForm.addEventListener("submit", submitPinUnlock);
profileForm.addEventListener("submit", submitProfile);
changePasswordForm.addEventListener("submit", submitChangePassword);
createFamilyForm.addEventListener("submit", submitCreateFamily);
renameFamilyForm.addEventListener("submit", submitRenameFamily);
inviteFamilyForm.addEventListener("submit", submitInviteFamily);
familyMembersList.addEventListener("click", handleFamilyAction);
familyInvitationsList.addEventListener("click", handleFamilyAction);

logoutBtn.addEventListener("click", logout);
chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(messageInput.value);
});
voiceBtn.addEventListener("click", startVoice);
clearSpeechBtn.addEventListener("click", () => {
  window.speechSynthesis.cancel();
  setAvatarState("");
  setStatus("Đã dừng đọc văn bản.");
});
installAppBtn.addEventListener("click", () => {
  handleInstallApp().catch(() => {
    showBanner("Chưa thể mở hộp cài ứng dụng trên thiết bị này.", "error");
  });
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && !views.app.classList.contains("hidden")) {
    loadProtectedState().catch(() => {});
  }
});

window.addEventListener("focus", () => {
  if (!views.app.classList.contains("hidden")) {
    loadProtectedState().catch(() => {});
  }
});

updateInstallButton();
bootstrapSession();
