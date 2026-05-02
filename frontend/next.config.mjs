import withPWAInit from "@ducanh2912/next-pwa";

/**
 * PWA configuration.
 *
 * Caching policy:
 *  - /auth/*, /broker, /broker/*, /me, /me/*, /aurum/* (Phase 4) → NetworkOnly,
 *    NEVER cached. We never want stale auth state, broker state, or AURUM data.
 *  - /_next/static/*, /_next/image/*, fonts, images → CacheFirst with revalidation.
 *  - Everything else (HTML pages) → NetworkFirst with offline fallback.
 *
 * The plugin auto-generates the service worker at build time and registers it.
 * skipWaiting + clientsClaim → silent updates on next navigation.
 */
const withPWA = withPWAInit({
  dest: "public",
  cacheOnFrontEndNav: true,
  aggressiveFrontEndNavCaching: true,
  reloadOnOnline: true,
  swcMinify: true,
  disable: process.env.NODE_ENV !== "production",
  fallbacks: {
    document: "/offline",
  },
  workboxOptions: {
    skipWaiting: true,
    clientsClaim: true,
    cleanupOutdatedCaches: true,
    runtimeCaching: [
      // Never cache anything that hits the FastAPI backend (auth/broker/me/aurum)
      {
        urlPattern: ({ url, sameOrigin }) =>
          sameOrigin &&
          (url.pathname.startsWith("/auth/") ||
            url.pathname === "/me" ||
            url.pathname.startsWith("/me/") ||
            url.pathname === "/broker" ||
            url.pathname.startsWith("/broker/") ||
            url.pathname.startsWith("/aurum/") ||
            url.pathname === "/healthz" ||
            url.pathname === "/readyz"),
        handler: "NetworkOnly",
        method: "GET",
      },
      {
        urlPattern: ({ url, sameOrigin }) =>
          sameOrigin &&
          (url.pathname.startsWith("/auth/") ||
            url.pathname === "/broker" ||
            url.pathname.startsWith("/broker/") ||
            url.pathname.startsWith("/me") ||
            url.pathname.startsWith("/aurum/")),
        handler: "NetworkOnly",
        method: "POST",
      },
      // Static Next.js assets
      {
        urlPattern: /^\/_next\/static\/.*/i,
        handler: "CacheFirst",
        options: {
          cacheName: "next-static",
          expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 * 30 },
        },
      },
      {
        urlPattern: /^\/_next\/image\?.*/i,
        handler: "StaleWhileRevalidate",
        options: {
          cacheName: "next-image",
          expiration: { maxEntries: 64, maxAgeSeconds: 60 * 60 * 24 * 30 },
        },
      },
      // Fonts / icons / manifest
      {
        urlPattern: /\.(?:woff2?|ttf|otf|eot)$/i,
        handler: "CacheFirst",
        options: { cacheName: "fonts", expiration: { maxAgeSeconds: 60 * 60 * 24 * 365 } },
      },
      {
        urlPattern: /\.(?:png|svg|jpg|jpeg|gif|webp|ico)$/i,
        handler: "CacheFirst",
        options: {
          cacheName: "images",
          expiration: { maxEntries: 64, maxAgeSeconds: 60 * 60 * 24 * 30 },
        },
      },
      {
        urlPattern: /\/manifest\.webmanifest$/i,
        handler: "StaleWhileRevalidate",
        options: { cacheName: "manifest" },
      },
      // App pages — network-first, fall back to cache, then to /offline
      {
        urlPattern: ({ request, sameOrigin }) =>
          sameOrigin && request.destination === "document",
        handler: "NetworkFirst",
        options: {
          cacheName: "pages",
          expiration: { maxEntries: 32, maxAgeSeconds: 60 * 60 * 24 * 7 },
          networkTimeoutSeconds: 5,
        },
      },
    ],
  },
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: { typedRoutes: false },
  async headers() {
    return [
      {
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Service-Worker-Allowed", value: "/" },
        ],
      },
      {
        source: "/manifest.webmanifest",
        headers: [
          { key: "Content-Type", value: "application/manifest+json" },
          { key: "Cache-Control", value: "public, max-age=3600" },
        ],
      },
    ];
  },
};

export default withPWA(nextConfig);
