import { describe, expect, it, vi } from "vitest";
import { handler, validate } from "../infra/analytics/handler.mjs";

describe("analytics collector", () => {
  it("rejects unexpected or identifying fields", () => {
    expect(
      validate({
        schema: 1,
        event: "download",
        tool: "compress",
        filename: "private.pdf",
      }),
    ).toBeNull();
    expect(
      validate({ schema: 1, event: "download", tool: "compress" }),
    ).not.toBeNull();
  });

  it("accepts a bounded event without echoing it", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const response = await handler({
      body: JSON.stringify({
        schema: 1,
        event: "process_success",
        tool: "compress",
        pages: "<=20",
      }),
    });
    expect(response).toEqual({ statusCode: 204, body: "" });
    expect(log).toHaveBeenCalledOnce();
    const record = JSON.parse(String(log.mock.calls[0]?.[0]));
    expect(record).toMatchObject({
      schema: 1,
      event: "process_success",
      tool: "compress",
      pages: "<=20",
    });
    expect(record).not.toHaveProperty("_aws");
    log.mockRestore();
  });
});
