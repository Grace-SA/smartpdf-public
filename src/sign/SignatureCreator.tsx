import { FontSample } from "./FontSample";
import { useEffect, useRef, useState, type PointerEvent } from "react";
import {
  canvasAsset,
  importedAsset,
  prepareSignFont,
  styles,
  supportsName,
  typedAsset,
} from "./assets";
import { SIGN_LIMITS, type SignatureAsset } from "./model";
type Point = { x: number; y: number };
type Stroke = Point[];
export function SignatureCreator({
  open,
  close,
  onUse,
  dirty,
}: {
  open: boolean;
  close: () => void;
  onUse: (asset: SignatureAsset) => boolean;
  dirty: () => void;
}) {
  const [mode, setMode] = useState<"Draw" | "Type" | "Image">("Draw"),
    [name, setName] = useState(""),
    [font, setFont] = useState<string>("Kalam"),
    [color, setColor] = useState("#111111"),
    [strokes, setStrokes] = useState<Stroke[]>([]),
    [redo, setRedo] = useState<Stroke[][]>([]),
    [undo, setUndo] = useState<Stroke[][]>([]),
    [image, setImage] = useState<SignatureAsset | null>(null),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  const [loadedFonts, setLoadedFonts] = useState<string[]>([]);
  const [fontFailure, setFontFailure] = useState<string | null>(null);
  const [fontRetry, setFontRetry] = useState(0);
  const canvas = useRef<HTMLCanvasElement>(null),
    dialog = useRef<HTMLDialogElement>(null),
    drawing = useRef<Stroke | null>(null),
    urls = useRef(new Set<string>()),
    mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    const saved = urls.current;
    return () => {
      mounted.current = false;
      for (const u of saved) URL.revokeObjectURL(u);
    };
  }, []);
  useEffect(() => {
    if (!open) return;
    const d = dialog.current!,
      previous = document.activeElement;
    d.showModal();
    return () => {
      d.close();
      if (previous instanceof HTMLElement && previous.isConnected)
        previous.focus();
    };
  }, [open]);
  useEffect(() => {
    if (!open || mode !== "Type") return;
    let current = true;
    void prepareSignFont(font)
      .then(() => {
        if (current) {
          setLoadedFonts((fonts) => [...new Set([...fonts, font])]);
          setFontFailure(null);
        }
      })
      .catch(() => {
        if (current) setFontFailure(font);
      });
    return () => {
      current = false;
    };
  }, [open, mode, font, fontRetry]);
  function paint(extra: Stroke | null = null) {
    const c = canvas.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    ctx.clearRect(0, 0, c.width, c.height);
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 3.5;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (const stroke of [...strokes, ...(extra ? [extra] : [])]) {
      if (!stroke.length) continue;
      ctx.beginPath();
      ctx.moveTo(stroke[0]!.x, stroke[0]!.y);
      for (const p of stroke) ctx.lineTo(p.x, p.y);
      ctx.stroke();
      if (stroke.length === 1) {
        ctx.beginPath();
        ctx.arc(stroke[0]!.x, stroke[0]!.y, 2, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }
  useEffect(() => {
    paint();
  });
  function change(next: Stroke[]) {
    setUndo((u) => [...u, strokes].slice(-50));
    setRedo([]);
    setStrokes(next);
    dirty();
  }
  function point(e: PointerEvent<HTMLCanvasElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1024, ((e.clientX - r.left) / r.width) * 1024)),
      y: Math.max(0, Math.min(400, ((e.clientY - r.top) / r.height) * 400)),
    };
  }
  async function accept() {
    setBusy(true);
    setMessage("");
    try {
      let a: SignatureAsset;
      if (mode === "Type") a = await typedAsset(name, font, color);
      else if (mode === "Image") {
        if (!image) return;
        a = image;
      } else {
        const all = strokes.flat();
        if (!all.length) return;
        const l = Math.max(0, Math.floor(Math.min(...all.map((p) => p.x)) - 8)),
          t = Math.max(0, Math.floor(Math.min(...all.map((p) => p.y)) - 8)),
          r = Math.min(1024, Math.ceil(Math.max(...all.map((p) => p.x)) + 8)),
          b = Math.min(400, Math.ceil(Math.max(...all.map((p) => p.y)) + 8));
        const c = document.createElement("canvas");
        c.width = r - l;
        c.height = b - t;
        c.getContext("2d")!.drawImage(
          canvas.current!,
          l,
          t,
          r - l,
          b - t,
          0,
          0,
          r - l,
          b - t,
        );
        try {
          a = await canvasAsset(c);
        } finally {
          c.width = c.height = 0;
        }
      }
      if (!mounted.current) {
        URL.revokeObjectURL(a.url);
        return;
      }
      urls.current.add(a.url);
      if (onUse(a)) urls.current.delete(a.url);
      else
        setMessage(
          "Signature limit reached. Remove an existing signature before adding another.",
        );
    } catch (e) {
      if (mounted.current)
        setMessage(
          e instanceof Error ? e.message : "Could not create signature.",
        );
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  const valid =
    mode === "Draw"
      ? strokes.length > 0
      : mode === "Image"
        ? !!image
        : supportsName(font, name) && name.length <= SIGN_LIMITS.nameLength;
  if (!open) return null;
  return (
    <dialog
      className="sign-creator"
      ref={dialog}
      aria-label="Create signature"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) close();
      }}
    >
      <header>
        <h2>Create signature</h2>
        <button
          className="secondary"
          disabled={busy}
          onClick={close}
          aria-label="Close signature creator"
        >
          ×
        </button>
      </header>
      <fieldset disabled={busy}>
        <div className="sign-tabs" role="tablist" aria-label="Signature method">
          {(["Draw", "Type", "Image"] as const).map((m) => (
            <button
              key={m}
              role="tab"
              aria-selected={mode === m}
              className={mode === m ? "" : "secondary"}
              onClick={() => {
                setMode(m);
                setMessage("");
              }}
            >
              {m}
            </button>
          ))}
        </div>
        {mode !== "Image" && (
          <div className="sign-colors" aria-label="Ink color">
            {[
              ["Black", "#111111"],
              ["Blue", "#245baf"],
            ].map(([label, value]) => (
              <button
                key={value}
                className="secondary"
                aria-pressed={color === value}
                onClick={() => {
                  setColor(value!);
                  dirty();
                }}
              >
                {label}
              </button>
            ))}
          </div>
        )}
        {mode === "Draw" && (
          <>
            <canvas
              ref={canvas}
              width={1024}
              height={400}
              aria-label="Draw your signature"
              className="signature-draw"
              onPointerDown={(e) => {
                if (!e.isPrimary) return;
                e.currentTarget.setPointerCapture(e.pointerId);
                drawing.current = [point(e)];
                paint(drawing.current);
              }}
              onPointerMove={(e) => {
                if (!drawing.current) return;
                if (
                  strokes.flat().length + drawing.current.length >=
                  SIGN_LIMITS.points
                ) {
                  setMessage(
                    "Drawing limit reached. Undo strokes or clear the canvas.",
                  );
                  return;
                }
                drawing.current.push(point(e));
                paint(drawing.current);
              }}
              onPointerUp={() => {
                if (drawing.current) {
                  change([...strokes, drawing.current]);
                  drawing.current = null;
                }
              }}
              onPointerCancel={() => {
                drawing.current = null;
                paint();
              }}
            />
            <p className="sign-hint">Draw with your mouse, pen or finger.</p>
            <div className="sign-row">
              <button
                className="secondary"
                disabled={!undo.length}
                onClick={() => {
                  setRedo((r) => [...r, strokes]);
                  setStrokes(undo.at(-1)!);
                  setUndo((u) => u.slice(0, -1));
                }}
              >
                Undo stroke
              </button>
              <button
                className="secondary"
                disabled={!redo.length}
                onClick={() => {
                  setUndo((u) => [...u, strokes]);
                  setStrokes(redo.at(-1)!);
                  setRedo((r) => r.slice(0, -1));
                }}
              >
                Redo stroke
              </button>
              <button
                className="secondary"
                disabled={!strokes.length}
                onClick={() => change([])}
              >
                Clear
              </button>
            </div>
          </>
        )}
        {mode === "Type" && (
          <div className="sign-type">
            <label>
              Your name
              <input
                autoComplete="off"
                spellCheck={false}
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  if (
                    !supportsName(font, e.target.value) &&
                    supportsName("MaShanZheng", e.target.value)
                  )
                    setFont("MaShanZheng");
                  dirty();
                }}
              />
            </label>
            {name.length > SIGN_LIMITS.nameLength && (
              <p role="alert">
                Use up to 120 characters. Your name has not been shortened.
              </p>
            )}
            <p className="sign-hint">
              Choose a style. All processing stays on this device.
            </p>
            <div className="sign-fonts">
              {styles.map((s) => (
                <button
                  key={s.id}
                  className="secondary"
                  disabled={!!name.trim() && !supportsName(s.id, name)}
                  aria-pressed={font === s.id}
                  onClick={() => {
                    setFont(s.id);
                    dirty();
                  }}
                >
                  {loadedFonts.includes(s.id) ? (
                    <FontSample
                      font={s.id}
                      name={
                        name.length > SIGN_LIMITS.nameLength
                          ? "Shorten name to preview"
                          : name
                      }
                      color={color}
                    />
                  ) : (
                    <span className="sign-font-placeholder">
                      {font === s.id
                        ? "Preparing preview…"
                        : "Select to preview"}
                    </span>
                  )}
                  <small>
                    {s.label}
                    {name.length > SIGN_LIMITS.nameLength
                      ? " · Shorten name"
                      : name.trim() && !supportsName(s.id, name)
                        ? " · Some characters unavailable"
                        : ""}
                  </small>
                </button>
              ))}
            </div>
            {!loadedFonts.includes(font) && (
              <p role="status">
                {fontFailure === font
                  ? "This signature style could not load. Your document and name are kept."
                  : "Loading your signature style…"}
                {fontFailure === font && (
                  <button
                    className="secondary"
                    onClick={() => {
                      setFontFailure(null);
                      setFontRetry((value) => value + 1);
                    }}
                  >
                    Retry style
                  </button>
                )}
              </p>
            )}
            {name.length <= SIGN_LIMITS.nameLength &&
              name.trim() &&
              !supportsName(font, name) && (
                <p role="status">
                  Choose an available style that supports your name.
                </p>
              )}
          </div>
        )}
        {mode === "Image" && (
          <div className="sign-import">
            {image && <img src={image.url} alt="Signature image preview" />}
            <label className="sign-file">
              {image ? "Change image" : "Choose image"}
              <input
                type="file"
                accept=".png,.jpg,.jpeg,image/png,image/jpeg"
                aria-label="Choose signature image"
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  e.target.value = "";
                  if (!f) return;
                  setBusy(true);
                  setMessage("");
                  try {
                    const a = await importedAsset(f);
                    if (!mounted.current) {
                      URL.revokeObjectURL(a.url);
                      return;
                    }
                    urls.current.add(a.url);
                    if (mounted.current) {
                      if (image && urls.current.has(image.url)) {
                        URL.revokeObjectURL(image.url);
                        urls.current.delete(image.url);
                      }
                      setImage(a);
                      dirty();
                    }
                  } catch (error) {
                    setMessage(
                      error instanceof Error
                        ? error.message
                        : "Could not read image.",
                    );
                  } finally {
                    if (mounted.current) setBusy(false);
                  }
                }}
              />
            </label>
            <p>PNG or JPEG · up to 5 MiB / 4 MP</p>
            <p>
              White backgrounds may cover document text. Use a transparent PNG
              or draw your signature.
            </p>
          </div>
        )}
      </fieldset>
      {message && <p role="alert">{message}</p>}
      <p className="sign-hint">Your signature stays in this task only.</p>
      <footer>
        <button className="secondary" disabled={busy} onClick={close}>
          Cancel
        </button>
        <button
          disabled={
            busy || !valid || (mode === "Type" && !loadedFonts.includes(font))
          }
          onClick={() => void accept()}
        >
          {busy ? "Preparing signature…" : "Use signature"}
        </button>
      </footer>
    </dialog>
  );
}
