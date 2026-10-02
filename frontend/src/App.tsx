import { useQuery } from "@tanstack/react-query";
import { api } from "./lib/api";

export default function App() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["readiness"],
    queryFn: api.readiness,
  });

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-6">
      <div className="w-full max-w-lg rounded-2xl border border-slate-800 bg-slate-900/60 p-8 shadow-xl">
        <h1 className="text-3xl font-bold tracking-tight">Kompilo</h1>
        <p className="mt-1 text-sm text-slate-400">AI Execution Intelligence</p>

        <div className="mt-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
            Backend status
          </h2>

          {isLoading && <p className="mt-2 text-slate-300">Checking…</p>}

          {isError && (
            <p className="mt-2 text-red-400">
              Unreachable: {(error as Error).message}
            </p>
          )}

          {data && (
            <ul className="mt-3 space-y-2">
              <li className="text-slate-200">
                Overall:{" "}
                <span className={data.status === "ok" ? "text-emerald-400" : "text-amber-400"}>
                  {data.status}
                </span>
              </li>
              {data.components.map((c) => (
                <li key={c.name} className="flex items-center gap-2">
                  <span className={c.ok ? "text-emerald-400" : "text-red-400"}>
                    {c.ok ? "●" : "○"}
                  </span>
                  <span className="text-slate-300">{c.name}</span>
                  {c.detail && <span className="text-xs text-slate-500">({c.detail})</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
