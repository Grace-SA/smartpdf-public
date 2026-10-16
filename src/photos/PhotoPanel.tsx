import { FilePicker } from "../FilePicker";
import { LeaveTaskDialog } from "../LeaveTaskDialog";
import { PreviewDialog } from "../PreviewDialog";
import { TaskNotice } from "../TaskNotice";
import { CardMove } from "../CardMove";
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type RefObject,
} from "react";
import { readLocalFile } from "../platform/abort";
import { createPhotos } from "./service";
import { analyticsReason, track } from "../analytics";
import { normalizePhoto } from "./heic";
import { inspectImageColor } from "./color-profile";
import {
  defaultSettings,
  inspectImage,
  layout,
  PHOTO_LIMITS,
  photoCopy,
  safeFilename,
  type ImageInfo,
  type PhotoSettings,
} from "./model";
export type PhotoPanelHandle = { guard: (action: () => void) => void };
type Item = {
  id: number;
  file: File;
  turns: number;
  info?: ImageInfo;
  thumb?: string;
  error?: string;
  notice?: string;
};
type Props = {
  ready: boolean;
  seedFiles?: File[];
  onSeedConsumed?: () => void;
  pauseInitialInput?: boolean;
  retainedBytes: number;
  apply: (file: File, signal: AbortSignal) => Promise<boolean>;
  onClose: () => void;
  onDirty: (dirty: boolean) => void;
  onBusy: (busy: boolean) => void;
};

