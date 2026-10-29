import { describe, expect, it, vi } from "vitest";
import { handler, validate } from "../infra/analytics/handler.mjs";
import { readFileSync } from "node:fs";
import { publicTools } from "../src/routes";

describe("analytics collector", () => {
  it("keeps standalone and deployable collector tool lists aligned with every public route", () => {
    for (const tool of publicTools)
      expect(validate({ schema: 1, event: "tool_view", tool })).not.toBeNull();
    const template = readFileSync("infra/site/template.yaml", "utf8");
    const list = template.match(/const tools = new Set\(\[([\s\S]*?)\]\)/)![1]!;
    expect(
      [...list.matchAll(/"([^"]+)"/g)].map((match) => match[1]).sort(),
    ).toEqual([...publicTools].sort());
  });
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
