import { useEffect, useRef, useState, type MouseEvent } from "react";
import {
  toolPaths,
  toolCatalog,
  publicTools,
  shortcutTools,
  toolGroups,
  type PublicTool,
} from "./published-routes";
import { ToolIcon } from "./ToolIcon";

export function ToolNavigation({
  active,
  keepCurrent,
  disabled,
  choose,
}: {
  active?: PublicTool;
  keepCurrent: boolean;
  disabled: boolean;
  choose: (tool: PublicTool) => void;
}) {
  const [open, setOpen] = useState(false);
  const host = useRef<HTMLDivElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const expanded = open && !disabled;
  function close(restoreFocus = false) {
    setOpen(false);
    if (restoreFocus) toggle.current?.focus({ preventScroll: true });
  }
  function select(event: MouseEvent<HTMLAnchorElement>, id: PublicTool) {
    // Preserve native links for opening a clean tool in another tab.
    if (
      !disabled &&
      (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
    )
      return;
    event.preventDefault();
    if (disabled) return;
    toggle.current?.focus({ preventScroll: true });
    close();
    if (id !== active || !keepCurrent) choose(id);
  }
  useEffect(() => {
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !host.current?.contains(event.target))
        setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && open) {
        event.preventDefault();
        setOpen(false);
        toggle.current?.focus({ preventScroll: true });
      }
    };
    const media = window.matchMedia("(min-width: 1100px)");
    const resize = () => setOpen(false);
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    media.addEventListener("change", resize);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
      media.removeEventListener("change", resize);
    };
  }, [open]);
  return (
    <div
      className="tool-navigation"
      ref={host}
      data-open={expanded}
      onKeyDown={(event) => {
        if (
          !expanded ||
          event.key !== "Tab" ||
          event.altKey ||
          event.ctrlKey ||
          event.metaKey
        )
          return;
        // WebKit can skip buttons and links in its native Tab order. Keep
        // the open panel reachable, while leaving both boundaries untrapped.
        const stops = [
          toggle.current,
          ...event.currentTarget.querySelectorAll<HTMLElement>(
            '.tool-nav button:not(:disabled), .tool-nav a[href]:not([aria-disabled="true"])',
          ),
        ];
        const index = stops.indexOf(document.activeElement as HTMLElement);
        if (index < 0) return;
        const next = stops[index + (event.shiftKey ? -1 : 1)];
        if (next) {
          event.preventDefault();
          next.focus({ preventScroll: true });
        }
      }}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) close();
      }}
    >
      <nav className="tool-shortcuts" aria-label="Popular PDF tools">
        {shortcutTools.map((id) => (
          <a
            key={id}
            href={toolPaths[id]}
            aria-disabled={disabled}
            aria-current={active === id ? "page" : undefined}
            onClick={(event) => select(event, id)}
          >
            {toolCatalog[id].title}
          </a>
        ))}
      </nav>
      <button
        ref={toggle}
        className="tools-toggle secondary"
        aria-expanded={expanded}
        aria-controls="header-tools"
        disabled={disabled}
        onClick={() => setOpen(!open)}
      >
        <span className="tools-desktop-label">All PDF tools</span>
        <span className="tools-mobile-label">Tools</span>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      <nav
        id="header-tools"
        className="tool-nav"
        aria-label="PDF tools"
        hidden={!expanded}
      >
        <div className="tools-menu-heading">
          <strong>All PDF tools</strong>
          <button
            ref={closeButton}
            className="tools-close secondary"
            aria-label="Close tools"
            onClick={() => close(true)}
          >
            ×
          </button>
        </div>
        <div className="tool-menu-groups">
          {toolGroups.map((group) => (
            <section className="tool-menu-group" key={group} aria-label={group}>
              <h2>{group}</h2>
              {publicTools
                .filter((id) => toolCatalog[id].group === group)
                .map((id) => (
                  <a
                    role="button"
                    href={toolPaths[id]}
                    key={id}
                    aria-label={toolCatalog[id].label}
                    className={active === id ? "active" : ""}
                    aria-current={active === id ? "page" : undefined}
                    aria-disabled={disabled}
                    onClick={(event) => select(event, id)}
                  >
                    <ToolIcon tool={id} />
                    <span>{toolCatalog[id].title}</span>
                  </a>
                ))}
            </section>
          ))}
        </div>
      </nav>
    </div>
  );
}
