import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type PromptVersion, type VersionDiff } from "../lib/api";
import { useT } from "../lib/i18n";

/** A single prompt: its versions, a "save a compilation" action, and a neutral diff. */
export function PromptDetail({
  token,
  promptId,
  onBack,
}: {
  token: string;
  promptId: string;
  onBack: () => void;
}) {
  const t = useT();
  const qc = useQueryClient();

  const promptQ = useQuery({
    queryKey: ["prompt", promptId],
    queryFn: () => api.getPrompt(token, promptId),
  });
  const versionsQ = useQuery({
    queryKey: ["versions", promptId],
    queryFn: () => api.listVersions(token, promptId),
  });

  const [task, setTask] = useState("");
  const saveM = useMutation({
    mutationFn: () => api.saveCompilation(token, promptId, { task: task.trim() }),
    onSuccess: () => {
      setTask("");
      void qc.invalidateQueries({ queryKey: ["versions", promptId] });
    },
  });

  const versions = versionsQ.data ?? [];

  return (
    <section className="space-y-4">
      <button
        type="button"
        onClick={onBack}
        className="text-sm text-accent-ink hover:text-ink"
      >
        {t("detail.back")}
      </button>

      {promptQ.data && (
        <header>
          <h2 className="text-xl font-bold text-ink">{promptQ.data.name}</h2>
          <p className="text-sm text-muted">
            <code>{promptQ.data.slug}</code>
            {promptQ.data.description ? ` · ${promptQ.data.description}` : ""}
          </p>
          {promptQ.data.tags.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {promptQ.data.tags.map((tag) => (
                <span
                  key={tag}
                  className="rounded-md border border-accent/30 bg-accent/10 px-2 py-0.5 text-xs text-accent-ink"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </header>
      )}

      {/* Save a compilation → new version. */}
      <div className="rounded-2xl border border-line bg-surface p-5">
        <h3 className="text-sm font-semibold text-ink">{t("detail.save.title")}</h3>
        <p className="mt-1 text-xs text-muted">{t("detail.save.hint")}</p>
        <textarea
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder={t("detail.save.ph")}
          rows={2}
          className="mt-3 w-full rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink placeholder:text-subtle"
        />
        <div className="mt-2 flex items-center gap-3">
          <button
            type="button"
            disabled={!task.trim() || saveM.isPending}
            onClick={() => saveM.mutate()}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saveM.isPending ? t("form.submitting") : t("detail.save.submit")}
          </button>
          {saveM.isError && (
            <span role="alert" className="text-sm text-danger">
              {(saveM.error as Error).message}
            </span>
          )}
          {saveM.isSuccess && saveM.data.compile.questions.length > 0 && (
            <span className="text-sm text-warn">
              {t("detail.save.saved", { n: saveM.data.version.version })}
            </span>
          )}
        </div>
      </div>

      {/* Version history. */}
      <div className="rounded-2xl border border-line bg-surface p-5">
        <h3 className="text-sm font-semibold text-ink">
          {t("detail.versions")}{" "}
          {versions.length > 0 && <span className="text-subtle">({versions.length})</span>}
        </h3>
        {versionsQ.isLoading && <p className="mt-2 text-sm text-muted">{t("detail.versions.loading")}</p>}
        {versions.length === 0 && !versionsQ.isLoading && (
          <p className="mt-2 text-sm text-muted">{t("detail.versions.empty")}</p>
        )}
        {versions.length > 0 && (
          <ul className="mt-3 space-y-2">
            {versions.map((v) => (
              <VersionRow key={v.id} v={v} />
            ))}
          </ul>
        )}
      </div>

      {versions.length >= 2 && <DiffPanel token={token} promptId={promptId} versions={versions} />}
    </section>
  );
}

function VersionRow({ v }: { v: PromptVersion }) {
  const t = useT();
  return (
    <li className="rounded-xl border border-line bg-raised p-3 text-sm">
      <div className="flex items-center justify-between">
        <span className="font-semibold text-ink">v{v.version}</span>
        <span className="text-xs text-subtle">{new Date(v.created_at).toLocaleString()}</span>
      </div>
      {v.model_target && (
        <p className="text-xs text-muted">{t("detail.version.model", { v: v.model_target })}</p>
      )}
      {v.source_intent && (
        <p className="mt-1 line-clamp-2 text-xs text-muted">« {v.source_intent} »</p>
      )}
    </li>
  );
}

function DiffPanel({
  token,
  promptId,
  versions,
}: {
  token: string;
  promptId: string;
  versions: PromptVersion[];
}) {
  const t = useT();
  const numbers = versions.map((v) => v.version);
  const [from, setFrom] = useState(numbers[numbers.length - 2]);
  const [to, setTo] = useState(numbers[numbers.length - 1]);
  const [diff, setDiff] = useState<VersionDiff | null>(null);
  const [error, setError] = useState<string | null>(null);

  const diffM = useMutation({
    mutationFn: () => api.diffVersions(token, promptId, from, to),
    onSuccess: (d) => {
      setDiff(d);
      setError(null);
    },
    onError: (e) => setError((e as Error).message),
  });

  // Keep selectors valid if the version list grows.
  useEffect(() => {
    if (!numbers.includes(from)) setFrom(numbers[numbers.length - 2]);
    if (!numbers.includes(to)) setTo(numbers[numbers.length - 1]);
  }, [numbers, from, to]);

  return (
    <div className="rounded-2xl border border-line bg-surface p-5">
      <h3 className="text-sm font-semibold text-ink">{t("detail.compare.title")}</h3>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
        <VersionSelect label={t("detail.compare.from")} value={from} options={numbers} onChange={setFrom} />
        <VersionSelect label={t("detail.compare.to")} value={to} options={numbers} onChange={setTo} />
        <button
          type="button"
          disabled={from === to || diffM.isPending}
          onClick={() => diffM.mutate()}
          className="rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {diffM.isPending ? t("detail.compare.comparing") : t("detail.compare.submit")}
        </button>
      </div>
      {from === to && <p className="mt-2 text-xs text-warn">{t("detail.compare.different")}</p>}
      {error && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {error}
        </p>
      )}
      {diff && <DiffView diff={diff} />}
    </div>
  );
}

function VersionSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: number;
  options: number[];
  onChange: (v: number) => void;
}) {
  return (
    <label className="flex items-center gap-1 text-muted">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="rounded-md border border-line bg-raised px-2 py-1 text-ink"
      >
        {options.map((n) => (
          <option key={n} value={n}>
            v{n}
          </option>
        ))}
      </select>
    </label>
  );
}

