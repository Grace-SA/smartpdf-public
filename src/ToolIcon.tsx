export function ToolIcon({ tool }: { tool: string }) {
  return (
    <svg
      viewBox="0 0 48 48"
      width="48"
      height="48"
      fill="none"
      aria-hidden="true"
      focusable="false"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {tool === "watermark" ? (
        <>
          <rect x="9" y="5" width="30" height="38" rx="3" />
          <path d="m14 30 8-16 5 12 4-8 5 12M16 25h8" />
        </>
      ) : tool === "raster" ? (
        <>
          <rect x="8" y="6" width="32" height="36" rx="3" />
          <circle cx="18" cy="17" r="3" />
          <path d="m10 35 11-11 7 7 5-5 7 9" />
        </>
      ) : tool === "rotate" ? (
        <>
          <path d="M37 17A15 15 0 1 0 38 32M37 6v11H26" />
          <rect x="18" y="17" width="12" height="17" rx="2" />
        </>
      ) : tool === "sign" ? (
        <>
          <path d="M8 38h32M12 30l4-10L33 3l9 9-17 17-13 1Z M16 20l9 9M29 7l9 9" />
        </>
      ) : tool === "compress" ? (
        <>
          <rect x="8" y="7" width="32" height="36" rx="3" />
          <path d="M14 17h8m12 0h-8m-4-4v8M14 33h8m12 0h-8m-4-4v8" />
        </>
      ) : tool === "combine" ? (
        <>
          <rect
            x="8"
            y="7"
            width="23"
            height="29"
            rx="3"
            opacity=".35"
            fill="currentColor"
            stroke="none"
          />
          <rect x="17" y="14" width="23" height="29" rx="3" />
          <path d="m5 23 8 0-3-3m3 3-3 3M27 27h7m-7 6h7" />
        </>
      ) : tool === "split" ? (
        <>
          <rect
            x="7"
            y="8"
            width="34"
            height="32"
            rx="3"
            opacity=".12"
            fill="currentColor"
            stroke="none"
          />
          <path d="M24 6v7m0 6v10m0 6v7M18 10H8v28h10m12-28h10v28H30M18 24H7m0 0 4-4m-4 4 4 4m19-4h11m0 0-4-4m4 4-4 4" />
        </>
      ) : tool === "organize" ? (
        <>
          <rect
            x="7"
            y="7"
            width="14"
            height="15"
            rx="2"
            fill="currentColor"
            opacity=".15"
          />
          <rect x="27" y="7" width="14" height="15" rx="2" />
          <rect x="7" y="28" width="14" height="15" rx="2" />
          <path d="M28 35h13m-4-4 4 4-4 4" />
        </>
      ) : (
        <>
          <rect
            x="6"
            y="12"
            width="30"
            height="29"
            rx="3"
            opacity=".2"
            fill="currentColor"
            stroke="none"
          />
          <rect x="12" y="7" width="30" height="29" rx="3" />
          <circle cx="21" cy="16" r="3" />
          <path d="m13 30 9-8 6 5 6-7 7 9" />
        </>
      )}
    </svg>
  );
}
