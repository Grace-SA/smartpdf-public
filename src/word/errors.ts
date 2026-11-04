export class WordRequestError extends Error {
  constructor(
    message: string,
    public code: string,
    public status = 0,
  ) {
    super(message);
  }
}
export function wordFailure(code: string | undefined, fallback?: string) {
  switch (code) {
    case "INPUT_REJECTED":
      return (
        fallback ||
        "This document needs changes in Word before converting. Choose a corrected copy."
      );
    case "ENGINE_STARTUP_FAILED":
      return "The conversion service could not start. Retry shortly; your original is unchanged.";
    case "INPUT_VIEW_PREPARATION_FAILED":
      return "Your chosen revision or comment view could not be prepared. Resolve it in Word and choose a new copy.";
    case "WORKER_TIMEOUT":
    case "CONVERSION_TIMEOUT":
      return "Conversion took too long. Try a smaller document or export from Word.";
    case "OUTPUT_INVALID":
      return "The PDF failed its checks and was not offered for download. Retry or export from Word.";
    case "CLEANUP_FAILED":
      return "Server cleanup could not be confirmed. Retry deletion before starting another conversion.";
    default:
      return (
        fallback || "Conversion could not finish. Retry, or export from Word."
      );
  }
}
export function responseFailure(
  status: number,
  value?: { error?: string; code?: string },
) {
  const defaults: Record<number, [string, string]> = {
    401: [
      "SESSION_EXPIRED",
      "Reopen this tool to start a new session. Your original is unchanged.",
    ],
    400: ["INVALID_OPTIONS", "Choose valid document output options."],
    403: [
      "SESSION_EXPIRED",
      "Reopen this tool to start a new session. Your original is unchanged.",
    ],
    404: [
      "TASK_EXPIRED",
      "This conversion has expired or was deleted. Start a new conversion.",
    ],
    410: [
      "TASK_EXPIRED",
      "This conversion has expired. Start a new conversion.",
    ],
    409: [
      "TASK_CONFLICT",
      "This task cannot continue. Delete its temporary files and try again.",
    ],
    413: ["INPUT_TOO_LARGE", "Choose a non-empty DOCX up to 30 MiB."],
    415: [
      "INPUT_TYPE",
      "Choose a DOCX document. Save older .doc files as .docx in Word first.",
    ],
    429: [
      "QUEUE_FULL",
      "The service is busy or the conversion queue is full. Try again shortly.",
    ],
    503: [
      "SERVICE_UNAVAILABLE",
      "Conversion is temporarily unavailable. Retry shortly.",
    ],
  };
  const [code, message] = defaults[status] || [
    "SERVICE_UNAVAILABLE",
    "The service returned an unexpected response. Retry shortly.",
  ];
  return new WordRequestError(
    value?.error || message,
    value?.code || code,
    status,
  );
}
export async function wordRequest<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const abort = new AbortController();
  const cancel = () => abort.abort(init?.signal?.reason);
  if (init?.signal?.aborted) cancel();
  else init?.signal?.addEventListener("abort", cancel, { once: true });
  const timer = setTimeout(() => abort.abort(), 15000);
  try {
    const response = await fetch(url, {
      credentials: "same-origin",
      ...init,
      signal: abort.signal,
    });
    let value;
    try {
      value = await response.json();
    } catch {
      if (abort.signal.aborted) throw abort.signal.reason;
      throw responseFailure(response.ok ? 502 : response.status);
    }
    if (!response.ok) throw responseFailure(response.status, value);
    return value as T;
  } catch (error) {
    if (init?.signal?.aborted || error instanceof WordRequestError) throw error;
    throw new WordRequestError(
      "Connection interrupted. Check your connection and retry. Temporary files may need deletion.",
      "NETWORK",
    );
  } finally {
    clearTimeout(timer);
    init?.signal?.removeEventListener("abort", cancel);
  }
}
