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

export type DiagnosticLevel = "low" | "medium" | "high";

export interface DiagnosticDimension {
  dimension: string;
  label: string;
  level: DiagnosticLevel;
  detail: string;
  reason: string | null;
  recommendation: string | null;
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
  // 204 No Content (e.g. DELETE) and empty bodies have no JSON to parse.
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? (JSON.parse(text) as T) : (undefined as T));
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

export interface EvaluationCriterion {
  name: string;
  passed: boolean;
  score: number;
  weight: number;
  detail: string;
}

export interface EvaluationReport {
  score: number;
  passed: boolean;
  criteria: EvaluationCriterion[];
  method: string;
  measured: boolean;
  summary: string;
}

export interface Improvement {
  target: string;
  suggestion: string;
  rationale: string;
  derived_from: string;
}

export interface ImprovementReport {
  improvements: Improvement[];
  method: string;
  summary: string;
}

export interface PipelineStage {
  stage: string;
  status: string;
}

export interface ExecuteResponse {
  execution_id: string | null;
  status: string;
  output: string;
  steps: unknown[];
  questions: string[];
  metadata: ExecuteMetadata | null;
  verification: VerificationReport | null;
  evaluation: EvaluationReport | null;
  improvements: ImprovementReport | null;
  trace: PipelineStage[];
}

export interface ExecuteRequest {
  task: string;
  mode?: CompileMode;
  output_format?: string;
  target_model?: string;
  quality_contract?: string[];
}

// ── Prompt library + versioning (authenticated) ────────────────────────────────────
export interface Project {
  id: string;
  slug: string;
  name: string;
  description: string | null;
}

export interface Prompt {
  id: string;
  tenant_id: string;
  project_id: string;
  slug: string;
  name: string;
  description: string | null;
  tags: string[];
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface PromptVersion {
  id: string;
  prompt_id: string;
  version: number;
  source_intent: string | null;
  catr: unknown | null;
  ir: unknown | null;
  renders: PromptRenders | null;
  diagnostics: DiagnosticDimension[] | null;
  model_target: string | null;
  author_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface SaveCompilationResponse {
  version: PromptVersion;
  compile: CompileResponse;
}

export interface FieldChange {
  path: string;
  change: "added" | "removed" | "changed";
  before: unknown | null;
  after: unknown | null;
}

export interface ScalarDelta {
  before: string | null;
  after: string | null;
  changed: boolean;
}

export interface RenderDiff {
  mode: string;
  changed: boolean;
  unified_diff: string;
}

export interface DiagnosticDelta {
  dimension: string;
  before: string | null;
  after: string | null;
  changed: boolean;
}

export interface VersionDiff {
  prompt_id: string;
  from_version: number;
  to_version: number;
  source_intent: ScalarDelta;
  model_target: ScalarDelta;
  catr_fields: FieldChange[];
  renders: RenderDiff[];
  diagnostics: DiagnosticDelta[];
  summary: string;
  note: string;
}

export interface ListPromptsParams {
  project_id?: string;
  tag?: string[];
  q?: string;
  limit?: number;
  offset?: number;
}

function authed(token: string, init?: RequestInit): RequestInit {
  return {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {}),
    },
  };
}

function toQuery(params: ListPromptsParams): string {
  const sp = new URLSearchParams();
  if (params.project_id) sp.set("project_id", params.project_id);
  if (params.q) sp.set("q", params.q);
  if (params.limit != null) sp.set("limit", String(params.limit));
  if (params.offset != null) sp.set("offset", String(params.offset));
  for (const t of params.tag ?? []) sp.append("tag", t);
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

// ── Executions (async pipeline runs; observability) ────────────────────────────────
export interface Execution {
  id: string;
  tenant_id: string;
  prompt_version_id: string | null;
  status: string;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

// ── Documents / RAG corpus (authenticated, tenant-isolated) ─────────────────────────
export interface DocumentRead {
  id: string;
  title: string;
  source_uri: string | null;
  embedding_model: string;
  embedding_is_real: boolean;
  created_at: string;
}

export interface IngestResult {
  document: DocumentRead;
  n_chunks: number;
  embedding_is_real: boolean;
  note: string;
}

export interface RetrievedChunk {
  document_id: string;
  document_title: string;
  chunk_id: string;
  chunk_index: number;
  content: string;
  score: number;
}

export interface SearchResult {
  query: string;
  chunks: RetrievedChunk[];
  is_real: boolean;
  note: string;
}

export const api = {
  health: () => request<Health>("/v1/health"),
  login: (body: { org_slug: string; email: string; password: string }) =>
    request<TokenResponse>("/v1/auth/login", { method: "POST", body: JSON.stringify(body) }),
  signup: (body: { org_slug: string; org_name: string; email: string; password: string }) =>
    request<TokenResponse>("/v1/auth/signup", { method: "POST", body: JSON.stringify(body) }),
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

  // Library
  listProjects: (token: string) => request<Project[]>("/v1/projects", authed(token)),
  createProject: (token: string, body: { slug: string; name: string }) =>
    request<Project>("/v1/projects", authed(token, { method: "POST", body: JSON.stringify(body) })),
  listPrompts: (token: string, params: ListPromptsParams = {}) =>
    request<Page<Prompt>>(`/v1/prompts${toQuery(params)}`, authed(token)),
  createPrompt: (
    token: string,
    body: { project_id: string; slug: string; name: string; tags?: string[] },
  ) =>
    request<Prompt>("/v1/prompts", authed(token, { method: "POST", body: JSON.stringify(body) })),
  getPrompt: (token: string, id: string) => request<Prompt>(`/v1/prompts/${id}`, authed(token)),
  listVersions: (token: string, id: string) =>
    request<PromptVersion[]>(`/v1/prompts/${id}/versions`, authed(token)),
  saveCompilation: (token: string, id: string, body: { task: string; mode?: CompileMode }) =>
    request<SaveCompilationResponse>(
      `/v1/prompts/${id}/compilations`,
      authed(token, { method: "POST", body: JSON.stringify(body) }),
    ),
  diffVersions: (token: string, id: string, from: number, to: number) =>
    request<VersionDiff>(
      `/v1/prompts/${id}/versions/diff?from_version=${from}&to_version=${to}`,
      authed(token),
    ),

  // Executions (observability: status, cost, latency, steps)
  listExecutions: (token: string) => request<Execution[]>("/v1/executions", authed(token)),
  getExecution: (token: string, id: string) =>
    request<Execution>(`/v1/executions/${id}`, authed(token)),

  // Documents / RAG corpus
  listDocuments: (token: string) => request<DocumentRead[]>("/v1/documents", authed(token)),
  ingestDocument: (token: string, body: { title: string; content: string; source_uri?: string }) =>
    request<IngestResult>(
      "/v1/documents",
      authed(token, { method: "POST", body: JSON.stringify(body) }),
    ),
  deleteDocument: (token: string, id: string) =>
    request<void>(`/v1/documents/${id}`, authed(token, { method: "DELETE" })),
  searchDocuments: (token: string, body: { query: string; k?: number }) =>
    request<SearchResult>(
      "/v1/documents/search",
      authed(token, { method: "POST", body: JSON.stringify(body) }),
    ),
};
