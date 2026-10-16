export type CompressionLevel = "recommended" | "smaller" | "quality";

export type CompressionSummary = {
  originalBytes: number;
  outputBytes: number;
  savedPercent: number;
  alreadyOptimized: boolean;
  level: CompressionLevel;
};

export const compressionOptions: {
  value: CompressionLevel;
  title: string;
  badge?: string;
  description: string;
  detail: string;
}[] = [
  {
    value: "recommended",
    title: "Recommended",
    badge: "Best for most PDFs",
    description: "Balanced size and quality",
    detail:
      "Recompresses suitable large images when that makes the file smaller.",
  },
  {
    value: "smaller",
    title: "Smaller file",
    description: "More compression for sharing",
    detail:
      "Uses stronger image recompression. Images may look softer when zoomed or printed.",
  },
  {
    value: "quality",
    title: "Highest quality",
    description: "Minimal visual change",
    detail:
      "Optimizes structure without intentionally reducing image quality. The saving may be small.",
  },
];

export function compressionArgs(level: CompressionLevel): string[] {
  const common = [
    "--object-streams=generate",
    "--stream-data=compress",
    "--decode-level=generalized",
    "--recompress-flate",
    "--compression-level=9",
  ];
  if (level === "quality") return common;
  return [
    ...common,
    "--optimize-images",
    `--jpeg-quality=${level === "smaller" ? 65 : 80}`,
    "--oi-min-width=256",
    "--oi-min-height=256",
    "--oi-min-area=65536",
  ];
}

export function summarizeCompression(
  originalBytes: number,
  candidateBytes: number,
  level: CompressionLevel,
): CompressionSummary {
  const outputBytes =
    candidateBytes < originalBytes ? candidateBytes : originalBytes;
  return {
    originalBytes,
    outputBytes,
    savedPercent:
      originalBytes > 0
        ? Math.max(0, Math.round((1 - outputBytes / originalBytes) * 1000) / 10)
        : 0,
    alreadyOptimized: candidateBytes >= originalBytes,
    level,
  };
}