function DiffView({ diff }: { diff: VersionDiff }) {
  const t = useT();
  const changedFields = diff.catr_fields;
  const changedDiag = diff.diagnostics.filter((d) => d.changed);
  const changedRenders = diff.renders.filter((r) => r.changed);
  return (
    <div className="mt-4 space-y-3 text-sm">
      <p className="text-muted">{diff.summary}</p>
      <p className="rounded-lg border border-line bg-raised p-2 text-xs italic text-muted">
        {diff.note}
      </p>

      {changedFields.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-subtle">
            {t("detail.diff.catr")}
          </h4>
          <ul className="mt-1 space-y-1">
            {changedFields.map((c) => (
              <li key={c.path} className="rounded-md border border-line bg-raised p-2">
                <span className="font-mono text-accent-ink">{c.path}</span>{" "}
                <span className="text-xs uppercase text-subtle">{c.change}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {changedDiag.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-subtle">
            {t("detail.diff.diagnostic")}
          </h4>
          <ul className="mt-1 space-y-1">
            {changedDiag.map((d) => (
              <li key={d.dimension} className="text-muted">
                {d.dimension} : <span className="text-subtle">{d.before ?? "—"}</span> →{" "}
                <span className="text-ink">{d.after ?? "—"}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {changedRenders.map((r) => (
        <details key={r.mode} className="rounded-lg border border-line bg-raised p-2">
          <summary className="cursor-pointer text-xs font-semibold text-muted">
            {t("detail.diff.render", { mode: r.mode })}
          </summary>
          <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap font-mono text-xs text-muted">
            {r.unified_diff}
          </pre>
        </details>
      ))}

      {changedFields.length === 0 && changedDiag.length === 0 && changedRenders.length === 0 && (
        <p className="text-muted">{t("detail.diff.none")}</p>
      )}
    </div>
  );
}
