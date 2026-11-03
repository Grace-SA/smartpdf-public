import { enabledTools, toolFromPath as catalogPath } from "./routes";
export {
  toolCatalog,
  toolGroups,
  toolPaths,
  shortcutTools,
  absoluteUrl,
} from "./routes";
export type { PublicTool } from "./routes";

// Development and CI can review Protect without publishing its entry points.
const reviewProtect =
  !import.meta.env.PROD || import.meta.env.VITE_ENABLE_PROTECT === "true";
export const publicTools = enabledTools(reviewProtect);
export const toolFromPath = (pathname: string) =>
  catalogPath(pathname, publicTools);
