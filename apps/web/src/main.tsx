import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/700.css";
import "@mesh2param/ui/tokens.css";
import "@mesh2param/ui/reset.css";
import "@mesh2param/ui/components.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./app.css";

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);

if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js").then(() => navigator.serviceWorker.ready).then((registration) => {
      const urls = [...new Set(performance.getEntriesByType("resource")
        .map((entry) => entry.name)
        .filter((value) => value.startsWith(window.location.origin + "/assets/")))];
      registration.active?.postMessage({ type: "CACHE_URLS", urls });
    }).catch(() => {
      // Browser-local geometry remains available online if persistent caching
      // is disabled by the browser or deployment policy.
    });
  });
}
