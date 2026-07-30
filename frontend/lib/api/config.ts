const API_PREFIX = "/api";

export function getApiBaseUrl(): string {
  return API_PREFIX;
}

export function apiUrl(path: string): string {
  return `${getApiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
}
