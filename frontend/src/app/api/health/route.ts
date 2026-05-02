// Tiny route the docker healthcheck pings to confirm the Next.js server is up.
// Has nothing to do with the backend's /healthz — different origin in dev,
// same origin in prod (where Caddy routes /healthz to the backend, not here).
export const dynamic = "force-static";

export function GET() {
  return new Response(JSON.stringify({ status: "ok" }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
