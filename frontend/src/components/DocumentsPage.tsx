import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type SearchResult } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useT } from "../lib/i18n";
import { SignInBar } from "./SignInBar";

/**
 * Documents = the RAG corpus surface over the backend that already exists
 * (`POST/GET/DELETE /v1/documents`, `POST /v1/documents/search`). Tenant-isolated
 * (RLS). Honesty is preserved: when embeddings are the offline lexical proxy
 * (`embedding_is_real` / `is_real` false), the UI flags that the ranking is not semantic.
 */
export function DocumentsPage() {
  const t = useT();
  const { token } = useAuth();
  if (!token) {
    return (
      <div className="space-y-4">
        <SignInBar />
        <p className="text-sm text-subtle">{t("docs.signin.hint")}</p>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <SignInBar />
      <IngestForm token={token} />
      <SearchBox token={token} />
      <DocumentList token={token} />
    </div>
  );
}

function OfflineNote({ note }: { note: string }) {
  const t = useT();
  return (
    <p className="rounded-lg border border-warn/40 bg-warn/10 p-2 text-xs text-warn">
      {note || t("docs.offline.warn")}
    </p>
  );
}

function IngestForm({ token }: { token: string }) {
  const t = useT();
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [source, setSource] = useState("");

  const m = useMutation({
    mutationFn: () =>
      api.ingestDocument(token, {
        title: title.trim(),
        content: content.trim(),
        source_uri: source.trim() || undefined,
      }),
    onSuccess: () => {
      setTitle("");
      setContent("");
      setSource("");
      void qc.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const canSubmit = title.trim() && content.trim() && !m.isPending;

  return (
    <div className="space-y-2 rounded-2xl border border-line bg-surface p-4">
      <h2 className="text-sm font-semibold text-muted">{t("docs.ingest.title")}</h2>
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder={t("docs.ingest.titlePh")}
        aria-label={t("docs.ingest.titleAria")}
        className="w-full rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink placeholder:text-subtle"
      />
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder={t("docs.ingest.contentPh")}
        aria-label={t("docs.ingest.contentAria")}
        rows={4}
        className="w-full rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink placeholder:text-subtle"
      />
      <input
        value={source}
        onChange={(e) => setSource(e.target.value)}
        placeholder={t("docs.ingest.sourcePh")}
        aria-label={t("docs.ingest.sourceAria")}
        className="w-full rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink placeholder:text-subtle"
      />
      {m.isError && (
        <p role="alert" className="text-sm text-danger">
          {(m.error as Error).message}
        </p>
      )}
      {m.isSuccess && (
        <div className="space-y-2 text-sm text-ok">
          <p>{t("docs.ingest.done", { n: m.data.n_chunks })}</p>
          {!m.data.embedding_is_real && <OfflineNote note={m.data.note} />}
        </div>
      )}
      <button
        type="button"
        disabled={!canSubmit}
        onClick={() => m.mutate()}
        className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {m.isPending ? t("docs.ingest.submitting") : t("docs.ingest.submit")}
      </button>
    </div>
  );
}

function SearchBox({ token }: { token: string }) {
  const t = useT();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);

  const m = useMutation({
    mutationFn: () => api.searchDocuments(token, { query: query.trim(), k: 5 }),
    onSuccess: (r) => setResult(r),
  });

  const canSubmit = query.trim() && !m.isPending;

  return (
    <div className="space-y-2 rounded-2xl border border-line bg-surface p-4">
      <h2 className="text-sm font-semibold text-muted">{t("docs.search.title")}</h2>
      <div className="flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && canSubmit) m.mutate();
          }}
          placeholder={t("docs.search.ph")}
          aria-label={t("docs.search.aria")}
          className="flex-1 rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink placeholder:text-subtle"
        />
        <button
          type="button"
          disabled={!canSubmit}
          onClick={() => m.mutate()}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {m.isPending ? t("docs.search.searching") : t("docs.search.submit")}
        </button>
      </div>
      {m.isError && (
        <p role="alert" className="text-sm text-danger">
          {(m.error as Error).message}
        </p>
      )}
      {result && (
        <div className="space-y-2">
          {!result.is_real && <OfflineNote note={result.note} />}
          {result.chunks.length === 0 ? (
            <p className="text-sm text-muted">{t("docs.search.empty")}</p>
          ) : (
            <ul className="space-y-2">
              {result.chunks.map((c) => (
                <li key={c.chunk_id} className="rounded-xl border border-line bg-raised p-3">
                  <div className="flex items-center justify-between gap-2 text-xs text-subtle">
                    <span className="font-medium text-muted">{c.document_title}</span>
                    <span>
                      {t("docs.search.score")}: {c.score.toFixed(3)}
                    </span>
                  </div>
                  <p className="mt-1 whitespace-pre-wrap break-words text-sm text-ink">
                    {c.content}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function DocumentList({ token }: { token: string }) {
  const t = useT();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["documents"], queryFn: () => api.listDocuments(token) });

  const del = useMutation({
    mutationFn: (id: string) => api.deleteDocument(token, id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["documents"] }),
  });

  if (q.isError)
    return (
      <p role="alert" className="text-sm text-danger">
        {(q.error as Error).message}
      </p>
    );
  if (!q.data) return <p className="text-sm text-muted">{t("docs.list.loading")}</p>;

  return (
    <div className="space-y-2">
      <h2 className="text-sm font-semibold text-muted">{t("docs.list.title")}</h2>
      {q.data.length === 0 ? (
        <p className="text-sm text-muted">{t("docs.list.empty")}</p>
      ) : (
        <ul className="space-y-2">
          {q.data.map((d) => (
            <li
              key={d.id}
              className="flex items-center justify-between gap-3 rounded-xl border border-line bg-surface p-4"
            >
              <div className="min-w-0">
                <p className="truncate font-semibold text-ink">{d.title}</p>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-subtle">
                  <span>{new Date(d.created_at).toLocaleString()}</span>
                  <span
                    className={
                      "rounded-md border px-2 py-0.5 " +
                      (d.embedding_is_real
                        ? "border-ok/40 bg-ok/10 text-ok"
                        : "border-warn/40 bg-warn/10 text-warn")
                    }
                  >
                    {d.embedding_is_real
                      ? d.embedding_model
                      : t("docs.offlineBadge")}
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  if (window.confirm(t("docs.delete.confirm"))) del.mutate(d.id);
                }}
                disabled={del.isPending}
                className="shrink-0 rounded-md border border-line px-3 py-1 text-sm text-muted transition hover:border-danger/50 hover:text-danger disabled:opacity-40"
              >
                {t("docs.delete")}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
