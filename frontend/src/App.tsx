import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, type CompileMode, type CompileResponse } from "./lib/api";
import { CompileForm } from "./components/CompileForm";
import { ExecutionPanel } from "./components/ExecutionPanel";
import { LibraryPage } from "./components/LibraryPage";
import { ResultView } from "./components/ResultView";

type View = "compile" | "library";

export default function App() {
  const [view, setView] = useState<View>("compile");
  const [task, setTask] = useState("");
  const [mode, setMode] = useState<CompileMode>("professional");

  const mutation = useMutation<CompileResponse, Error, void>({
    mutationFn: () => api.compile({ task: task.trim(), mode }),
  });

  return (
    <div className="min-h-screen">
      <main className="mx-auto w-full max-w-3xl px-4 py-10 sm:py-16">
        <header className="mb-8">
          <h1 className="text-2xl font-bold tracking-tight text-white">
            Kompilo<span className="text-kompilo-blue">.</span>
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            AI Execution Intelligence — transforme une intention en stratégie d'exécution.
          </p>
          <nav className="mt-4 flex gap-1 rounded-xl border border-kompilo-border bg-kompilo-panel p-1 text-sm">
            {(["compile", "library"] as const).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setView(v)}
                className={
                  "rounded-lg px-4 py-1.5 font-medium transition " +
                  (view === v
                    ? "bg-kompilo-blue text-white"
                    : "text-slate-400 hover:text-white")
                }
              >
                {v === "compile" ? "Compiler" : "Bibliothèque"}
              </button>
            ))}
          </nav>
        </header>

        {view === "library" && <LibraryPage />}

        {view === "compile" && (
          <>
            <CompileForm
              value={task}
              onChange={setTask}
              mode={mode}
              onModeChange={setMode}
              onSubmit={() => mutation.mutate()}
              isPending={mutation.isPending}
            />

            {/* Live region so screen readers announce state changes. */}
            <div className="mt-6" aria-live="polite" aria-busy={mutation.isPending}>
              {mutation.isPending && (
                <div className="rounded-2xl border border-kompilo-border bg-kompilo-panel p-6 text-slate-300">
                  <span className="inline-flex items-center gap-2">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-kompilo-blue" />
                    Compilation en cours…
                  </span>
                </div>
              )}

              {mutation.isError && (
                <div
                  role="alert"
                  className="rounded-2xl border border-red-500/40 bg-red-500/10 p-6 text-red-200"
                >
                  <p className="font-semibold">La compilation a échoué.</p>
                  <p className="mt-1 text-sm text-red-300/90">{mutation.error.message}</p>
                </div>
              )}

              {mutation.isSuccess && <ResultView data={mutation.data} />}

              {mutation.isSuccess && mutation.data.questions.length === 0 && (
                <details className="mt-4 rounded-2xl border border-kompilo-border bg-kompilo-panel p-5 sm:p-6">
                  <summary className="cursor-pointer list-none text-sm font-semibold text-slate-300 hover:text-white">
                    <span className="text-kompilo-blue-300">Exécution en direct</span> (avancé)
                  </summary>
                  <ExecutionPanel task={task} />
                </details>
              )}
            </div>
          </>
        )}

        <footer className="mt-12 text-center text-xs text-slate-600">
          Kompilo · le cœur de compilation est déterministe · coûts affichés = estimés
        </footer>
      </main>
    </div>
  );
}
