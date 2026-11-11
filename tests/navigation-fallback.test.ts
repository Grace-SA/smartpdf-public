import { expect, it, vi } from "vitest";
import { pushToolPath } from "../src/platform/navigation";
it("reloads the selected tool if the browser silently ignores a history write", () => {
  const assign = vi.fn();
  expect(
    pushToolPath("/split-pdf/", {
      location: { pathname: "/merge-pdf/", assign },
      history: { pushState: vi.fn() },
    }),
  ).toBe(false);
  expect(assign).toHaveBeenCalledWith("/split-pdf/");
});
it("recovers from browser history quotas without emitting an uncaught error", () => {
  const assign = vi.fn();
  expect(
    pushToolPath("/split-pdf/", {
      location: { pathname: "/", assign },
      history: {
        pushState() {
          throw new DOMException("Quota", "SecurityError");
        },
      },
    }),
  ).toBe(false);
  expect(assign).toHaveBeenCalledOnce();
});
it("preserves ordinary same-document history and avoids duplicate entries", () => {
  const location = { pathname: "/", assign: vi.fn() };
  const pushState = vi.fn((_s: unknown, _u: string, p: string) => {
    location.pathname = p;
  });
  const target = { location, history: { pushState } };
  expect(pushToolPath("/merge-pdf/", target)).toBe(true);
  expect(pushToolPath("/merge-pdf/", target)).toBe(true);
  expect(pushState).toHaveBeenCalledOnce();
  expect(location.assign).not.toHaveBeenCalled();
});
