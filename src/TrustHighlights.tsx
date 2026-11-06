type Variant = "home" | "workspace" | "result";

const highlights = [
  {
    icon: "device",
    title: "Processed on your device",
    text: "Your browser does the work locally.",
  },
  {
    icon: "cloud",
    title: "No file upload",
    text: "Files and filenames never reach our servers.",
  },
  {
    icon: "original",
    title: "Originals stay untouched",
    text: "Every change creates a new file.",
  },
  {
    icon: "account",
    title: "No account required",
    text: "Use every tool without signing in.",
  },
] as const;

function TrustIcon({ name }: { name: (typeof highlights)[number]["icon"] }) {
  if (name === "device")
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="5" y="3" width="14" height="18" rx="2" />
        <path d="M9 17h6M10 7h4" />
      </svg>
    );
  if (name === "cloud")
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M7 18h10a4 4 0 0 0 .6-7.95A6 6 0 0 0 6.2 8.2 4.9 4.9 0 0 0 7 18Z" />
        <path d="m8 8 8 8M16 8l-8 8" />
      </svg>
    );
  if (name === "original")
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M7 3h7l4 4v14H7zM14 3v5h4" />
        <path d="m9.5 14 1.7 1.7 3.6-4" />
      </svg>
    );
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="8" r="3" />
      <path d="M6.5 19a5.5 5.5 0 0 1 11 0M4 4l16 16" />
    </svg>
  );
}

export function TrustHighlights({ variant }: { variant: Variant }) {
  const visible = highlights.slice(0, 3);
  return (
    <section
      className={`trust-highlights trust-${variant}`}
      aria-label="Your privacy with Smart PDF"
    >
      <div className="trust-items">
        {visible.map((original) => {
          const item =
            variant === "home" && original.icon === "device"
              ? {
                  ...original,
                  title: "Local PDF tools",
                  text: "PDF editing runs in your browser.",
                }
              : variant === "home" && original.icon === "cloud"
                ? {
                    ...original,
                    title: "Clearly marked cloud conversion",
                    text: "Office documents upload only when you start.",
                  }
                : original;
          return (
            <article key={item.title}>
              <span className="trust-icon">
                <TrustIcon name={item.icon} />
              </span>
              <div>
                <h3>{item.title}</h3>
                <p>{item.text}</p>
              </div>
            </article>
          );
        })}
      </div>
      {variant === "result" && (
        <p className="trust-footnote">Created locally. Nothing was uploaded.</p>
      )}
    </section>
  );
}
