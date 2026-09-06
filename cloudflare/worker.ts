const PROXY_PATHS = new Set(["/health", "/ready", "/docs", "/openapi.json"]);
const ERROR_SECURITY_HEADERS = {
  "Content-Security-Policy": "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Resource-Policy": "same-origin",
  "Permissions-Policy": "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
} as const;

function isProxyPath(pathname: string): boolean {
  return pathname === "/api" || pathname.startsWith("/api/") || PROXY_PATHS.has(pathname);
}

function isLoopbackHostname(hostname: string): boolean {
  const normalized = hostname.toLowerCase();
  return normalized === "localhost" || normalized === "127.0.0.1" || normalized === "[::1]";
}

function configuredApiOrigin(value: string): URL | null {
  const candidate = value.trim();
  if (candidate === "") return null;

  try {
    const url = new URL(candidate);
    const hasSafeProtocol =
      url.protocol === "https:" ||
      (url.protocol === "http:" && isLoopbackHostname(url.hostname));
    const hasCleanOrigin =
      hasSafeProtocol &&
      url.username === "" &&
      url.password === "" &&
      (url.pathname === "" || url.pathname === "/") &&
      url.search === "" &&
      url.hash === "";
    return hasCleanOrigin ? url : null;
  } catch {
    return null;
  }
}

function unavailable(requestId: string): Response {
  return Response.json(
    {
      error: {
        code: "api_origin_not_configured",
        summary: "Mesh2Param API unavailable",
        detail:
          "This Cloudflare Worker serves the web application, but MESH2PARAM_API_ORIGIN is not configured with a valid HTTPS or loopback HTTP origin.",
        phase: null,
        projectId: null,
        jobId: null,
        recoverable: false,
        recommendedAction: "Configure the Worker with the origin of the separately hosted Mesh2Param API.",
      },
      meta: { requestId },
    },
    {
      status: 503,
      headers: {
        ...ERROR_SECURITY_HEADERS,
        "Cache-Control": "no-store",
        "X-Request-ID": requestId,
      },
    },
  );
}

function browserLocalHealth(requestId: string): Response {
  return Response.json(
    {
      status: "ok",
      service: "mesh2param-worker",
      executionMode: "browser-local",
      apiProxy: "not-configured",
    },
    {
      headers: {
        ...ERROR_SECURITY_HEADERS,
        "Cache-Control": "no-store",
        "X-Request-ID": requestId,
      },
    },
  );
}

function proxyFailure(requestId: string): Response {
  return Response.json(
    {
      error: {
        code: "api_proxy_failed",
        summary: "Mesh2Param API unavailable",
        detail: "The Cloudflare Worker could not reach the configured Mesh2Param API.",
        phase: null,
        projectId: null,
        jobId: null,
        recoverable: true,
        recommendedAction: "Verify API readiness and the MESH2PARAM_API_ORIGIN Worker variable.",
      },
      meta: { requestId },
    },
    {
      status: 502,
      headers: {
        ...ERROR_SECURITY_HEADERS,
        "Cache-Control": "no-store",
        "X-Request-ID": requestId,
      },
    },
  );
}

function requestIdFor(request: Request): string {
  const supplied = request.headers.get("X-Request-ID") ?? "";
  return /^[A-Za-z0-9._:-]{1,64}$/.test(supplied) ? supplied : crypto.randomUUID();
}

async function proxyToApi(request: Request, env: Env): Promise<Response> {
  const requestId = requestIdFor(request);
  const apiOrigin = configuredApiOrigin(env.MESH2PARAM_API_ORIGIN);
  if (apiOrigin === null) return unavailable(requestId);

  const incomingUrl = new URL(request.url);
  if (apiOrigin.origin === incomingUrl.origin) return unavailable(requestId);

  const upstreamUrl = new URL(`${incomingUrl.pathname}${incomingUrl.search}`, apiOrigin);
  const upstreamRequest = new Request(upstreamUrl, request);
  upstreamRequest.headers.set("X-Request-ID", requestId);

  try {
    const upstreamResponse = await fetch(upstreamRequest, { redirect: "manual" });
    const headers = new Headers(upstreamResponse.headers);
    const location = headers.get("Location");
    if (location !== null) {
      const redirectUrl = new URL(location, apiOrigin);
      if (redirectUrl.origin === apiOrigin.origin) {
        redirectUrl.protocol = incomingUrl.protocol;
        redirectUrl.host = incomingUrl.host;
        headers.set("Location", redirectUrl.toString());
      }
    }
    headers.set("X-Request-ID", headers.get("X-Request-ID") ?? requestId);
    return new Response(upstreamResponse.body, {
      status: upstreamResponse.status,
      statusText: upstreamResponse.statusText,
      headers,
    });
  } catch (error) {
    console.error(
      JSON.stringify({
        message: "Mesh2Param API proxy request failed",
        error: error instanceof Error ? error.message : String(error),
        method: request.method,
        path: incomingUrl.pathname,
        requestId,
      }),
    );
    return proxyFailure(requestId);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const pathname = new URL(request.url).pathname;
    if (pathname === "/healthz") {
      const headers = {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
      };
      if (request.method !== "GET" && request.method !== "HEAD") {
        return new Response(null, { status: 405, headers: { ...headers, allow: "GET, HEAD" } });
      }
      return new Response(
        request.method === "HEAD" ? null : JSON.stringify({ status: "ok", service: "mesh2param" }),
        { headers },
      );
    }

    if (pathname === "/health" && configuredApiOrigin(env.MESH2PARAM_API_ORIGIN) === null) {
      return browserLocalHealth(requestIdFor(request));
    }
    if (isProxyPath(pathname)) return proxyToApi(request, env);
    return env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;
