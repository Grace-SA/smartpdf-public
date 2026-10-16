/** One line that scales to fit, matching the typed signature's output layout. */
export function FontSample({
  name,
  font,
  color,
}: {
  name: string;
  font: string;
  color: string;
}) {
  const text = name.trim() || "Your name";
  const ctx = document.createElement("canvas").getContext("2d")!;
  ctx.font = `80px "${font}"`;
  const m = ctx.measureText(text),
    left = Math.max(0, m.actualBoundingBoxLeft),
    right = Math.max(m.width, m.actualBoundingBoxRight),
    top = Math.max(1, m.actualBoundingBoxAscent),
    bottom = Math.max(1, m.actualBoundingBoxDescent);
  return (
    <svg
      className="sign-font-sample"
      role="img"
      aria-label={text}
      viewBox={`0 0 ${left + right + 20} ${top + bottom + 20}`}
    >
      <text
        x={left + 10}
        y={top + 10}
        style={{
          fontFamily: font,
          fontSize: 80,
          fontWeight: 400,
          fontStyle: "normal",
          fill: color,
        }}
      >
        {text}
      </text>
    </svg>
  );
}
