const banner = document.getElementById("messageBanner");
const downloadModal = document.getElementById("downloadModal");
const installAndroidBtn = document.getElementById("installAndroidBtn");
const modalInstallAndroidBtn = document.getElementById("modalInstallAndroidBtn");
const openDownloadModalBtn = document.getElementById("openDownloadModalBtn");
const closeDownloadModalBtn = document.getElementById("closeDownloadModalBtn");
const downloadModalDismissers = [...document.querySelectorAll("[data-close-download-modal]")];
const downloadLinks = [...document.querySelectorAll("[data-download-link]")];
const androidInstallButtons = [installAndroidBtn, modalInstallAndroidBtn].filter(Boolean);

let deferredInstallPrompt = null;

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

function openDownloadModal() {
  downloadModal.classList.remove("hidden");
}

function closeDownloadModal() {
  downloadModal.classList.add("hidden");
}

function isStandaloneMode() {
  return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

function updateInstallButtons() {
  const installed = isStandaloneMode();
  const canPromptInstall = Boolean(deferredInstallPrompt);

  androidInstallButtons.forEach((button) => {
    if (installed) {
      button.textContent = "App da duoc cai";
      button.disabled = true;
      return;
    }

    button.disabled = false;
    button.textContent = canPromptInstall ? "Cai app tren Android" : "Huong dan cai tren Android";
  });
}

async function installFromBrowser() {
  if (isStandaloneMode()) {
    showBanner("App nay da duoc cai tren thiet bi nay roi.");
    return;
  }

  if (deferredInstallPrompt) {
    deferredInstallPrompt.prompt();
    await deferredInstallPrompt.userChoice;
    deferredInstallPrompt = null;
    updateInstallButtons();
    return;
  }

  showBanner(
    "Neu Android chua hien popup cai dat, hay mo menu trinh duyet va chon Add to Home Screen hoac Install app."
  );
}

openDownloadModalBtn.addEventListener("click", openDownloadModal);
closeDownloadModalBtn.addEventListener("click", closeDownloadModal);

downloadModalDismissers.forEach((element) => {
  element.addEventListener("click", closeDownloadModal);
});

downloadLinks.forEach((link) => {
  link.addEventListener("click", (event) => {
    if (link.dataset.downloadLink === "android-browser") {
      event.preventDefault();
      installFromBrowser().catch(() => {
        showBanner("Chua mo duoc luong cai dat tu trinh duyet.", "error");
      });
      return;
    }

    const href = link.getAttribute("href") || "";
    if (href && href !== "#") {
      return;
    }

    event.preventDefault();
    showBanner("Nen tang nay chua duoc cau hinh link tai tren server.", "error");
  });
});

androidInstallButtons.forEach((button) => {
  button.addEventListener("click", () => {
    installFromBrowser().catch(() => {
      showBanner("Chua mo duoc luong cai dat tu trinh duyet.", "error");
    });
  });
});

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredInstallPrompt = event;
  updateInstallButtons();
});

window.addEventListener("appinstalled", () => {
  deferredInstallPrompt = null;
  updateInstallButtons();
  closeDownloadModal();
  showBanner("Da cai app thanh cong tren thiet bi nay.");
});

window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeDownloadModal();
  }
});

updateInstallButtons();
