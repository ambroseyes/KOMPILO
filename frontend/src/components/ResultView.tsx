import type { ReactNode } from "react";
import type { CompileResponse } from "../lib/api";
import { CopyButton } from "./CopyButton";
import { Diagnostics } from "./Diagnostics";
import { VariantTabs } from "./VariantTabs";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-line bg-surface p-5 sm:p-6">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-accent-ink">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

export function ResultView({ data }: { data: CompileResponse }) {
  const { understood, questions, compiled_prompt, renders, diagnostics, execution_plan, metadata } =
    data;

  return (
    <div className="space-y-4">
      {/* 1. Understood intent */}
      <Section title="Intention comprise">
        <p className="text-lg text-ink">{understood.objective}</p>
        <span className="mt-2 inline-block rounded-md border border-line bg-raised px-2 py-0.5 text-xs text-muted">
          domaine : {understood.domain}
        </span>
      </Section>

      {/* 2. Critical questions (only when the engine needs clarification) */}
      {questions.length > 0 && (
        <section
          className="rounded-2xl border border-warn/40 bg-warn/10 p-5 sm:p-6"
          role="alert"
        >
          <h2 className="text-sm font-semibold uppercase tracking-wider text-warn">
            Questions à clarifier
          </h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-ink">
            {questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-warn">
            Précise ces points puis relance la compilation pour obtenir l'instruction.
          </p>
        </section>
      )}

      {/* 3. Compiled instruction + 4. variants (tabs) */}
      {compiled_prompt && renders && (
        <Section title="Instruction compilée">
          <VariantTabs renders={renders} initial={compiled_prompt.mode} />
        </Section>
      )}

      {/* 5. Multidimensional diagnostic */}
      {diagnostics.length > 0 && (
        <Section title="Diagnostic">
          <Diagnostics items={diagnostics} />
        </Section>
      )}

      {/* Progressive disclosure: everything technical, folded by default. */}
      <details className="group rounded-2xl border border-line bg-surface p-5 sm:p-6">
        <summary className="cursor-pointer list-none text-sm font-semibold text-muted hover:text-ink">
          <span className="text-accent-ink">Détails</span> — plan d'exécution, coûts, sections,
          métadonnées
        </summary>

        <div className="mt-4 space-y-4 text-sm">
          {execution_plan && (
            <div>
              <h3 className="font-semibold text-ink">Plan d'exécution</h3>
              <p className="mt-1 text-muted">
                Stratégie : <span className="text-ink">{execution_plan.strategy}</span> · Modèle :{" "}
                <span className="text-ink">{execution_plan.target_model ?? "—"}</span>
                {execution_plan.fallback_models.length > 0 && (
                  <> · Repli : {execution_plan.fallback_models.join(", ")}</>
                )}
              </p>
              <ol className="mt-2 list-decimal space-y-1 pl-5 text-muted">
                {execution_plan.steps.map((s) => (
                  <li key={s.order}>
                    <span className="text-ink">{s.action}</span> — {s.detail}
                  </li>
                ))}
              </ol>
              <p className="mt-2 text-muted">
                Coût{" "}
                <span className="rounded bg-raised px-1.5 py-0.5 text-xs uppercase text-warn">
                  estimé
                </span>{" "}
                : ~${execution_plan.cost.cost_usd_est.toFixed(5)} ({execution_plan.cost.input_tokens_est}{" "}
                in / {execution_plan.cost.output_tokens_est} out tokens)
              </p>
              <p className="mt-1 text-xs text-subtle">{execution_plan.cost.disclaimer}</p>
            </div>
          )}

          {compiled_prompt && (
            <div>
              <h3 className="font-semibold text-ink">Sections de l'IR</h3>
              <p className="mt-1 text-muted">{compiled_prompt.sections.join(" · ")}</p>
            </div>
          )}

          <div>
            <div className="flex items-center gap-3">
              <h3 className="font-semibold text-ink">Métadonnées</h3>
              <CopyButton text={JSON.stringify(data, null, 2)} label="Copier le JSON" />
            </div>
            <ul className="mt-1 space-y-1 text-muted">
              <li>moteur : {metadata.engine}</li>
              <li>déterministe : {metadata.deterministic ? "oui" : "non"}</li>
              <li>LLM utilisé : {metadata.llm_used ? "oui" : "non"}</li>
              <li>coûts estimés : {metadata.costs_estimated ? "oui" : "non"}</li>
              {metadata.notes.map((n, i) => (
                <li key={i} className="text-subtle">
                  note : {n}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </details>
    </div>
  );
}
