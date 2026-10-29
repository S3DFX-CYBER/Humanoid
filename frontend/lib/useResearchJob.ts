import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError, type Job, type Stage } from "./api";

const POLL_INTERVAL_MS = 1500;
const MAX_POLL_FAILURES = 4;

export interface ResearchState {
  job: Job | null;
  stages: Stage[];
  error: string | null;
  isRunning: boolean;
  start: (topic: string, citationStyle?: string) => Promise<void>;
  retry: () => Promise<void>;
  reset: () => void;
}

const TERMINAL: Job["status"][] = ["done", "failed"];

export function useResearchJob(): ResearchState {
  const [job, setJob] = useState<Job | null>(null);
  const [stages, setStages] = useState<Stage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abort = useRef<AbortController | null>(null);
  const failures = useRef(0);

  const stopPolling = useCallback(() => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    abort.current?.abort();
    abort.current = null;
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const poll = useCallback(
    async (jobId: string) => {
      abort.current = new AbortController();

      try {
        const [nextJob, nextStages] = await Promise.all([
          api.getJob(jobId, abort.current.signal),
          api.listStages(jobId, abort.current.signal),
        ]);

        failures.current = 0;
        setJob(nextJob);
        setStages(nextStages);

        if (TERMINAL.includes(nextJob.status)) {
          setIsRunning(false);
          if (nextJob.status === "failed") {
            const failedStage = nextStages.find((s) => s.status === "failed");
            setError(
              failedStage?.error ??
                "The pipeline stopped before finishing. Retry to continue from the last completed step.",
            );
          }
          return;
        }
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === "AbortError") return;

        failures.current += 1;
        if (failures.current >= MAX_POLL_FAILURES) {
          setIsRunning(false);
          setError(
            caught instanceof ApiError
              ? caught.message
              : "Lost contact with the server while this job was running.",
          );
          return;
        }
      }

      timer.current = setTimeout(() => void poll(jobId), POLL_INTERVAL_MS);
    },
    [],
  );

  const start = useCallback(
    async (topic: string, citationStyle = "apa") => {
      stopPolling();
      setError(null);
      setStages([]);
      setIsRunning(true);
      failures.current = 0;

      try {
        const created = await api.createJob(topic, citationStyle);
        setJob(created);
        void poll(created.id);
      } catch (caught) {
        setIsRunning(false);
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Could not start this job.",
        );
      }
    },
    [poll, stopPolling],
  );

  const retry = useCallback(async () => {
    if (!job) return;
    stopPolling();
    setError(null);
    setIsRunning(true);
    failures.current = 0;

    try {
      const requeued = await api.retryJob(job.id);
      setJob(requeued);
      void poll(requeued.id);
    } catch (caught) {
      setIsRunning(false);
      setError(
        caught instanceof ApiError ? caught.message : "Could not retry this job.",
      );
    }
  }, [job, poll, stopPolling]);

  const reset = useCallback(() => {
    stopPolling();
    setJob(null);
    setStages([]);
    setError(null);
    setIsRunning(false);
  }, [stopPolling]);

  return { job, stages, error, isRunning, start, retry, reset };
}
