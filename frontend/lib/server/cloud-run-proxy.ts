import "server-only";

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

const REQUEST_HEADERS = [
  "accept",
  "content-type",
  "idempotency-key",
  "if-range",
  "range",
  "x-request-id",
  "x-run-id",
  "x-trace-id",
];

const RESPONSE_HEADERS = [
  "accept-ranges",
  "cache-control",
  "content-disposition",
  "content-length",
  "content-range",
  "content-type",
  "etag",
  "last-modified",
  "x-accel-buffering",
  "x-content-type-options",
  "x-request-id",
  "x-run-id",
  "x-trace-id",
];

type ProxyConfig = {
  backendUrl: string;
  projectNumber: string;
  poolId: string;
  providerId: string;
  serviceAccountEmail: string;
  backendApiKey: string;
};

type TokenExchange = { access_token?: string };
type IdTokenResponse = { token?: string };

class ProxyFailure extends Error {
  constructor(
    readonly stage: "sts" | "iamcredentials" | "upstream",
    readonly status?: number,
    readonly reason?: string,
  ) {
    super(stage);
  }
}

async function googleFailure(response: Response, stage: ProxyFailure["stage"]): Promise<ProxyFailure> {
  let reason: string | undefined;
  try {
    const payload = (await response.json()) as { error?: unknown; error_description?: string };
    const message = typeof payload.error === "string"
      ? payload.error_description ?? payload.error
      : typeof payload.error === "object" && payload.error && "message" in payload.error && typeof payload.error.message === "string"
        ? payload.error.message
        : undefined;
    reason = message?.slice(0, 240);
  } catch {
    reason = undefined;
  }
  return new ProxyFailure(stage, response.status, reason);
}

function config(): ProxyConfig {
  const values = {
    backendUrl: process.env.CLOUD_RUN_STAGING_URL?.replace(/\/$/, "") ?? "",
    projectNumber: process.env.GCP_PROJECT_NUMBER ?? "",
    poolId: process.env.GCP_WORKLOAD_IDENTITY_POOL_ID ?? "",
    providerId: process.env.GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID ?? "",
    serviceAccountEmail: process.env.GCP_SERVICE_ACCOUNT_EMAIL ?? "",
    backendApiKey: process.env.BACKEND_API_KEY ?? "",
  };
  if (Object.entries(values).some(([key, value]) => key !== "backendApiKey" && !value)) {
    throw new Error("Server-side Cloud Run federation configuration is incomplete.");
  }
  const backend = new URL(values.backendUrl);
  if (backend.protocol !== "https:") {
    throw new Error("CLOUD_RUN_STAGING_URL must use HTTPS.");
  }
  return values;
}

async function googleIdToken(oidcToken: string, proxyConfig: ProxyConfig, signal: AbortSignal): Promise<string> {
  const audience = `//iam.googleapis.com/projects/${proxyConfig.projectNumber}/locations/global/workloadIdentityPools/${proxyConfig.poolId}/providers/${proxyConfig.providerId}`;
  const exchange = await fetch("https://sts.googleapis.com/v1/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      audience,
      grant_type: "urn:ietf:params:oauth:grant-type:token-exchange",
      requested_token_type: "urn:ietf:params:oauth:token-type:access_token",
      scope: "https://www.googleapis.com/auth/cloud-platform",
      subject_token: oidcToken,
      subject_token_type: "urn:ietf:params:oauth:token-type:jwt",
    }),
    signal,
  });
  if (!exchange.ok) throw await googleFailure(exchange, "sts");
  const accessToken = (await exchange.json() as TokenExchange).access_token;
  if (!accessToken) throw new ProxyFailure("sts");

  const idToken = await fetch(
    `https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/${encodeURIComponent(proxyConfig.serviceAccountEmail)}:generateIdToken`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ audience: proxyConfig.backendUrl, includeEmail: true }),
      signal,
    },
  );
  if (!idToken.ok) throw await googleFailure(idToken, "iamcredentials");
  const token = (await idToken.json() as IdTokenResponse).token;
  if (!token) throw new ProxyFailure("iamcredentials");
  return token;
}

function forwardRequestHeaders(request: Request, idToken: string, backendApiKey: string): Headers {
  const headers = new Headers();
  for (const name of REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set("Authorization", `Bearer ${idToken}`);
  if (backendApiKey) headers.set("X-API-Key", backendApiKey);
  return headers;
}

function forwardResponseHeaders(upstream: Response): Headers {
  const headers = new Headers();
  for (const name of RESPONSE_HEADERS) {
    if (!HOP_BY_HOP_HEADERS.has(name)) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
  }
  return headers;
}

function upstreamUrl(request: Request, path: string[], backendUrl: string): URL {
  if (!path.length || path.some((segment) => !segment || segment === "." || segment === "..")) {
    throw new Error("Invalid proxy path.");
  }
  const target = new URL(`${backendUrl}/${path.map(encodeURIComponent).join("/")}`);
  target.search = new URL(request.url).search;
  return target;
}

export async function proxyCloudRunRequest(request: Request, path: string[]): Promise<Response> {
  const oidcToken = process.env.VERCEL_OIDC_TOKEN ?? request.headers.get("x-vercel-oidc-token");
  if (!oidcToken) {
    return Response.json({ detail: "Server identity is unavailable." }, { status: 503 });
  }

  let proxyConfig: ProxyConfig;
  try {
    proxyConfig = config();
  } catch {
    return Response.json({ detail: "Proxy configuration is unavailable." }, { status: 503 });
  }

  const timeout = new AbortController();
  const timeoutMs = Number.parseInt(process.env.PROXY_CONNECT_TIMEOUT_MS ?? "120000", 10);
  const timer = setTimeout(() => timeout.abort(), Number.isFinite(timeoutMs) ? timeoutMs : 120000);
  request.signal.addEventListener("abort", () => timeout.abort(), { once: true });
  try {
    const idToken = await googleIdToken(oidcToken, proxyConfig, timeout.signal);
    const init: RequestInit & { duplex?: "half" } = {
      method: request.method,
      headers: forwardRequestHeaders(request, idToken, proxyConfig.backendApiKey),
      body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
      signal: timeout.signal,
      redirect: "manual",
    };
    if (init.body) init.duplex = "half";
    const upstream = await fetch(upstreamUrl(request, path, proxyConfig.backendUrl), init);
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: forwardResponseHeaders(upstream),
    });
  } catch (error) {
    if (error instanceof ProxyFailure) {
      console.error("Cloud Run proxy authentication failed", {
        stage: error.stage,
        status: error.status,
        reason: error.reason,
      });
    } else if (error instanceof DOMException && error.name === "AbortError") {
      console.error("Cloud Run proxy request aborted");
    } else {
      console.error("Cloud Run proxy request failed");
    }
    return Response.json({ detail: "The private research service is unavailable." }, { status: 502 });
  } finally {
    clearTimeout(timer);
  }
}