async function thumbnail(file: File, signal: AbortSignal): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file),
      image = new Image();
    const clean = () => {
      image.onload = null;
      image.onerror = null;
      image.src = "";
      URL.revokeObjectURL(url);
      signal.removeEventListener("abort", abort);
    };
    const abort = () => {
      clean();
      reject(new Error("Cancelled"));
    };
    signal.addEventListener("abort", abort, { once: true });
    image.onerror = () => {
      clean();
      reject(new Error(photoCopy.invalid));
    };
    image.onload = () => {
      const canvas = document.createElement("canvas");
      try {
        const factor = Math.min(
          1,
          320 / Math.max(image.naturalWidth, image.naturalHeight),
        );
        canvas.width = Math.max(1, Math.round(image.naturalWidth * factor));
        canvas.height = Math.max(1, Math.round(image.naturalHeight * factor));
        const ctx = canvas.getContext("2d");
        if (!ctx) throw new Error(photoCopy.invalid);
        ctx.fillStyle = "white";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL("image/png"));
      } catch {
        reject(new Error(photoCopy.invalid));
      } finally {
        canvas.width = canvas.height = 0;
        clean();
      }
    };
    if (signal.aborted) abort();
    else image.src = url;
  });
}
export const PhotoPanel = forwardRef<PhotoPanelHandle, Props>(
  function PhotoPanel(props, ref) {
    const [items, setItems] = useState<Item[]>([]),
      [settings, setSettings] = useState<PhotoSettings>(defaultSettings);
    const [name, setName] = useState("Photos.pdf"),
      [message, setMessage] = useState(""),
      [busy, setBusy] = useState("");
    const [dirty, setDirty] = useState(false);
    const [pending, setPending] = useState<{ action: () => void } | null>(null);
    const [failure, setFailure] = useState("");
    const [previewIndex, setPreviewIndex] = useState<number | null>(null);
    const nextId = useRef(0),
      task = useRef<AbortController | null>(null);
    const { onDirty, onBusy } = props;
    useEffect(() => {
      onDirty(dirty && items.length > 0);
    }, [dirty, items.length, onDirty]);
    useEffect(() => {
      onBusy(!!busy);
    }, [busy, onBusy]);
    useEffect(() => () => task.current?.abort(), []);
    useEffect(
      () => () => {
        onDirty(false);
        onBusy(false);
      },
      [onDirty, onBusy],
    );
    function guard(action: () => void) {
      if (task.current || (dirty && items.length > 0)) setPending({ action });
      else action();
    }
    useImperativeHandle(ref, () => ({ guard }));
    const initialize = useRef<(() => void) | null>(() => {
      if (props.seedFiles?.length)
        void add(props.seedFiles).finally(() => props.onSeedConsumed?.());
    });
    useEffect(() => {
      if (props.pauseInitialInput) return;
      const start = initialize.current;
      initialize.current = null;
      start?.();
    }, [props.pauseInitialInput]);
    function cancel() {
      task.current?.abort();
      setMessage("Cancelled. Your previous document is unchanged.");
    }
    async function add(files: File[]) {
      if (task.current || !files.length) return;
      if (
        items.length + files.length > PHOTO_LIMITS.count ||
        [...items.map((i) => i.file), ...files].reduce(
          (n, f) => n + f.size,
          0,
        ) > PHOTO_LIMITS.inputBytes
      ) {
        setMessage(photoCopy.total);
        return;
      }
      if (
        props.retainedBytes +
          [...items.map((i) => i.file), ...files].reduce(
            (n, f) => n + f.size,
            0,
          ) >
        PHOTO_LIMITS.sessionBytes
      ) {
        setMessage(photoCopy.budget);
        return;
      }
      const controller = new AbortController();
      task.current = controller;
      setMessage("");
      const added: Item[] = [];
      let timedOut = false;
      const timer = setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, PHOTO_LIMITS.timeoutMs);
      try {
        for (const [index, file] of files.entries()) {
          setBusy(`Checking image ${index + 1} of ${files.length}…`);
          const item: Item = { id: ++nextId.current, file, turns: 0 };
          try {
            if (file.size > PHOTO_LIMITS.fileBytes)
              throw new Error(photoCopy.large);
            item.file = await normalizePhoto(
              file,
              controller.signal,
              (message) => {
                item.notice = message;
              },
            );
            const retained = [...items, ...added].reduce(
              (sum, entry) => sum + entry.file.size,
              0,
            );
            if (
              retained + item.file.size > PHOTO_LIMITS.inputBytes ||
              props.retainedBytes + retained + item.file.size >
                PHOTO_LIMITS.sessionBytes
            ) {
              item.file = file;
              throw new Error(photoCopy.budget);
            }
            const imageBytes = await readLocalFile(
              item.file,
              controller.signal,
            );
            item.info = inspectImage(imageBytes);
            await inspectImageColor(imageBytes, item.info.format);
            item.thumb = await thumbnail(item.file, controller.signal);
          } catch (e) {
            if (controller.signal.aborted) break;
            item.error = e instanceof Error ? e.message : photoCopy.invalid;
          }
          added.push(item);
        }
        if (!controller.signal.aborted) {
          setItems((old) => [...old, ...added]);
          setDirty(true);
        } else {
          setMessage(
            timedOut
              ? "Checking images took too long. This batch was not added. Your earlier photos and document are unchanged. Try fewer or smaller images."
              : "Cancelled. This batch was not added. Your earlier photos and document are unchanged.",
          );
        }
      } finally {
        clearTimeout(timer);
        task.current = null;
        setBusy("");
      }
    }
    function move(id: number, to: number) {
      if (task.current) return;
      setItems((old) => {
        const from = old.findIndex((i) => i.id === id);
        if (from < 0 || to < 0 || to >= old.length) return old;
        const a = [...old],
          entry = a.splice(from, 1)[0]!;
        a.splice(to, 0, entry);
        return a;
      });
      setDirty(true);
    }
    const input = items.reduce((n, i) => n + i.file.size, 0);
    const estimate =
      items.reduce(
        (n, i) =>
          n +
          (i.info?.format === "jpeg"
            ? i.file.size + 4096
            : i.info
              ? i.info.width * i.info.height * 5 + 65536
              : 0),
        0,
      ) + 65536;
    const overBudget =
      props.retainedBytes + input + estimate > PHOTO_LIMITS.sessionBytes;
    const mib = (bytes: number) => (bytes / 1048576).toFixed(1);
    async function apply(): Promise<boolean> {
      if (
        task.current ||
        !items.length ||
        items.some((i) => i.error) ||
        !props.ready
      )
        return false;
      const started = performance.now();
      track("process_start", "photos", {
        fileCount: items.length,
        totalBytes: input,
        pages: items.length,
      });
      if (props.retainedBytes + input + estimate > PHOTO_LIMITS.sessionBytes) {
        setMessage(photoCopy.budget);
        track("process_failure", "photos", {
          durationMs: performance.now() - started,
          reason: "resource_limit",
        });
        return false;
      }
      const controller = new AbortController();
      task.current = controller;
      let timeout = false;
      const timer = setTimeout(() => {
        timeout = true;
        controller.abort();
      }, PHOTO_LIMITS.timeoutMs);
      setMessage("");
      setFailure("");
      setBusy("Creating PDF…");
      try {
        const bytes = await createPhotos(
          items,
          settings,
          controller.signal,
          setBusy,
        );
        if (
          props.retainedBytes + input + bytes.byteLength >
          PHOTO_LIMITS.sessionBytes
        )
          throw new Error(photoCopy.budget);
        if (controller.signal.aborted)
          throw new DOMException("Aborted", "AbortError");
        setBusy("Checking the new PDF and preparing its preview…");
        const file = new File(
          [bytes as Uint8Array<ArrayBuffer>],
          safeFilename(name),
          { type: "application/pdf" },
        );
        const ok = await props.apply(file, controller.signal);
        if (controller.signal.aborted)
          throw new DOMException("Aborted", "AbortError");
        if (ok) {
          setMessage("");
          track("process_success", "photos", {
            fileCount: items.length,
            totalBytes: file.size,
            pages: items.length,
            durationMs: performance.now() - started,
          });
          return true;
        }
        throw new Error(photoCopy.failed);
      } catch (e) {
        track(
          controller.signal.aborted && !timeout
            ? "process_cancel"
            : "process_failure",
          "photos",
          {
            durationMs: performance.now() - started,
            reason: analyticsReason(e, timeout),
          },
        );
        if (!controller.signal.aborted || timeout)
          setFailure(
            timeout
              ? "Processing took too long. Try fewer or smaller images."
              : e instanceof Error
                ? e.message
                : photoCopy.failed,
          );
        setMessage(
          timeout
            ? "This task took too long. Try fewer or smaller images."
            : controller.signal.aborted
              ? "Cancelled. Your previous document is unchanged."
              : e instanceof Error
                ? e.message
                : photoCopy.failed,
        );
        return false;
      } finally {
        clearTimeout(timer);
        task.current = null;
        setBusy("");
      }
    }
    return (
      <section
        className={`photo-task images-task ${items.length ? "has-inputs" : "empty-inputs"}`}
        aria-label="Turn Photos into PDF"
        onDragOver={(e) => {
          if (e.dataTransfer.types.includes("Files")) e.preventDefault();
        }}
        onDrop={(e) => {
          if (e.dataTransfer.files.length) {
            e.preventDefault();
            if (!task.current) void add(Array.from(e.dataTransfer.files));
          }
        }}
      >
        <h2>{items.length ? "Image settings" : "Select images"}</h2>
        <p>Choose images, arrange them, then create one PDF.</p>
        <FilePicker
          id="photo-files"

          multiple
          accept="image/*,.heic,.heif"
          disabled={!!busy}
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = "";
            void add(files);
          }}
        >
          {items.length ? "+ Add images" : "Choose JPEG, PNG or HEIC images"}
        </FilePicker>
        <p className="limits">
          Up to 20 images · 15 MiB / 16 MP each · 50 MiB total
        </p>
        {!items.length && (
          <details className="image-support input-support">
            <summary>File support</summary>
            <p className="limits">
              HEIC still photos are converted locally to high-quality JPEG (95%)
              without resizing. The PDF contains the visible still image, not
              photo metadata, depth or motion. Colors are converted to sRGB.
              Supported iPhone HDR photos use their standard-brightness image.
              HDR-only and multi-photo HEIC files are not supported. Converted
              images also count toward the size limits.
            </p>
            <p className="limits">
              JPEG and PNG images keep their supported color settings.
              Unsupported color settings are reported before creating the PDF.
            </p>
            <p className="limits" aria-label="Session capacity">
              Session: {mib(props.retainedBytes + input)} / 60 MiB retained,
              including this task’s selected photos.
              {items.length > 0 && !items.some((item) => item.error) && (
                <>
                  {" "}
                  Estimated with new PDF:{" "}
                  {mib(props.retainedBytes + input + estimate)} / 60 MiB. PNG
                  estimates are conservative.
                </>
              )}
            </p>
          </details>
        )}
        {items.length > 0 && overBudget && (
          <p role="alert">{photoCopy.budget}</p>
        )}
        <fieldset disabled={!!busy}>
          <legend>Page layout</legend>
          <label>
            Paper{" "}
            <select
              value={settings.paper}
              onChange={(e) => {
                setSettings({
                  ...settings,
                  paper: e.target.value as PhotoSettings["paper"],
                });
                setDirty(true);
              }}
            >
              <option>A4</option>
              <option>Letter</option>
            </select>
          </label>
          <label>
            Direction{" "}
            <select
              value={settings.direction}
              onChange={(e) => {
                setSettings({
                  ...settings,
                  direction: e.target.value as PhotoSettings["direction"],
                });
                setDirty(true);
              }}
            >
              <option value="auto">Automatic for each image</option>
              <option value="portrait">Portrait</option>
              <option value="landscape">Landscape</option>
            </select>
          </label>
          <p>10 mm margins · whole image fits · white background</p>
          <details className="output-name">
            <summary>Output filename</summary>
            <label>
              PDF name{" "}
              <input
                value={name}
                maxLength={180}
                onChange={(e) => {
                  setName(e.target.value);
                  setDirty(true);
                }}
              />
            </label>
          </details>
        </fieldset>
        <ol className="photo-list" data-reorder-list>
          {items.map((item, index) => (
            <li key={item.id} data-sort-index={index}>
              {item.thumb && (
                <button
                  className="image-preview-trigger"
                  aria-label={`Preview image ${index + 1}`}
                  disabled={!!busy}
                  onClick={(e) => {
                    e.currentTarget.focus();
                    setPreviewIndex(index);
                  }}
                >
                  <PhotoSheet item={item} settings={settings} index={index} />
                </button>
              )}
              <strong title={item.file.name}>
                <span className="file-index">{index + 1}.</span>
                <span className="file-name">{item.file.name}</span>
              </strong>
              {item.error ? (
                <p role="alert">{item.error} Remove this image to continue.</p>
              ) : (
                <p>
                  {item.info?.width} × {item.info?.height} pixels
                  {item.info &&
                  layout(item.info, item.turns, settings).ppi < 150
                    ? ` — ${photoCopy.low}`
                    : ""}
                </p>
              )}
              {item.notice && !item.error && (
                <p className="limits">{item.notice}</p>
              )}
              <div className="photo-actions card-actions">
                <CardMove
                  index={index}
                  count={items.length}
                  label={`image ${index + 1}`}
                  disabled={!!busy}
                  move={(to) => move(item.id, to)}
                />
                <button
                  className="secondary"
                  disabled={!!busy || !!item.error}
                  onClick={() => {
                    setItems((old) =>
                      old.map((i) =>
                        i.id === item.id
                          ? { ...i, turns: (i.turns + 1) % 4 }
                          : i,
                      ),
                    );
                    setDirty(true);
                  }}
                  aria-label={`Rotate image ${index + 1}`}
                >
                  ↻
                </button>
                <button
                  className="secondary"
                  disabled={!!busy}
                  onClick={() => {
                    setItems((old) => old.filter((i) => i.id !== item.id));
                    setDirty(true);
                  }}
                  aria-label={`Remove image ${index + 1}`}
                >
                  ×
                </button>
              </div>
            </li>
          ))}
        </ol>
        {busy ? (
          <div role="status">
            <p>{busy}</p>
            <button onClick={cancel}>Cancel photo task</button>
          </div>
        ) : (
          <div className="photo-actions">
            <button
              disabled={
                !props.ready ||
                !items.length ||
                items.some((i) => !!i.error) ||
                overBudget
              }
              onClick={() => void apply()}
            >
              Convert to PDF →
            </button>
            <button
              className="secondary"
              onClick={(event) => {
                event.currentTarget.focus({ preventScroll: true });
                guard(props.onClose);
              }}
            >
              Cancel task
            </button>
          </div>
        )}
        {message && <p role="alert">{message}</p>}
        {(busy || failure) && (
          <TaskNotice
            working={!!busy}
            message={busy || failure}
            close={() => {
              if (busy) task.current?.abort();
              else setFailure("");
            }}
          />
        )}
        {previewIndex !== null && items[previewIndex] && (
          <ImagePreview
            item={items[previewIndex]!}
            settings={settings}
            index={previewIndex}
            count={items.length}
            close={() => setPreviewIndex(null)}
            previous={
              previewIndex > 0 && items[previewIndex - 1]?.thumb
                ? () => setPreviewIndex(previewIndex - 1)
                : undefined
            }
            next={
              previewIndex < items.length - 1 && items[previewIndex + 1]?.thumb
                ? () => setPreviewIndex(previewIndex + 1)
                : undefined
            }
          />
        )}
        {pending && (
          <LeaveTaskDialog
            description="Your selected images and layout settings will be cleared."
            keep={() => setPending(null)}
            leave={() => {
              const action = pending.action;
              setPending(null);
              action();
            }}
          />
        )}
      </section>
    );
  },
);

