export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface Health {
  status: string;
  version: string;
  db: string;
}

export type CompileMode = "compact" | "professional" | "expert";

export interface PromptSection {
  name: string;
  content: string;
}

export interface PromptRenders {
  compact: string;
  professional: string;
  expert: string;
}

export interface CompiledPrompt {
  mode: CompileMode;
  text: string;
  sections: string[];
  ir: PromptSection[];
}

export interface ExecutionStep {
  order: number;
  action: string;
  detail: string;
}

export interface CostEstimate {
  estimated: boolean;
  currency: string;
  input_tokens_est: number;
  output_tokens_est: number;
  cost_usd_est: number;
  disclaimer: string;
}

export interface ExecutionPlan {
  strategy: string;
  target_model: string | null;
  fallback_models: string[];
  steps: ExecutionStep[];
  cost: CostEstimate;
}

export interface DiagnosticDimension {
  dimension: string;
  level: string;
  detail: string;
}

export interface UnderstoodIntent {
  objective: string;
  domain: string;
}

export interface CompileMetadata {
  engine: string;
  deterministic: boolean;
  llm_used: boolean;
  target_model: string | null;
  costs_estimated: boolean;
  notes: string[];
}

export interface CompileResponse {
  understood: UnderstoodIntent;
  execution_plan: ExecutionPlan | null;
  compiled_prompt: CompiledPrompt | null;
  renders: PromptRenders | null;
  diagnostics: DiagnosticDimension[];
  questions: string[];
  metadata: CompileMetadata;
}

export interface CompileRequest {
  task: string;
  mode?: CompileMode;
  output_format?: string;
  target_model?: string;
  quality_contract?: string[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new Error("Impossible de joindre le serveur Kompilo. Est-il démarré ?");
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      /* non-JSON error body — keep the status line */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

// ── Execute (authenticated) ──────────────────────────────────────────────────────
export interface ExecuteActualCost {
  actual: boolean;
  currency: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface ExecuteMetadata {
  provider: string;
  provider_is_real: boolean;
  model: string | null;
  actual_cost: ExecuteActualCost;
  latency_ms: number;
  cached: boolean;
  idempotent_replay: boolean;
  note: string | null;
}

export interface VerificationIssue {
  kind: string;
  detail: string;
  path: string | null;
}

export interface VerificationReport {
  valid: boolean;
  format: string;
  issues: VerificationIssue[];
  summary: string;
}

export interface ExecuteResponse {
  execution_id: string | null;
  status: string;
  output: string;
  steps: unknown[];
  questions: string[];
  metadata: ExecuteMetadata | null;
  verification: VerificationReport | null;
}

export interface ExecuteRequest {
  task: string;
  mode?: CompileMode;
  output_format?: string;
  target_model?: string;
  quality_contract?: string[];
}

export const api = {
  health: () => request<Health>("/v1/health"),
  compile: (req: CompileRequest) =>
    request<CompileResponse>("/v1/compile", {
      method: "POST",
      body: JSON.stringify(req),
    }),
  execute: (req: ExecuteRequest, token: string) =>
    request<ExecuteResponse>("/v1/execute", {
      method: "POST",
      body: JSON.stringify(req),
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    }),
};
