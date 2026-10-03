import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Project } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useT } from "../lib/i18n";
import { SignInBar } from "./SignInBar";
import { PromptDetail } from "./PromptDetail";

const PAGE_SIZE = 10;

/** The prompt library: list (search + tags + project filter + pagination) and detail. */
export function LibraryPage() {
  const t = useT();
  const { token } = useAuth();

  if (!token) {
    return (
      <div className="space-y-4">
        <SignInBar />
        <p className="text-sm text-subtle">{t("lib.signin.hint")}</p>
      </div>
    );
  }
  return <LibraryAuthed token={token} />;
}

function LibraryAuthed({ token }: { token: string }) {
  const [selected, setSelected] = useState<string | null>(null);

  if (selected) {
    return (
      <div className="space-y-4">
        <SignInBar />
        <PromptDetail token={token} promptId={selected} onBack={() => setSelected(null)} />
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <SignInBar />
      <PromptBrowser token={token} onOpen={setSelected} />
    </div>
  );
}

function PromptBrowser({ token, onOpen }: { token: string; onOpen: (id: string) => void }) {
  const t = useT();
  const [q, setQ] = useState("");
  const [tagsRaw, setTagsRaw] = useState("");
  const [projectId, setProjectId] = useState<string>("");
  const [offset, setOffset] = useState(0);

  const tags = tagsRaw
    .split(",")
    .map((t) => t.trim().toLowerCase())
    .filter(Boolean);

  const projectsQ = useQuery({ queryKey: ["projects"], queryFn: () => api.listProjects(token) });

  const promptsQ = useQuery({
    queryKey: ["prompts", { q, tags, projectId, offset }],
    queryFn: () =>
      api.listPrompts(token, {
        q: q.trim() || undefined,
        tag: tags.length ? tags : undefined,
        project_id: projectId || undefined,
        limit: PAGE_SIZE,
        offset,
      }),
  });

  const page = promptsQ.data;
  const hasPrev = offset > 0;
  const hasNext = page ? offset + PAGE_SIZE < page.total : false;

  return (
    <div className="space-y-4">
      <NewPromptForm token={token} projects={projectsQ.data ?? []} />

      {/* Filters */}
      <div className="grid gap-2 sm:grid-cols-3">
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOffset(0);
          }}
          placeholder={t("filters.search.ph")}
          aria-label={t("filters.search.aria")}
          className="rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink placeholder:text-subtle"
        />
        <input
          value={tagsRaw}
          onChange={(e) => {
            setTagsRaw(e.target.value);
            setOffset(0);
          }}
          placeholder={t("filters.tags.ph")}
          aria-label={t("filters.tags.aria")}
          className="rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink placeholder:text-subtle"
        />
        <select
          value={projectId}
          onChange={(e) => {
            setProjectId(e.target.value);
            setOffset(0);
          }}
          aria-label={t("filters.project.aria")}
          className="rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink"
        >
          <option value="">{t("filters.allProjects")}</option>
          {(projectsQ.data ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      {promptsQ.isError && (
        <p role="alert" className="text-sm text-danger">
          {(promptsQ.error as Error).message}
        </p>
      )}

      {/* List */}
      {page && page.items.length === 0 && (
        <p className="text-sm text-muted">{t("list.empty")}</p>
      )}
      <ul className="space-y-2">
        {page?.items.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              onClick={() => onOpen(p.id)}
              className="w-full rounded-xl border border-line bg-surface p-4 text-left transition hover:border-accent/50"
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold text-ink">{p.name}</span>
                <code className="text-xs text-subtle">{p.slug}</code>
              </div>
              {p.description && <p className="mt-1 text-sm text-muted">{p.description}</p>}
              {p.tags.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {p.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-md border border-accent/30 bg-accent/10 px-2 py-0.5 text-xs text-accent-ink"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </button>
          </li>
        ))}
      </ul>

      {/* Pagination */}
      {page && page.total > 0 && (
        <div className="flex items-center justify-between text-sm text-muted">
          <span>
            {t("pager.range", {
              a: offset + 1,
              b: Math.min(offset + PAGE_SIZE, page.total),
              total: page.total,
            })}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={!hasPrev}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              className="rounded-md border border-line px-3 py-1 disabled:opacity-40"
            >
              {t("pager.prev")}
            </button>
            <button
              type="button"
              disabled={!hasNext}
              onClick={() => setOffset(offset + PAGE_SIZE)}
              className="rounded-md border border-line px-3 py-1 disabled:opacity-40"
            >
              {t("pager.next")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function NewPromptForm({ token, projects }: { token: string; projects: Project[] }) {
  const t = useT();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [projectId, setProjectId] = useState("");
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [tagsRaw, setTagsRaw] = useState("");

  const createM = useMutation({
    mutationFn: () =>
      api.createPrompt(token, {
        project_id: projectId,
        slug: slug.trim(),
        name: name.trim(),
        tags: tagsRaw
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      }),
    onSuccess: () => {
      setSlug("");
      setName("");
      setTagsRaw("");
      void qc.invalidateQueries({ queryKey: ["prompts"] });
    },
  });

  const canSubmit = projectId && slug.trim() && name.trim() && !createM.isPending;

  return (
    <details
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
      className="rounded-2xl border border-line bg-surface p-4"
    >
      <summary className="cursor-pointer text-sm font-semibold text-muted">
        {t("newprompt.summary")}
      </summary>
      {projects.length === 0 ? (
        <p className="mt-3 text-sm text-warn">{t("newprompt.needProject")}</p>
      ) : (
        <div className="mt-3 space-y-2">
          <div className="grid gap-2 sm:grid-cols-2">
            <select
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              aria-label={t("newprompt.project.aria")}
              className="rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink"
            >
              <option value="">{t("newprompt.project.choose")}</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <input
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder={t("newprompt.slug.ph")}
              aria-label={t("newprompt.slug.aria")}
              className="rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink placeholder:text-subtle"
            />
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("newprompt.name.ph")}
              aria-label={t("newprompt.name.aria")}
              className="rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink placeholder:text-subtle"
            />
            <input
              value={tagsRaw}
              onChange={(e) => setTagsRaw(e.target.value)}
              placeholder={t("newprompt.tags.ph")}
              aria-label={t("newprompt.tags.aria")}
              className="rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink placeholder:text-subtle"
            />
          </div>
          {createM.isError && (
            <p role="alert" className="text-sm text-danger">
              {(createM.error as Error).message}
            </p>
          )}
          <button
            type="button"
            disabled={!canSubmit}
            onClick={() => createM.mutate()}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {createM.isPending ? t("newprompt.creating") : t("newprompt.create")}
          </button>
        </div>
      )}
    </details>
  );
}