function PhotoSheet({
  item,
  settings,
  index,
  large = false,
  imageRef,
}: {
  item: Item;
  settings: PhotoSettings;
  index: number;
  large?: boolean;
  imageRef?: RefObject<HTMLImageElement | null>;
}) {
  if (!item.info) return null;
  const info = item.info,
    sheet = layout(info, item.turns, settings);
  const w = info.orientation >= 5 ? info.height : info.width;
  const h = info.orientation >= 5 ? info.width : info.height;
  const scale = 72 / sheet.ppi;
  return (
    <div
      className="photo-sheet"
      style={{
        aspectRatio: `${sheet.width} / ${sheet.height}`,
        width: large
          ? `min(85vw, calc(72dvh * ${sheet.width / sheet.height}))`
          : `min(100%, ${(174 * sheet.width) / sheet.height}px)`,
        height: "auto",
      }}
      data-paper-width={sheet.width}
      data-paper-height={sheet.height}
    >
      <img
        ref={imageRef}
        draggable={false}
        src={item.thumb}
        alt={`Image ${index + 1}`}
        style={{
          width: `${(100 * w * scale) / sheet.width}%`,
          height: `${(100 * h * scale) / sheet.height}%`,
          transform: `translate(-50%, -50%) rotate(${item.turns * 90}deg)`,
        }}
      />
    </div>
  );
}

function ImagePreview({
  item,
  settings,
  index,
  count,
  close,
  previous,
  next,
}: {
  item: Item;
  settings: PhotoSettings;
  index: number;
  count: number;
  close: () => void;
  previous?: () => void;
  next?: () => void;
}) {
  const imageRef = useRef<HTMLImageElement>(null);
  useEffect(() => {
    const url = URL.createObjectURL(item.file);
    const image = imageRef.current;
    if (image) image.src = url;
    return () => {
      if (image) image.removeAttribute("src");
      URL.revokeObjectURL(url);
    };
  }, [item.file]);
  return (
    <PreviewDialog
      title={`${item.file.name} · ${index + 1} / ${count}`}
      label="Image page preview"
      close={close}
      previous={previous}
      next={next}
      toolbar={
        <span>Page layout preview · {settings.paper} · 10 mm margins</span>
      }
    >
      <PhotoSheet
        item={item}
        imageRef={imageRef}
        settings={settings}
        index={index}
        large
      />
    </PreviewDialog>
  );
}
