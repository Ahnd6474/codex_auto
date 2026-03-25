const CONSENT_KEY = "codex_auto_analytics_consent";

function loadGoogleAnalytics(measurementId) {
  if (!measurementId) {
    return;
  }
  if (window.__codexAutoGaLoaded) {
    return;
  }
  window.__codexAutoGaLoaded = true;

  const script = document.createElement("script");
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${measurementId}`;
  document.head.appendChild(script);

  window.dataLayer = window.dataLayer || [];
  window.gtag = function gtag() {
    window.dataLayer.push(arguments);
  };
  window.gtag("js", new Date());
  window.gtag("config", measurementId, {
    anonymize_ip: true,
  });
}

function applyAnalyticsConsent() {
  const config = window.CodexAutoAnalytics || {};
  loadGoogleAnalytics(config.gaMeasurementId);
}

function updateBannerVisibility(banner, visible) {
  banner.hidden = !visible;
}

function bootstrapConsent() {
  const banner = document.querySelector("[data-consent-banner]");
  const acceptButton = document.querySelector("[data-consent-accept]");
  const declineButton = document.querySelector("[data-consent-decline]");
  const openButton = document.querySelector("[data-open-consent]");
  if (!banner || !acceptButton || !declineButton || !openButton) {
    return;
  }

  const stored = localStorage.getItem(CONSENT_KEY);
  if (stored === "accepted") {
    applyAnalyticsConsent();
    updateBannerVisibility(banner, false);
  } else if (stored === "declined") {
    updateBannerVisibility(banner, false);
  } else {
    updateBannerVisibility(banner, true);
  }

  acceptButton.addEventListener("click", () => {
    localStorage.setItem(CONSENT_KEY, "accepted");
    applyAnalyticsConsent();
    updateBannerVisibility(banner, false);
  });

  declineButton.addEventListener("click", () => {
    localStorage.setItem(CONSENT_KEY, "declined");
    updateBannerVisibility(banner, false);
  });

  openButton.addEventListener("click", () => {
    localStorage.removeItem(CONSENT_KEY);
    updateBannerVisibility(banner, true);
  });
}

document.addEventListener("DOMContentLoaded", bootstrapConsent);
