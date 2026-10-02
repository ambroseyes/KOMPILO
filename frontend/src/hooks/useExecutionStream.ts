import { useEffect, useState } from "react";
import { API_URL } from "../lib/api";

export type StreamStatus = "idle" | "connecting" | "streaming" | "done" | "error";

export interface StreamStep {
  order: number;
  action: string;
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  cached: boolean;
  latency_ms: number;
}

export interface ExecutionStream {
  text: string;
  steps: StreamStep[];
  status: StreamStatus;
  error: string | null;
}

/**
 * Subscribe to an execution's SSE stream and surface the response progressively.
 *
 * Non-blocking: EventSource delivers events asynchronously; the component re-renders
 * as `text` grows. Robust close: the EventSource is closed on `done`, on any error,
 * and on unmount / dependency change (the effect cleanup). The access token is passed
 * as a query param because EventSource cannot set an Authorization header.
 */
export function useExecutionStream(
  executionId: string | null,
  token: string | null,
): ExecutionStream {
  const [text, setText] = useState("");
  const [steps, setSteps] = useState<StreamStep[]>([]);
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!executionId || !token) return;

    setText("");
    setSteps([]);
    setError(null);
    setStatus("connecting");

    const url = `${API_URL}/v1/executions/${executionId}/stream?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);

    const onStep = (e: MessageEvent) => {
      setStatus("streaming");
      try {
        setSteps((prev) => [...prev, JSON.parse(e.data) as StreamStep]);
      } catch {
        /* ignore malformed event */
      }
    };
    const onToken = (e: MessageEvent) => {
      setStatus("streaming");
      try {
        const chunk = (JSON.parse(e.data) as { text?: string }).text ?? "";
        setText((prev) => prev + chunk);
      } catch {
        /* ignore malformed event */
      }
    };
    const onDone = () => {
      setStatus("done");
      es.close();
    };
    // Fires for both a server-sent `error` event and a connection error; never
    // downgrades a stream that already completed.
    const onFail = () => {
      setStatus((prev) => (prev === "done" ? prev : "error"));
      setError((prev) => prev ?? "La connexion au flux a été interrompue.");
      es.close();
    };

    es.addEventListener("step", onStep);
    es.addEventListener("token", onToken);
    es.addEventListener("done", onDone);
    es.addEventListener("error", onFail);

    return () => {
      es.close();
    };
  }, [executionId, token]);

  return { text, steps, status, error };
}
