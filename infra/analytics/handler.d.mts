export type AnalyticsEvent = {
  schema: 1;
  event: string;
  tool: string;
  file_count?: string;
  size_mib?: string;
  pages?: string;
  duration_ms?: string;
  reason?: string;
};

export function validate(body: unknown): AnalyticsEvent | null;
export function handler(event: { body?: string }): Promise<{
  statusCode: number;
  body: string;
}>;
