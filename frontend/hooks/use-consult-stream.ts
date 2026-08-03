"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { authHeaders } from "@/lib/auth-store";
import type { CustomerConsultationRequest } from "@/lib/types";

export interface ConsultEvent {
  event: string;
  data: Record<string, unknown>;
}

/**
 * Consumes the SSE consultation stream via fetch + ReadableStream (POST body
 * is required, so EventSource is not an option). Exposes the public event
 * trail only — never internal chain-of-thought.
 */
export function useConsultStream() {
  const [events, setEvents] = useState<ConsultEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [finalResponse, setFinalResponse] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setRunning(false);
  }, []);

  // Abort an in-flight SSE stream when the component unmounts so a client
  // navigation does not leave the connection open.
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const run = useCallback(async (payload: CustomerConsultationRequest) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setEvents([]);
    setFinalResponse(null);
    setError(null);
    setRunning(true);
    try {
      const response = await fetch("/api/v1/customer-consultations/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      if (!response.ok) {
        let message = `请求失败（HTTP ${response.status}）`;
        try {
          const body = await response.json();
          message = body?.error?.message ?? message;
        } catch {
          /* keep default */
        }
        throw new Error(message);
      }
      if (!response.body) throw new Error("响应不支持流式输出");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let boundary: number;
        while ((boundary = buffer.indexOf("\n\n")) !== -1) {
          const block = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          const lines = block.split("\n");
          let event = "message";
          const dataLines: string[] = [];
          for (const line of lines) {
            if (line.startsWith("event:")) event = line.slice(6).trim();
            else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
          }
          if (dataLines.length === 0) continue;
          let data: Record<string, unknown> = {};
          try {
            data = JSON.parse(dataLines.join("\n"));
          } catch {
            data = { raw: dataLines.join("\n") };
          }
          setEvents((prev) => [...prev, { event, data }]);
          if (event === "done" && typeof data.final_response === "string") {
            setFinalResponse(data.final_response);
          }
          if (event === "error") {
            throw new Error(typeof data.message === "string" ? data.message : "处理出错");
          }
        }
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      setError(err instanceof Error ? err.message : "处理出错");
    } finally {
      if (!controller.signal.aborted) setRunning(false);
    }
  }, []);

  return { events, running, finalResponse, error, run, cancel };
}
