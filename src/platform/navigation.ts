type NavigationTarget = {
  location: { pathname: string; assign(path: string): void };
  history: { pushState(data: unknown, unused: string, path: string): void };
};
// WebKit can reject or throttle frequent History API writes. Keep the visible
// tool and address bar consistent by opening the already-authorized clean task.
export function pushToolPath(
  path: string,
  target: NavigationTarget = window,
): boolean {
  if (target.location.pathname === path) return true;
  try {
    target.history.pushState({}, "", path);
    if (target.location.pathname === path) return true;
  } catch (error) {
    if (!(error instanceof DOMException) || error.name !== "SecurityError")
      throw error;
  }
  target.location.assign(path);
  return false;
}
