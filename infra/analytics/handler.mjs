const events = new Set([
  "tool_view",
  "file_selected",
  "process_start",
  "process_success",
  "process_failure",
  "process_cancel",
  "download",
  "download_failure",
]);
const tools = new Set([
  "combine",
  "split",
  "organize",
  "photos",
  "sign",
  "compress",
  "rotate",
  "raster",
  "watermark",
  "numbers",
  "unlock",
  "protect",
]);
const reasons = new Set([
  "cancelled",
  "timeout",
  "unsupported",
  "resource_limit",
  "validation",
  "worker",
  "unknown",
]);
const bucket = /^(<=|>)[0-9]+$/;
const allowedKeys = new Set([
  "schema",
  "event",
  "tool",
  "file_count",
  "size_mib",
  "pages",
  "duration_ms",
  "reason",
]);

export function validate(body) {
  if (!body || typeof body !== "object" || Array.isArray(body)) return null;
  if (Object.keys(body).some((key) => !allowedKeys.has(key))) return null;
  if (body.schema !== 1 || !events.has(body.event) || !tools.has(body.tool))
    return null;
  for (const key of ["file_count", "size_mib", "pages", "duration_ms"])
    if (body[key] !== undefined && !bucket.test(body[key])) return null;
  if (body.reason !== undefined && !reasons.has(body.reason)) return null;
  return body;
}

export async function handler(event) {
  const raw = event?.body ?? "";
  if (typeof raw !== "string" || Buffer.byteLength(raw) > 2048)
    return { statusCode: 413, body: "" };
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { statusCode: 400, body: "" };
  }
  const data = validate(parsed);
  if (!data) return { statusCode: 400, body: "" };

  // Keep MVP analytics in structured logs rather than publishing a custom
  // metric for every tool/event combination. Logs Insights can calculate the
  // funnel on demand without the standing cost of dozens of custom metrics.
  const record = {
    schema: data.schema,
    event: data.event,
    tool: data.tool,
    file_count: data.file_count,
    size_mib: data.size_mib,
    pages: data.pages,
    duration_ms: data.duration_ms,
    reason: data.reason,
  };
  console.log(JSON.stringify(record));
  return { statusCode: 204, body: "" };
}
