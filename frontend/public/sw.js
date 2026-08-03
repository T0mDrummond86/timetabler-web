/* TAFEtabler mobile viewer service worker.
 *
 * Two caches:
 *   - app shell: the built assets, so the viewer opens with no connection.
 *   - timetables: network-first responses for grids the user has actually
 *     opened, replayed from cache when offline. The page decides how to
 *     present staleness; the worker just records when it stored the copy.
 */
const SHELL_CACHE = "tafetabler-shell-v2";
const DATA_CACHE = "tafetabler-data-v1";
const SHELL_ASSETS = ["/", "/m", "/manifest.webmanifest", "/icon-192.png", "/icon-512.png"];

// Only these reads are worth replaying offline. Anything else (and anything
// that isn't a GET) always goes to the network.
const CACHEABLE_API = [
  /\/sessions\/\d+\/timetable\?/,
  /\/global-sessions\/\d+\/staff$/,
  /\/global-sessions\/\d+$/,
  /\/orgs\/\d+\/global-sessions$/,
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      // One bad URL must not fail the whole install.
      .then((cache) => Promise.allSettled(SHELL_ASSETS.map((u) => cache.add(u))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k !== SHELL_CACHE && k !== DATA_CACHE)
            .map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

function isApiRequest(url) {
  return CACHEABLE_API.some((re) => re.test(url.pathname + url.search));
}

/** Stamp the store time so the page can show "last updated". */
async function cacheWithTimestamp(cache, request, response) {
  const body = await response.clone().blob();
  const headers = new Headers(response.headers);
  headers.set("x-tt-cached-at", new Date().toISOString());
  await cache.put(
    request,
    new Response(body, { status: response.status, statusText: response.statusText, headers }),
  );
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  let url;
  try {
    url = new URL(request.url);
  } catch {
    return;
  }
  if (url.origin !== self.location.origin) return;

  // Timetable data: network first, fall back to the last good copy.
  if (isApiRequest(url)) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(DATA_CACHE);
        try {
          const fresh = await fetch(request);
          // Never cache an auth failure — it would strand the user logged out.
          if (fresh.ok) await cacheWithTimestamp(cache, request, fresh);
          return fresh;
        } catch (err) {
          const cached = await cache.match(request);
          if (cached) return cached;
          throw err;
        }
      })(),
    );
    return;
  }

  // Navigations: serve the shell so a cold offline launch still boots.
  //
  // The stored copy is refreshed on every successful navigation. Without that
  // it would only ever be written at install, and since this file rarely
  // changes there is no reinstall — so the offline fallback would stay pinned
  // to the asset hashes of whichever build was live the first time the viewer
  // was opened, and a slow launch would boot a months-old app.
  if (request.mode === "navigate") {
    event.respondWith(
      (async () => {
        try {
          const fresh = await fetch(request);
          if (fresh.ok) {
            const cache = await caches.open(SHELL_CACHE);
            await cache.put(url.pathname.startsWith("/m") ? "/m" : "/", fresh.clone());
          }
          return fresh;
        } catch {
          const cache = await caches.open(SHELL_CACHE);
          return (await cache.match("/m")) ?? (await cache.match("/")) ?? Response.error();
        }
      })(),
    );
    return;
  }

  // Built assets are content-hashed, so a cache hit is always correct.
  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(SHELL_CACHE);
        const hit = await cache.match(request);
        if (hit) return hit;
        const fresh = await fetch(request);
        if (fresh.ok) await cache.put(request, fresh.clone());
        return fresh;
      })(),
    );
  }
});
