const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface ReadinessComponent {
  name: string;
  ok: boolean;
  detail?: string | null;
}

export interface Readiness {
  status: string;
  components: ReadinessComponent[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

export const api = {
  readiness: () => request<Readiness>("/api/v1/health/ready"),
};
