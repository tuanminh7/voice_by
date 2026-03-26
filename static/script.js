const banner = document.getElementById("messageBanner");
const downloadModal = document.getElementById("downloadModal");
const openDownloadModalBtn = document.getElementById("openDownloadModalBtn");
const closeDownloadModalBtn = document.getElementById("closeDownloadModalBtn");
const downloadModalDismissers = [...document.querySelectorAll("[data-close-download-modal]")];

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

openDownloadModalBtn.addEventListener("click", openDownloadModal);
closeDownloadModalBtn.addEventListener("click", closeDownloadModal);

downloadModalDismissers.forEach((element) => {
  element.addEventListener("click", closeDownloadModal);
});

window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeDownloadModal();
  }
});
