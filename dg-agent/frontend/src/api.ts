// Thin API client. The JWT is held in sessionStorage (cleared when the tab closes).
export type Json = any; // eslint-disable-line @typescript-eslint/no-explicit-any

const KEY = "dg_token";
export const auth = {
  get token(): string | null {
    try { return sessionStorage.getItem(KEY); } catch { return null; }
  },
  set(token: string | null) {
    try { token ? sessionStorage.setItem(KEY, token) : sessionStorage.removeItem(KEY); } catch { /* ignore */ }
  },
};

export class ApiError extends Error {
  constructor(public status: number, public detail: Json) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
}

async function request(method: string, path: string, body?: Json, isForm = false): Promise<Json> {
  const headers: Record<string, string> = {};
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`;
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { method, headers, body: isForm ? body : body !== undefined ? JSON.stringify(body) : undefined });
  if (res.status === 401 && path !== "/api/auth/login") {
    auth.set(null);
    window.dispatchEvent(new Event("dg-logout"));
  }
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? data);
  return data;
}

export const api = {
  get: (p: string) => request("GET", p),
  post: (p: string, b?: Json) => request("POST", p, b ?? {}),
  patch: (p: string, b: Json) => request("PATCH", p, b),
  upload: (p: string, form: FormData) => request("POST", p, form, true),
  async download(p: string, filename: string) {
    const res = await fetch(p, { headers: auth.token ? { Authorization: `Bearer ${auth.token}` } : {} });
    if (!res.ok) throw new ApiError(res.status, await res.text());
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },
};
