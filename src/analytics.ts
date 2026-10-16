import type { PublicTool } from "./routes";

export type AnalyticsEvent =
  | "tool_view"
  | "file_selected"
  | "process_start"
  | "process_success"
  | "process_failure"
  | "process_cancel"
  | "download"
  | "download_failure";

type EventDetails = {
  fileCount?: number;
  totalBytes?: number;
  pages?: number;
  durationMs?: number;
  reason?:
    | "cancelled"
    | "timeout"
    | "unsupported"
    | "resource_limit"
    | "validation"
    | "worker"
    | "unknown";
};

export type AnalyticsPayload = {
  schema: 1;
  event: AnalyticsEvent;
  tool: PublicTool;
  file_count?: string;
  size_mib?: string;
  pages?: string;
  duration_ms?: string;
  reason?: EventDetails["reason"];
};

const endpoint = import.meta.env.VITE_ANALYTICS_ENDPOINT?.trim();

const bucket = (value: number | undefined, bounds: number[]) => {
  if (value === undefined || !Number.isFinite(value) || value < 0)
    return undefined;
  const limit = bounds.find((candidate) => value <= candidate);
  return limit === undefined ? `>${bounds.at(-1)}` : `<=${limit}`;
};

/**
 * Send only an allow-listed, aggregate-friendly event. Never send file names,
 * document bytes, free-form errors, URLs, account IDs or persistent user IDs.
 */
export function track(
  event: AnalyticsEvent,
  tool: PublicTool,
  details: EventDetails = {},
) {
  if (!endpoint || typeof navigator === "undefined") return;
  const payload = JSON.stringify(buildAnalyticsPayload(event, tool, details));
  try {
    if (
      typeof navigator.sendBeacon === "function" &&
      navigator.sendBeacon(
        endpoint,
        new Blob([payload], { type: "text/plain" }),
      )
    )
      return;
    void fetch(endpoint, {
      method: "POST",
      body: payload,
      headers: { "Content-Type": "text/plain" },
      keepalive: true,
      credentials: "omit",
      referrerPolicy: "no-referrer",
    }).catch(() => undefined);
  } catch {
    // Analytics must never block or alter a PDF task.
  }
}

export function buildAnalyticsPayload(
  event: AnalyticsEvent,
  tool: PublicTool,
  details: EventDetails = {},
): AnalyticsPayload {
  return {
    schema: 1,
    event,
    tool,
    file_count: bucket(details.fileCount, [1, 2, 5, 10, 20]),
    size_mib: bucket(
      details.totalBytes === undefined
        ? undefined
        : details.totalBytes / 1024 / 1024,
      [1, 5, 10, 30, 50],
    ),
    pages: bucket(details.pages, [1, 5, 20, 50, 100, 200]),
    duration_ms: bucket(details.durationMs, [500, 1000, 3000, 10_000, 30_000]),
    reason: details.reason,
  };
}

export function analyticsReason(error: unknown, timedOut = false) {
  if (timedOut) return "timeout" as const;
  const message = error instanceof Error ? error.message.toLowerCase() : "";
  if (/cancel|abort/.test(message)) return "cancelled" as const;
  if (/limit|large|capacity|budget|size|pages/.test(message))
    return "resource_limit" as const;
  if (/unsupported|cannot be|unavailable|encrypted|password/.test(message))
    return "unsupported" as const;
  if (/valid|preview|page count|structure/.test(message))
    return "validation" as const;
  if (/worker|engine|stopped/.test(message)) return "worker" as const;
  return "unknown" as const;
}
