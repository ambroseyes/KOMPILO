import { useQuery } from "@tanstack/react-query";
import { api } from "./lib/api";

export default function App() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
  });

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-6">
      <div className="w-full max-w-lg rounded-2xl border border-slate-800 bg-slate-900/60 p-8 shadow-xl">
        <h1 className="text-3xl font-bold tracking-tight">Kompilo</h1>
        <p className="mt-1 text-sm text-slate-400">AI Execution Intelligence</p>

        <div className="mt-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
            Backend health
          </h2>

          {isLoading && <p className="mt-2 text-slate-300">Checking…</p>}

          {isError && (
            <p className="mt-2 text-red-400">Unreachable: {(error as Error).message}</p>
          )}

          {data && (
            <ul className="mt-3 space-y-2">
              <li className="flex items-center gap-2">
                <span className={data.status === "ok" ? "text-emerald-400" : "text-amber-400"}>
                  {data.status === "ok" ? "●" : "○"}
                </span>
                <span className="text-slate-300">status</span>
                <span className="text-slate-400">{data.status}</span>
              </li>
              <li className="flex items-center gap-2">
                <span className={data.db === "ok" ? "text-emerald-400" : "text-red-400"}>
                  {data.db === "ok" ? "●" : "○"}
                </span>
                <span className="text-slate-300">database</span>
                <span className="text-slate-400">{data.db}</span>
              </li>
              <li className="text-xs text-slate-500">version {data.version}</li>
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
