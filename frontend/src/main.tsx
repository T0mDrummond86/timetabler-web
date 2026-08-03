import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { applyTheme, getStoredTheme } from "./lib/theme";
import "./index.css";

applyTheme(getStoredTheme());

// Registered for everyone (it is what makes the mobile viewer installable),
// but it only caches reads — it can never affect an edit.
if ("serviceWorker" in navigator && import.meta.env.PROD) {
  // A worker that takes over mid-session means the page is running code from
  // the previous deploy — reload once so a new release is picked up without
  // the user having to know to refresh. Only when something was already in
  // control: the very first registration is not a stale page.
  const hadController = !!navigator.serviceWorker.controller;
  let reloading = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (!hadController || reloading) return;
    reloading = true;
    window.location.reload();
  });

  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js").catch(() => {
      /* offline support is a bonus; never block the app on it */
    });
  });
}

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
