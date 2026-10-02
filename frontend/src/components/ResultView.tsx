import type { ReactNode } from "react";
import type { CompileResponse } from "../lib/api";
import { CopyButton } from "./CopyButton";
import { Diagnostics } from "./Diagnostics";
import { VariantTabs } from "./VariantTabs";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-kompilo-border bg-kompilo-panel p-5 sm:p-6">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-kompilo-blue-300">{title}</h2>
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
        <p className="text-lg text-white">{understood.objective}</p>
        <span className="mt-2 inline-block rounded-md border border-kompilo-border bg-kompilo-raised px-2 py-0.5 text-xs text-slate-300">
          domaine : {understood.domain}
        </span>
      </Section>

      {/* 2. Critical questions (only when the engine needs clarification) */}
      {questions.length > 0 && (
        <section
          className="rounded-2xl border border-amber-500/40 bg-amber-500/10 p-5 sm:p-6"
          role="alert"
        >
          <h2 className="text-sm font-semibold uppercase tracking-wider text-amber-300">
            Questions à clarifier
          </h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-amber-100">
            {questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-amber-200/80">
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
      <details className="group rounded-2xl border border-kompilo-border bg-kompilo-panel p-5 sm:p-6">
        <summary className="cursor-pointer list-none text-sm font-semibold text-slate-300 hover:text-white">
          <span className="text-kompilo-blue-300">Détails</span> — plan d'exécution, coûts, sections,
          métadonnées
        </summary>

        <div className="mt-4 space-y-4 text-sm">
          {execution_plan && (
            <div>
              <h3 className="font-semibold text-slate-200">Plan d'exécution</h3>
              <p className="mt-1 text-slate-400">
                Stratégie : <span className="text-slate-200">{execution_plan.strategy}</span> · Modèle :{" "}
                <span className="text-slate-200">{execution_plan.target_model ?? "—"}</span>
                {execution_plan.fallback_models.length > 0 && (
                  <> · Repli : {execution_plan.fallback_models.join(", ")}</>
                )}
              </p>
              <ol className="mt-2 list-decimal space-y-1 pl-5 text-slate-400">
                {execution_plan.steps.map((s) => (
                  <li key={s.order}>
                    <span className="text-slate-300">{s.action}</span> — {s.detail}
                  </li>
                ))}
              </ol>
              <p className="mt-2 text-slate-400">
                Coût{" "}
                <span className="rounded bg-kompilo-raised px-1.5 py-0.5 text-xs uppercase text-amber-300">
                  estimé
                </span>{" "}
                : ~${execution_plan.cost.cost_usd_est.toFixed(5)} ({execution_plan.cost.input_tokens_est}{" "}
                in / {execution_plan.cost.output_tokens_est} out tokens)
              </p>
              <p className="mt-1 text-xs text-slate-500">{execution_plan.cost.disclaimer}</p>
            </div>
          )}

          {compiled_prompt && (
            <div>
              <h3 className="font-semibold text-slate-200">Sections de l'IR</h3>
              <p className="mt-1 text-slate-400">{compiled_prompt.sections.join(" · ")}</p>
            </div>
          )}

          <div>
            <div className="flex items-center gap-3">
              <h3 className="font-semibold text-slate-200">Métadonnées</h3>
              <CopyButton text={JSON.stringify(data, null, 2)} label="Copier le JSON" />
            </div>
            <ul className="mt-1 space-y-1 text-slate-400">
              <li>moteur : {metadata.engine}</li>
              <li>déterministe : {metadata.deterministic ? "oui" : "non"}</li>
              <li>LLM utilisé : {metadata.llm_used ? "oui" : "non"}</li>
              <li>coûts estimés : {metadata.costs_estimated ? "oui" : "non"}</li>
              {metadata.notes.map((n, i) => (
                <li key={i} className="text-slate-500">
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
