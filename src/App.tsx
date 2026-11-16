import { Suspense } from "react";
import { loadModule } from "./platform/module-loading";
import type { SignHandle } from "./sign/SignPanel";
import type { CompressHandle } from "./compress/CompressPanel";
import type { CompressionSummary } from "./compress/model";
import { FilePicker } from "./FilePicker";
import { Completion, type DownloadNotice } from "./Completion";
import { ToolIcon } from "./ToolIcon";
import { ToolNavigation } from "./ToolNavigation";
import { TaskNotice } from "./TaskNotice";
import { FilePreview } from "./FilePreview";
import type { CombineHandle, CombineProps } from "./combine/CombinePanel";
import type { ForwardRefExoticComponent, RefAttributes } from "react";
import { firstPageThumbnail } from "./combine/thumbnail";
import { zipFiles } from "./downloads/zip";
import { ConfirmDialog } from "./ConfirmDialog";
import { LeaveTaskDialog } from "./LeaveTaskDialog";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import { LIMITS, ProbeFailure } from "./core/contracts";
import type { Engine, Preview } from "./platform/engine";
import { copy, reasons } from "./copy";
import type { PhotoPanelHandle } from "./photos/PhotoPanel";
import {
  emptySession,
  currentDocument,
  commitDocument,
  commitWorkspace,
  sessionFiles,
  sessionBytes,
  type Session,
  type DocumentRevision,
} from "./session";
import type { SplitHandle } from "./split/SplitPanel";
import { safeFilename } from "./photos/model";
import type { OrganizeHandle } from "./organize/OrganizePanel";
import { SeoContent, applySeo } from "./SeoContent";
import {
  toolFromPath,
  toolPaths,
  publicTools,
  toolCatalog,
  type PublicTool,
} from "./published-routes";
import { track } from "./analytics";
import { TrustHighlights } from "./TrustHighlights";
import type { UnlockHandle } from "./unlock/UnlockPanel";
import type { ProtectHandle } from "./protect/ProtectPanel";

function ToolLoading() {
  return (
    <p role="status" className="tool-loading">
      Opening this tool…
    </p>
  );
}

function SourcePicker({
  kind,
  select,
}: {
  kind: "photos" | "combine" | "unlock" | "protect";
  select: (files: File[]) => void;
}) {
  const photos = kind === "photos";
  const unlock = kind === "unlock";
  const protect = kind === "protect";
  const single = unlock || protect;
  return (
    <section
      className={`photo-task ${photos ? "" : "combine-task"} empty-inputs`}
      aria-label={
        photos
          ? "Images to PDF"
          : unlock
            ? "Unlock PDF"
            : protect
              ? "Protect PDF"
              : "Combine PDFs"
      }
      onDragOver={(event) => {
        if (event.dataTransfer.types.includes("Files")) event.preventDefault();
      }}
      onDrop={(event) => {
        event.preventDefault();
        if (event.dataTransfer.files.length)
          select(Array.from(event.dataTransfer.files));
      }}
    >
      <h2>
        {photos
          ? "Select images"
          : protect
            ? "Select a PDF to protect"
            : unlock
              ? "Select a protected PDF"
              : "Select PDFs to merge"}
      </h2>
      <p>
        {protect
          ? "Add an opening password and download a protected copy."
          : unlock
            ? "Remove password protection and download an unlocked copy."
            : photos
              ? "Choose images, arrange them, then create one PDF."
              : "Choose 2–10 PDFs, then arrange them in order."}
      </p>
      <FilePicker
        id={photos ? "photo-files" : single ? "pdf-file" : "combine-files"}
        multiple={!single}
        accept={photos ? "image/*,.heic,.heif" : ".pdf,application/pdf"}
        disabled={false}
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          event.target.value = "";
          if (files.length) select(files);
        }}
      >
        {single
          ? "Select PDF file"
          : photos
            ? "Choose JPEG, PNG or HEIC images"
            : "Select PDF files or drop them here"}
      </FilePicker>
      <p className="limits">
        {single
          ? "One PDF · up to 30 MiB · 200 pages · no upload"
          : photos
            ? "Up to 20 images · 15 MiB / 16 MP each · 50 MiB total"
            : "30 MiB input · 200 pages total · Originals unchanged"}
      </p>
      <details className="input-support">
        <summary>File support</summary>
        <p>
          {protect
            ? "Ordinary, unencrypted PDFs. Digital signatures, Content Credentials, conformance declarations and unsupported structures are refused. Your original stays unchanged."
            : unlock
              ? "Use a PDF you own or have permission to unlock. You may need its current password. Digital signatures and unsupported protection methods are refused without changing your original."
              : photos
                ? "JPEG, PNG and supported HEIC still photos. Images are converted locally; your originals stay unchanged."
                : "Ordinary, unencrypted PDFs. Supported links, bookmarks and page structure are preserved; unsupported files are explained before merging."}
        </p>
      </details>
    </section>
  );
}

type Tool = "read" | PublicTool;
const toolTitles = {
  read: "Read PDF",
  ...Object.fromEntries(publicTools.map((id) => [id, toolCatalog[id].title])),
} as Record<Tool, string>;
const toolTaglines: Record<Tool, string> = {
  ppt: "Convert visible PPTX slides using cloud processing.",
  pdfword: "Turn simple text PDFs into editable Word documents.",
  excel: "Choose worksheets and convert an XLSX using cloud processing.",
  word: "Convert a DOCX using cloud processing.",
  protect: "Add an opening password. Keep your PDF on your device.",
  unlock: "Remove a known password. Keep your PDF on your device.",
  numbers: "Add page numbers without uploading your PDF.",
  watermark: "Add text or image watermarks without uploading your PDF.",
  raster: "Turn PDF pages into images without uploading your file.",
  rotate: "Turn pages the right way without uploading your PDF.",
  compress: "Reduce PDF size without uploading it.",
  sign: "Add a visible signature in your browser.",
  read: "Preview a PDF on this device.",
  combine: "Combine PDFs in the order you choose.",
  split: "Separate pages into new PDF files.",
  organize: "Reorder, rotate or remove pages.",
  photos: "Turn up to 20 images into one PDF.",
};
type ResourceState = "loading" | "ready" | "error";
export function App() {
  const initialTool = toolFromPath(window.location.pathname);
  const [screen, setScreen] = useState<"home" | "task" | "preview" | "result">(
    initialTool ? "task" : "home",
  );
  const [taskKey, setTaskKey] = useState(0);
  const [tool, setTool] = useState<Tool>(initialTool ?? "read");
  const toolRef = useRef<Tool>(initialTool ?? "read");
  const [deliveryIds, setDeliveryIds] = useState<string[]>([]);
  const [ProtectPanel, setProtectPanel] = useState<
    (typeof import("./protect/ProtectPanel"))["ProtectPanel"] | null
  >(null);
  const protectPanel = useRef<ProtectHandle>(null);
  const [protectResult, setProtectResult] = useState<{
    file: File;
    pages: number;
  } | null>(null);
  const [UnlockPanel, setUnlockPanel] = useState<
    (typeof import("./unlock/UnlockPanel"))["UnlockPanel"] | null
  >(null);
  const unlockPanel = useRef<UnlockHandle>(null);
  const [unlockResult, setUnlockResult] = useState<{
    file: File;
    pages: number;
  } | null>(null);
  const [previewFile, setPreviewFile] = useState<{
    file: File;
    engine: Engine;
  } | null>(null);
  const completed = useRef(false);
  const [packing, setPacking] = useState(false);
  const [preparingCopy, setPreparingCopy] = useState(false);
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [screen, tool]);
  // The homepage needs no PDF runtime. Initialize shared and tool-specific
  // resources only after the user opens a tool (or visits its direct URL).
  const [resource, setResource] = useState<ResourceState>(
    initialTool ? "loading" : "ready",
  );
  const [compressResource, setCompressResource] = useState<ResourceState>(
    initialTool === "compress" ? "loading" : "ready",
  );
  const [retry, setRetry] = useState(0);
  const [current, setCurrent] = useState<Preview | null>(null);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [downloadNotice, setDownloadNotice] = useState<DownloadNotice>(null);
  const engine = useRef<Engine | null>(null);
  const enginePreparation = useRef<Promise<void>>(Promise.resolve());
  const resourceController = useRef<AbortController | null>(null);
  const processingReady = useRef(!initialTool);
  const queuedInput = useRef<File | null>(null);
  const [waitingForResources, setWaitingForResources] = useState(false);
  const active = useRef<Preview | null>(null);
  const job = useRef<AbortController | null>(null);
  const host = useRef<HTMLDivElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const serial = useRef(0);
  const [Combine, setCombine] = useState<ForwardRefExoticComponent<
    CombineProps & RefAttributes<CombineHandle>
  > | null>(null);
  const [Photo, setPhoto] = useState<
    (typeof import("./photos/PhotoPanel"))["PhotoPanel"] | null
  >(null);
  const [SignPanel, setSignPanel] = useState<
    (typeof import("./sign/SignPanel"))["SignPanel"] | null
  >(null);
  const [SplitPanel, setSplitPanel] = useState<
    (typeof import("./split/SplitPanel"))["SplitPanel"] | null
  >(null);
  const [OrganizePanel, setOrganizePanel] = useState<
    (typeof import("./organize/OrganizePanel"))["OrganizePanel"] | null
  >(null);
  const [RotatePanel, setRotatePanel] = useState<
    (typeof import("./rotate/RotatePanel"))["RotatePanel"] | null
  >(null);
  const [RasterPanel, setRasterPanel] = useState<
    (typeof import("./raster/RasterPanel"))["RasterPanel"] | null
  >(null);
  const [rasterResult, setRasterResult] = useState<
    import("./raster/model").RasterResult | null
  >(null);
  const rasterPanel = useRef<OrganizeHandle>(null);
  const rastering = tool === "raster" && screen === "task" && !!current;
  const [WatermarkPanel, setWatermarkPanel] = useState<
    (typeof import("./watermark/WatermarkPanel"))["WatermarkPanel"] | null
  >(null);
  const watermarkPanel = useRef<OrganizeHandle>(null);
  const watermarking = tool === "watermark" && screen === "task" && !!current;
  const [NumberPanel, setNumberPanel] = useState<
    (typeof import("./numbers/NumberPanel"))["NumberPanel"] | null
  >(null);
  const numberPanel = useRef<OrganizeHandle>(null);
  const numbering = tool === "numbers" && screen === "task" && !!current;
  const [CompressPanel, setCompressPanel] = useState<
    (typeof import("./compress/CompressPanel"))["CompressPanel"] | null
  >(null);
  const [combining, setCombining] = useState(initialTool === "combine");
  const [organizing, setOrganizing] = useState(false);
  const [splitting, setSplitting] = useState(false);
  const [compressing, setCompressing] = useState(false);
  const [compressionSummary, setCompressionSummary] =
    useState<CompressionSummary | null>(null);
  const compressPanel = useRef<CompressHandle>(null);
  const splitPanel = useRef<SplitHandle>(null);
  const signPanel = useRef<SignHandle>(null);
  const signing = tool === "sign" && screen === "task" && !!current;
  const documentIdentity = useRef(0);
  const organizePanel = useRef<OrganizeHandle>(null);
  const pageIdentity = useRef(0);
  const [combineSeed, setCombineSeed] = useState<File | undefined>();
  const [sourceFiles, setSourceFiles] = useState<File[]>([]);
  const [sourceStage, setSourceStage] = useState<
    "empty" | "pending" | "editing"
  >("empty");
  const sourceSeed = useRef<File[] | null>(null);
  const [pendingSourceAction, setPendingSourceAction] = useState<{
    action: () => void;
    trigger: HTMLElement | null;
  } | null>(null);
  const restoreSourceFocus = useRef<HTMLElement | null>(null);
  function selectSources(files: File[]) {
    sourceSeed.current = files;
    setSourceFiles(files);
    setSourceStage("pending");
  }
  function sourceConsumed(files: File[]) {
    if (sourceSeed.current !== files) return;
    sourceSeed.current = null;
    setSourceFiles([]);
    setSourceStage("editing");
  }
  const combinePanel = useRef<CombineHandle>(null);
  const [photos, setPhotos] = useState(initialTool === "photos"),
    [photoDirty, setPhotoDirty] = useState(false),
    [photoBusy, setPhotoBusy] = useState(false);
  useEffect(() => {
    if (photoBusy || sourceStage !== "editing") return;
    const trigger = restoreSourceFocus.current;
    if (!trigger) return;
    const frame = requestAnimationFrame(() => {
      restoreSourceFocus.current = null;
      if (trigger.isConnected && document.activeElement === document.body)
        trigger.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [photoBusy, sourceStage]);
  const [taskState, setTaskState] = useState<Session>(emptySession);
  const taskStateRef = useRef(taskState),
    photoPanel = useRef<PhotoPanelHandle>(null),
    downloadUrls = useRef(new Set<string>());
  const [pendingCredential, setPendingCredential] = useState<File | null>(null);
  const [pendingOrdinary, setPendingOrdinary] = useState<File | null>(null);
  const currentRevision = currentDocument(taskState);
  const hasGenerated = taskState.present.results.length > 0;
  const publicTool = tool === "read" ? null : tool;
  const pristineTask =
    screen === "task" &&
    !currentRevision &&
    !photoDirty &&
    !hasGenerated &&
    sourceStage === "empty" &&
    !waitingForResources;
  const trackedToolView = useRef<PublicTool | null>(null);
  useEffect(() => {
    applySeo(screen === "home" ? null : publicTool);
    if (screen === "home") trackedToolView.current = null;
    else if (publicTool && trackedToolView.current !== publicTool) {
      track("tool_view", publicTool);
      trackedToolView.current = publicTool;
    }
  }, [screen, publicTool]);
  function openPreview(file: File) {
    if (engine.current) setPreviewFile({ file, engine: engine.current });
  }
  function updatePath(path: string) {
    if (window.location.pathname === path) return true;
    try {
      window.history.pushState({}, "", path);
      return true;
    } catch (error) {
      // WebKit limits rapid history updates. Complete a real navigation instead
      // of leaving the URL and React's tool state out of sync.
      if (!(error instanceof DOMException) || error.name !== "SecurityError")
        throw error;
      resourceController.current?.abort();
      window.location.assign(path);
      return false;
    }
  }
  function chooseTool(next: Tool, reuse = false) {
    if (job.current || photoBusy || packing) return;
    guard(() => {
      if (
        next === "word" ||
        next === "ppt" ||
        next === "excel" ||
        next === "pdfword"
      ) {
        // React cleanup does not run when replacing this document. Stop pending
        // blob workers while their document and error handlers still exist.
        resourceController.current?.abort();
        window.location.assign(toolPaths[next]);
        return;
      }
      if (next !== "read" && !updatePath(toolPaths[next])) return;
      if (!reuse) resetTask();
      completed.current = false;
      setTaskKey((key) => key + 1);
      if (next !== toolRef.current || resource === "error") {
        processingReady.current = false;
        setResource("loading");
      }
      if (next === toolRef.current && resource === "error")
        setRetry((value) => value + 1);
      if (
        next === "compress" &&
        (next !== toolRef.current || compressResource !== "ready")
      )
        setCompressResource("loading");
      toolRef.current = next;
      setTool(next);
      setScreen("task");
      setMessage("");
      setPhotos(false);
      setCombining(false);
      setOrganizing(false);
      setSplitting(false);
      setCompressing(false);
      if (next === "photos") setPhotos(true);
      else if (next === "combine") {
        setCombineSeed(
          reuse ? currentDocument(taskStateRef.current)?.file : undefined,
        );
        setCombining(true);
      } else if (reuse && currentDocument(taskStateRef.current)) {
        if (next === "organize" || next === "rotate") void startOrganize();
        else if (next === "split") setSplitting(true);
        else setScreen("preview");
      }
    });
  }
  function showHome() {
    if (job.current || photoBusy || packing) return;
    guard(abandonToHome);
  }
  function abandonToHome() {
    if (!updatePath("/")) return;
    setPhotos(false);
    setCombining(false);
    setOrganizing(false);
    setSplitting(false);
    setCompressing(false);
    resetTask();
    setScreen("home");
  }
  const navigateHistory = useEffectEvent(() => {
    // Empty and completed tasks can change routes without tearing down the app.
    // Keep native unload protection for an active task with local inputs/drafts.
    if (
      !completed.current &&
      (currentRevision ||
        photoDirty ||
        sourceStage !== "empty" ||
        waitingForResources ||
        busy ||
        photoBusy ||
        packing)
    ) {
      window.location.reload();
      return;
    }
    const next = toolFromPath(window.location.pathname);
    if (next) chooseTool(next);
    else abandonToHome();
  });
  useEffect(() => {
    const navigate = () => navigateHistory();
    window.addEventListener("popstate", navigate);
    return () => window.removeEventListener("popstate", navigate);
  }, []);
  function importPdf(file: File) {
    if (job.current || photoBusy || packing) return;
    guard(() => {
      setSplitting(false);
      setCombining(false);
      setOrganizing(false);
      setCompressing(false);
      setCombineSeed(undefined);
      if (!processingReady.current) {
        queuedInput.current = file;
        setWaitingForResources(true);
        setMessage("");
      } else void openForTask(file);
    }, true);
  }
  async function openForTask(file: File) {
    if (!(await run(file))) return;
    if (toolRef.current === "organize" || toolRef.current === "rotate") {
      setScreen("task");
      await startOrganize();
    } else if (
      toolRef.current === "sign" ||
      toolRef.current === "raster" ||
      toolRef.current === "numbers" ||
      toolRef.current === "watermark"
    ) {
      setScreen("task");
    } else if (toolRef.current === "compress") {
      setScreen("task");
      setCompressing(true);
    } else if (toolRef.current === "split") {
      setScreen("task");
      setSplitting(true);
    } else {
      setScreen("preview");
      openPreview(file);
    }
  }
  const openQueuedInput = useEffectEvent((file: File) => {
    void openForTask(file);
  });
  async function saveAll() {
    if (job.current || photoBusy || packing) return;
    const files = deliveryIds
      .map((id) => taskStateRef.current.present.documents[id]?.file)
      .filter((f): f is File => !!f);
    if (!files.length) return;
    setPacking(true);
    setDownloadNotice({ kind: "status", text: "Preparing your download…" });
    try {
      const blob = await zipFiles(files);
      const url = URL.createObjectURL(blob);
      downloadUrls.current.add(url);
      const a = document.createElement("a");
      a.href = url;
      a.download = "Smart-PDF-results.zip";
      document.body.append(a);
      a.click();
      a.remove();
      window.setTimeout(() => {
        URL.revokeObjectURL(url);
        downloadUrls.current.delete(url);
      }, 60000);
      setDownloadNotice({
        kind: "status",
        text: "Download started. Check your browser’s downloads.",
      });
      if (publicTool)
        track("download", publicTool, {
          fileCount: files.length,
          totalBytes: files.reduce((sum, file) => sum + file.size, 0),
        });
    } catch {
      setDownloadNotice({
        kind: "error",
        text: "Your results are still here. Download could not start. Please try again.",
      });
      if (publicTool) track("download_failure", publicTool);
    } finally {
      setPacking(false);
    }
  }
  function updateTaskState(value: Session) {
    taskStateRef.current = value;
    setTaskState(value);
    setDeliveryIds((ids) => ids.filter((id) => !!value.present.documents[id]));
  }
  function guard(action: () => void, replaceQueuedInput = false) {
    if (completed.current) {
      action();
      return;
    }
    if (
      sourceStage === "pending" ||
      (queuedInput.current && !replaceQueuedInput)
    ) {
      setPendingSourceAction({
        action,
        trigger:
          document.activeElement instanceof HTMLElement
            ? document.activeElement
            : null,
      });
      return;
    }
    if (tool === "protect" && protectPanel.current)
      protectPanel.current.guard(action);
    else if (tool === "unlock" && unlockPanel.current)
      unlockPanel.current.guard(action);
    else if (numbering && numberPanel.current)
      numberPanel.current.guard(action);
    else if (watermarking && watermarkPanel.current)
      watermarkPanel.current.guard(action);
    else if (rastering && rasterPanel.current)
      rasterPanel.current.guard(action);
    else if (signing && signPanel.current) signPanel.current.guard(action);
    else if (splitting && splitPanel.current) splitPanel.current.guard(action);
    else if (organizing && organizePanel.current)
      organizePanel.current.guard(action);
    else if (combining && combinePanel.current)
      combinePanel.current.guard(action);
    else if (photos && photoPanel.current) photoPanel.current.guard(action);
    else if (compressing && compressPanel.current)
      compressPanel.current.guard(action);
    else action();
  }
  useEffect(() => {
    const before = (event: BeforeUnloadEvent) => {
      if (
        photoDirty ||
        hasGenerated ||
        sourceStage === "pending" ||
        waitingForResources
      ) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", before);
    return () => window.removeEventListener("beforeunload", before);
  }, [photoDirty, hasGenerated, sourceStage, waitingForResources]);
  useEffect(() => {
    const urls = downloadUrls.current;
    return () => {
      for (const url of urls) URL.revokeObjectURL(url);
      urls.clear();
    };
  }, []);

  useEffect(() => {
    if (tool === "read") return;
    const controller = new AbortController();
    resourceController.current = controller;
    let mounted = true;
    const leavingDocument = () => {
      mounted = false;
      controller.abort();
    };
    window.addEventListener("pagehide", leavingDocument);
    let disposeCompression = () => {};
    let timeout = 0;
    const timedOut = new Promise<never>((_, reject) => {
      timeout = window.setTimeout(
        () => {
          controller.abort();
          reject(new Error("Processing resources could not be prepared."));
          // Cold CJK font delivery can outlast the ordinary engine budget.
          // File selection stays available; selected inputs remain guarded.
        },
        tool === "watermark" ? 180_000 : 30_000,
      );
    });
    let combineModule: typeof import("./combine/CombinePanel") | undefined;
    let toolPreparation: Promise<unknown> | null = null;
    if (tool === "combine")
      toolPreparation = loadModule(
        "merge",
        () => import("./combine/CombinePanel"),
        retry,
        controller.signal,
      ).then((module) => {
        combineModule = module;
        if (mounted) setCombine(() => module.CombinePanel);
        return module.prepareCombine(controller.signal);
      });
    else if (tool === "photos")
      toolPreparation = loadModule(
        "photoService",
        () => import("./photos/service"),
        retry,
        controller.signal,
      ).then((module) => module.preparePhotos(controller.signal));
    else if (tool === "compress")
      toolPreparation = loadModule(
        "compressService",
        () => import("./compress/service"),
        retry,
        controller.signal,
      ).then((module) => {
        disposeCompression = module.disposeCompress;
        return module.prepareCompress(controller.signal);
      });
    // A ready tool includes its operation UI and inline workers, so selecting a
    // file after going offline does not need to download another code chunk.
    const panelPreparation =
      tool === "protect"
        ? loadModule(
            "protect",
            () => import("./protect/ProtectPanel"),
            retry,
            controller.signal,
          ).then(async (module) => {
            if (mounted) setProtectPanel(() => module.ProtectPanel);
            await module.prepareProtect(controller.signal);
          })
        : tool === "unlock"
          ? loadModule(
              "unlock",
              () => import("./unlock/UnlockPanel"),
              retry,
              controller.signal,
            ).then(async (module) => {
              if (mounted) setUnlockPanel(() => module.UnlockPanel);
              await module.prepareUnlock(controller.signal);
            })
          : tool === "numbers"
            ? loadModule(
                "numbers",
                () => import("./numbers/NumberPanel"),
                retry,
                controller.signal,
              ).then(async (module) => {
                if (mounted) setNumberPanel(() => module.NumberPanel);
                await module.prepareNumberFont(controller.signal);
              })
            : tool === "watermark"
              ? loadModule(
                  "watermark",
                  () => import("./watermark/WatermarkPanel"),
                  retry,
                  controller.signal,
                ).then(async (module) => {
                  if (mounted) setWatermarkPanel(() => module.WatermarkPanel);
                  await module.prepareWatermark(controller.signal);
                })
              : tool === "raster"
                ? loadModule(
                    "raster",
                    () => import("./raster/RasterPanel"),
                    retry,
                    controller.signal,
                  ).then((module) => {
                    if (mounted) setRasterPanel(() => module.RasterPanel);
                  })
                : tool === "sign"
                  ? loadModule(
                      "sign",
                      () => import("./sign/SignPanel"),
                      retry,
                      controller.signal,
                    ).then((module) => {
                      if (mounted) setSignPanel(() => module.SignPanel);
                    })
                  : tool === "compress"
                    ? loadModule(
                        "compress",
                        () => import("./compress/CompressPanel"),
                        retry,
                        controller.signal,
                      ).then((module) => {
                        if (mounted)
                          setCompressPanel(() => module.CompressPanel);
                      })
                    : tool === "photos"
                      ? loadModule(
                          "photos",
                          () => import("./photos/PhotoPanel"),
                          retry,
                          controller.signal,
                        ).then((module) => {
                          if (mounted) setPhoto(() => module.PhotoPanel);
                        })
                      : tool === "split"
                        ? loadModule(
                            "split",
                            () => import("./split/SplitPanel"),
                            retry,
                            controller.signal,
                          ).then((module) => {
                            if (mounted) setSplitPanel(() => module.SplitPanel);
                          })
                        : tool === "rotate"
                          ? loadModule(
                              "rotate",
                              () => import("./rotate/RotatePanel"),
                              retry,
                              controller.signal,
                            ).then((module) => {
                              if (mounted)
                                setRotatePanel(() => module.RotatePanel);
                            })
                          : tool === "organize"
                            ? loadModule(
                                "organize",
                                () => import("./organize/OrganizePanel"),
                                retry,
                                controller.signal,
                              ).then((module) => {
                                if (mounted)
                                  setOrganizePanel(() => module.OrganizePanel);
                              })
                            : Promise.resolve();
    const initialize = async () => {
      try {
        const prepareEngine = async () => {
          if (tool === "unlock" || tool === "protect") return;
          const engineModule = await loadModule(
            "engine",
            () => import("./platform/engine"),
            retry,
            controller.signal,
          );
          if (!mounted) return;
          if (!engine.current) engine.current = new engineModule.Engine();
          if (!engineReady.current) {
            await engine.current.prepare(controller.signal);
            if (mounted) engineReady.current = true;
          }
        };
        enginePreparation.current = Promise.race([prepareEngine(), timedOut]);
        await Promise.race([
          Promise.all([
            enginePreparation.current,
            toolPreparation,
            panelPreparation,
          ]),
          timedOut,
        ]);
        if (mounted) {
          if (combineModule) setCombine(() => combineModule!.CombinePanel);
          processingReady.current = true;
          if (tool === "compress") setCompressResource("ready");
          setResource("ready");
          const selected = queuedInput.current;
          queuedInput.current = null;
          setWaitingForResources(false);
          if (selected) openQueuedInput(selected);
        }
      } catch {
        if (mounted) {
          if (tool === "compress") setCompressResource("error");
          setResource("error");
        }
      } finally {
        window.clearTimeout(timeout);
      }
    };
    void initialize();
    return () => {
      leavingDocument();
      window.removeEventListener("pagehide", leavingDocument);
      if (resourceController.current === controller)
        resourceController.current = null;
      window.clearTimeout(timeout);
      if (!engineReady.current) {
        engine.current?.dispose();
        engine.current = null;
      }
      disposeCompression();
    };
  }, [tool, retry]);

  const engineReady = useRef(false);
  useEffect(() => {
    const restore = (event: PageTransitionEvent) => {
      // Cancelled workers cannot be reused after a cross-document BFCache restore.
      if (event.persisted) location.reload();
    };
    window.addEventListener("pageshow", restore);
    return () => {
      window.removeEventListener("pageshow", restore);
      job.current?.abort();
      void active.current?.dispose();
      engine.current?.dispose();
      engineReady.current = false;
    };
  }, []);

  function clearCanvas() {
    const canvas = host.current?.querySelector("canvas");
    if (canvas) {
      canvas.width = 0;
      canvas.height = 0;
    }
    host.current?.replaceChildren();
  }
  function cancel() {
    serial.current++;
    job.current?.abort();
    job.current = null;
    setBusy("");
    setMessage("Cancelled. Your previous preview is unchanged.");
  }
  function clearPreview() {
    serial.current++;
    job.current?.abort();
    job.current = null;
    void active.current?.dispose();
    active.current = null;
    setCurrent(null);
    clearCanvas();
    setMessage("Choose a file to start a new task.");
    setBusy("");
    if (picker.current) picker.current.value = "";
  }
  function clear() {
    guard(abandonToHome);
  }
  async function startOrganize() {
    const revision = currentDocument(taskStateRef.current);
    if (job.current || !revision) return;
    const controller = new AbortController();
    job.current = controller;
    const id = ++serial.current;
    let timedOut = false;
    const rotating = toolRef.current === "rotate";
    setBusy(
      rotating
        ? "Checking your PDF…"
        : "Checking whether this PDF can be organized…",
    );
    setMessage("");
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, LIMITS.timeoutMs);
    try {
      const result = rotating
        ? await (
            await import("./rotate/service")
          ).inspectRotations(revision.file, controller.signal)
        : await (
            await import("./organize/service")
          ).inspectPages(revision.file, controller.signal);
      if (controller.signal.aborted || id !== serial.current) return;
      if (!result.ok) {
        if (
          rotating &&
          (result.reason === "standard" || result.reasons?.includes("standard"))
        ) {
          setPendingOrdinary(revision.file);
          return;
        }
        const detail =
          result.detail ||
          (result.reasons ?? (result.reason ? [result.reason] : []))
            .map((reason) => reasons[reason])
            .join(" ");
        setMessage(
          `${rotating ? "Rotation" : "Page organizing"} is unavailable for this PDF. ${detail} Your document is unchanged.`,
        );
        return;
      }
      setPhotos(false);
      setSplitting(false);
      setCombining(false);
      setCombineSeed(undefined);
      setOrganizing(true);
    } catch {
      if (id === serial.current)
        setMessage(
          timedOut
            ? `The ${rotating ? "rotation" : "page-organizing"} check took too long. Your document is unchanged. Try a smaller PDF.`
            : `The ${rotating ? "rotation" : "page-organizing"} check could not finish. Your document is unchanged. Try again.`,
        );
    } finally {
      clearTimeout(timer);
      if (id === serial.current) {
        job.current = null;
        setBusy("");
      }
    }
  }
  function download(file: File, name: string) {
    if (busy || photoBusy) return;
    try {
      const url = URL.createObjectURL(file);
      downloadUrls.current.add(url);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download =
        toolRef.current === "raster" ? name : safeFilename(name);
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => {
        URL.revokeObjectURL(url);
        downloadUrls.current.delete(url);
      }, 60000);
      setDownloadNotice({
        kind: "status",
        text: "Download started. Check your browser’s downloads.",
      });
      if (publicTool)
        track("download", publicTool, { fileCount: 1, totalBytes: file.size });
    } catch {
      setDownloadNotice({
        kind: "error",
        text: "Your result is still here. Download could not start. Please try again.",
      });
      if (publicTool) track("download_failure", publicTool);
    }
  }
  function resetTask() {
    sourceSeed.current = null;
    setSourceStage("empty");
    setPendingSourceAction(null);
    restoreSourceFocus.current = null;
    setSourceFiles([]);
    queuedInput.current = null;
    setWaitingForResources(false);
    setDownloadNotice(null);
    clearPreview();
    updateTaskState(emptySession());
    setPreviewFile(null);
    setPendingCredential(null);
    setPendingOrdinary(null);
    setCombineSeed(undefined);
    setDeliveryIds([]);
    setCompressionSummary(null);
    setRasterResult(null);
    setUnlockResult(null);
    setProtectResult(null);
    setPhotoDirty(false);
    completed.current = false;
  }
  function closeTask() {
    if (!completed.current) abandonToHome();
  }
  async function publishSplit(
    files: File[],
    signal: AbortSignal,
    source: DocumentRevision,
    pageCounts: number[],
  ): Promise<boolean> {
    if (
      job.current ||
      !engine.current ||
      source !== currentDocument(taskStateRef.current)
    )
      return false;
    const before = taskStateRef.current;
    if (
      !files.length ||
      files.length !== pageCounts.length ||
      before.present.results.filter(
        (id) => before.present.documents[id]?.splitChild,
      ).length +
        files.length >
        50
    )
      return false;
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    job.current = controller;
    const id = ++serial.current;
    const candidates: DocumentRevision[] = [];
    try {
      const { renderPage } = await loadModule(
        "engine",
        () => import("./platform/engine"),
        retry,
        controller.signal,
      );
      for (const [i, file] of files.entries()) {
        if (controller.signal.aborted) throw new Error("Cancelled");
        setBusy(`Checking split result ${i + 1} of ${files.length}…`);
        const preview = await engine.current.open(
          file,
          controller.signal,
          () => {},
        );
        try {
          if (preview.doc.numPages !== pageCounts[i])
            throw new Error("Split page count mismatch");
          const rendered = await renderPage(preview, 1, controller.signal);
          rendered.canvas.width = rendered.canvas.height = 0;
          candidates.push({
            id: `document-${++documentIdentity.current}`,
            file,
            generated: true,
            splitChild: true,
            label: "Split PDF",
            pageIds: Array.from(
              { length: preview.doc.numPages },
              () => `page-${++pageIdentity.current}`,
            ),
          });
        } finally {
          await preview.dispose();
        }
      }
      if (
        controller.signal.aborted ||
        serial.current !== id ||
        taskStateRef.current !== before
      )
        return false;
      const documents = { ...before.present.documents };
      for (const revision of candidates) documents[revision.id] = revision;
      updateTaskState(
        commitWorkspace(before, {
          ...before.present,
          documents,
          results: candidates.map((r) => r.id),
        }),
      );
      completed.current = true;
      setDeliveryIds(candidates.map((r) => r.id));
      setScreen("result");
      setMessage(
        `Created ${files.length} split results. Your original is unchanged.`,
      );
      return true;
    } catch {
      return false;
    } finally {
      signal.removeEventListener("abort", abort);
      if (serial.current === id) {
        job.current = null;
        setBusy("");
      }
    }
  }
  async function openCredentialCopy(ordinary = false) {
    const original = ordinary ? pendingOrdinary : pendingCredential;
    if (!original || job.current) return;
    setPreparingCopy(true);
    try {
      setPendingCredential(null);
      setPendingOrdinary(null);
      const controller = new AbortController();
      job.current = controller;
      const id = ++serial.current;
      setBusy(
        ordinary
          ? "Preparing an ordinary PDF copy…"
          : "Preparing a copy without Content Credentials…",
      );
      const timer = setTimeout(() => controller.abort(), LIMITS.timeoutMs);
      let copyFile: File | undefined;
      try {
        const { credentialCopy } =
          await import("./platform/credential-service");
        const bytes = await credentialCopy(
          original,
          true,
          controller.signal,
          ordinary,
        );
        if (!controller.signal.aborted && id === serial.current && bytes)
          copyFile = new File(
            [bytes as Uint8Array<ArrayBuffer>],
            safeFilename(
              original.name.replace(/\.pdf$/i, "") +
                (ordinary ? "-ordinary.pdf" : "-without-credentials.pdf"),
            ),
            { type: "application/pdf" },
          );
      } catch {
        if (id === serial.current)
          setMessage(
            "The copy could not be prepared safely. Your original PDF and previous document are unchanged.",
          );
      } finally {
        clearTimeout(timer);
        if (id === serial.current) {
          job.current = null;
          setBusy("");
        }
      }
      if (
        copyFile &&
        id === serial.current &&
        (await run(copyFile, 1, {
          generated: true,
          asSource: true,
          label: ordinary
            ? "Create ordinary PDF copy"
            : "Create copy without Content Credentials",
        }))
      ) {
        if (
          toolRef.current === "sign" ||
          toolRef.current === "watermark" ||
          toolRef.current === "numbers"
        ) {
          setScreen("task");
        } else if (toolRef.current === "split") {
          setScreen("task");
          setSplitting(true);
        } else if (
          toolRef.current === "organize" ||
          toolRef.current === "rotate"
        ) {
          setScreen("task");
          await startOrganize();
        } else if (toolRef.current === "compress") {
          setScreen("task");
          setCompressing(true);
        }
        setMessage(
          ordinary
            ? "This new ordinary PDF does not claim the original PDF/A, PDF/X or PDF/UA compliance. Colour settings and supported content are retained. The original file is unchanged."
            : "This new PDF does not retain the original C2PA Content Credentials. The original file is unchanged. You can now continue with this copy.",
        );
      }
    } finally {
      setPreparingCopy(false);
    }
  }
  async function run(
    file?: File,
    pageNumber = 1,
    options: {
      generated?: boolean;
      asSource?: boolean;
      label?: string;
      signal?: AbortSignal;
      pageIds?: string[];
      expectedPages?: number;
    } = {},
  ): Promise<boolean> {
    if (job.current || !engine.current) return false;
    const controller = new AbortController();
    job.current = controller;
    const externalAbort = () => controller.abort();
    options.signal?.addEventListener("abort", externalAbort, { once: true });
    if (options.signal?.aborted) controller.abort();
    const id = ++serial.current;
    let candidate: Preview | null = null;
    const releaseCandidate = () => {
      if (file && candidate && candidate !== active.current)
        void candidate.dispose();
    };
    controller.signal.addEventListener("abort", releaseCandidate, {
      once: true,
    });
    let timedOut = false;
    setMessage("");
    setBusy(file ? "Reading your file…" : "Preparing page…");
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, LIMITS.timeoutMs);
    try {
      let nextHistory: Session | null = null;
      let outputId: string | undefined;
      candidate = file
        ? await engine.current.open(file, controller.signal, (stage) => {
            if (id === serial.current) setBusy(stage);
          })
        : active.current;
      if (!candidate) return false;
      if (
        options.expectedPages !== undefined &&
        candidate.doc.numPages !== options.expectedPages
      )
        throw new Error("Output page count changed");
      if (file) {
        const revision: DocumentRevision = {
          file,
          generated: !!options.generated,
          id: `document-${++documentIdentity.current}`,
          label:
            options.label ??
            (options.generated ? "Create Photos PDF" : "Open PDF"),
          pageIds:
            options.pageIds ??
            Array.from(
              { length: candidate.doc.numPages },
              () => `page-${++pageIdentity.current}`,
            ),
        };
        if (options.generated && !options.asSource) {
          outputId = revision.id;
          const source = currentDocument(taskStateRef.current);
          nextHistory = commitWorkspace(taskStateRef.current, {
            documents: {
              ...(source ? { [source.id]: source } : {}),
              [revision.id]: revision,
            },
            activeId: source?.id ?? null,
            results: [revision.id],
          });
        } else nextHistory = commitDocument(taskStateRef.current, revision);
      }
      const { renderPage } = await loadModule(
        "engine",
        () => import("./platform/engine"),
        retry,
        controller.signal,
      );
      const rendered = await renderPage(
        candidate,
        pageNumber,
        controller.signal,
      );
      if (controller.signal.aborted || id !== serial.current) {
        rendered.canvas.width = 0;
        rendered.canvas.height = 0;
        return false;
      }
      if (outputId && nextHistory) {
        rendered.canvas.width = rendered.canvas.height = 0;
        updateTaskState(nextHistory);
        completed.current = true;
        setDeliveryIds([outputId]);
        setOrganizing(false);
        setScreen("result");
        return true;
      }
      clearCanvas();
      host.current?.append(rendered.canvas);
      if (file) {
        const previous = active.current;
        active.current = candidate;
        setCurrent(candidate);
        if (nextHistory) updateTaskState(nextHistory);
        void previous?.dispose();
        if (
          (toolRef.current === "sign" ||
            toolRef.current === "compress" ||
            toolRef.current === "numbers" ||
            toolRef.current === "watermark") &&
          !options.generated &&
          candidate.previewFeatures.includes("standard")
        )
          setPendingOrdinary(file);
      }
      return true;
    } catch (error) {
      if (id !== serial.current) return false;
      if (
        file &&
        !options.generated &&
        !controller.signal.aborted &&
        error instanceof ProbeFailure &&
        (error.reason === "signature" || error.reasons?.includes("signature"))
      ) {
        try {
          const { credentialCopy } =
            await import("./platform/credential-service");
          await credentialCopy(file, false, controller.signal);
          if (!controller.signal.aborted && id === serial.current) {
            setPendingCredential(file);
            setMessage(
              "This PDF has C2PA Content Credentials. Creating an editable copy requires your confirmation.",
            );
            return false;
          }
        } catch {
          /* Keep the ordinary refusal when another signature or structure prevents a safe copy. */
        }
      }
      const text = timedOut
        ? "This preview took too long. Try a smaller or simpler PDF."
        : controller.signal.aborted
          ? "Cancelled. Your previous preview is unchanged."
          : error instanceof ProbeFailure && error.reason
            ? `${(error.reasons ?? [error.reason]).map((reason) => reasons[reason]).join(" ")} ${copy.unsupported}`
            : "We couldn’t preview this PDF safely. Try another file. Your previous preview is unchanged.";
      setMessage(text);
      return false;
    } finally {
      options.signal?.removeEventListener("abort", externalAbort);
      controller.signal.removeEventListener("abort", releaseCandidate);
      clearTimeout(timer);
      if (file && candidate && candidate !== active.current)
        await candidate.dispose();
      if (id === serial.current) {
        job.current = null;
        setBusy("");
      }
    }
  }

  return (
    <div
      className={`app product-app ${screen === "task" && (tool === "protect" || tool === "unlock" || photos || combining || organizing || splitting || signing || compressing || rastering || watermarking || numbering) ? "is-editing" : ""} ${pristineTask ? "is-pristine" : ""}`}
      data-screen={screen}
      data-tool={tool}
    >
      {pendingSourceAction && (
        <LeaveTaskDialog
          description="Your selected files will be cleared from this task."
          keep={() => {
            if (sourceStage === "pending")
              restoreSourceFocus.current = pendingSourceAction.trigger;
            setPendingSourceAction(null);
          }}
          leave={() => {
            const action = pendingSourceAction.action;
            setPendingSourceAction(null);
            action();
          }}
        />
      )}
      {preparingCopy && (
        <TaskNotice
          working
          message={busy || "Preparing your editable copy…"}
          title="Preparing an editable copy…"
          close={cancel}
        />
      )}
      {previewFile && (
        <FilePreview
          key={previewFile.file.name + previewFile.file.lastModified}
          file={previewFile.file}
          engine={previewFile.engine}
          existing={
            currentRevision?.file === previewFile.file
              ? (current ?? undefined)
              : undefined
          }
          close={() => setPreviewFile(null)}
        />
      )}
      <header>
        <a
          className="brand"
          href="/"
          aria-label="Smart PDF home"
          onClick={(e) => {
            e.preventDefault();
            e.currentTarget.focus({ preventScroll: true });
            showHome();
          }}
        >
          <span className="brand-mark" aria-hidden="true">
            S
          </span>
          <span className="brand-wordmark" aria-hidden="true">
            <span>Smart</span>
            <strong>PDF</strong>
          </span>
        </a>
        <ToolNavigation
          key={`${screen}-${tool}`}
          active={screen === "home" || tool === "read" ? undefined : tool}
          keepCurrent={screen !== "result"}
          disabled={!!busy || photoBusy || packing}
          choose={chooseTool}
        />
        <span className="version">Local tools · Cloud Word conversion</span>
      </header>
      <main>
        {screen === "home" && (
          <section className="tool-home">
            <span className="hero-eyebrow">PRIVATE PDF TOOLS</span>
            <h1>Simple PDF tools. Clear choices for your files.</h1>
            <p className="hero-lede">
              Merge, split, organize, sign and compress in your browser. Word to
              PDF, PowerPoint to PDF and PDF to Word use cloud conversion and
              upload only when you start.
            </p>
            <div className="tool-cards">
              {publicTools.map((t) => (
                <a
                  key={t}
                  href={toolPaths[t]}
                  aria-disabled={!!busy || photoBusy || packing}
                  onClick={(e) => {
                    e.preventDefault();
                    chooseTool(t);
                  }}
                >
                  <span className={`tool-icon icon-${t}`} aria-hidden="true">
                    <ToolIcon tool={t} />
                  </span>
                  <h2>{toolTitles[t]}</h2>
                  <p>{toolCatalog[t].summary}</p>
                </a>
              ))}
            </div>
            <TrustHighlights variant="home" />
          </section>
        )}
        {screen !== "home" && screen !== "result" && (
          <div className="task-heading">
            <button
              className="secondary"
              onClick={(event) => {
                event.currentTarget.focus({ preventScroll: true });
                showHome();
              }}
              disabled={!!busy || photoBusy || packing}
            >
              ← All tools
            </button>
            <div>
              <h1>
                {screen === "preview"
                  ? (current?.name ?? "Read PDF")
                  : toolTitles[tool]}
              </h1>
              <p>
                {screen === "preview"
                  ? "Read-only preview. Close when you are finished."
                  : toolTaglines[tool]}
              </p>
            </div>
          </div>
        )}
        {screen === "task" && (
          <div className="task-privacy-banner" role="note">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 3 5.5 5.6v5.2c0 4.4 2.7 8.4 6.5 10.2 3.8-1.8 6.5-5.8 6.5-10.2V5.6L12 3Z" />
              <path d="m9 12 2 2 4-4" />
            </svg>
            <div>
              <strong>Private by design</strong>
              <span>Processed on this device · No file or filename upload</span>
            </div>
          </div>
        )}
        <div
          className="workspace"
          onChangeCapture={(event) => {
            const target = event.target;
            if (
              target instanceof HTMLInputElement &&
              target.type === "file" &&
              target.dataset.taskSource === "true" &&
              target.files?.length &&
              toolRef.current !== "read"
            )
              track("file_selected", toolRef.current, {
                fileCount: target.files.length,
                totalBytes: Array.from(target.files).reduce(
                  (sum, file) => sum + file.size,
                  0,
                ),
              });
          }}
        >
          <aside className="panel">
            <div
              className={`status ${resource}${(resource === "loading" && !waitingForResources) || (tool === "unlock" && sourceStage !== "empty" && UnlockPanel) || (tool === "protect" && sourceStage !== "empty" && ProtectPanel) ? " silent" : ""}`}
              role="status"
            >
              <span className="status-dot" />
              {resource === "ready"
                ? "Ready for local processing"
                : resource === "error"
                  ? waitingForResources
                    ? "Processing resources couldn’t load. Your selected PDF is kept; retry to continue."
                    : "Processing resources couldn’t load"
                  : waitingForResources
                    ? "Opening your PDF… Your file stays on this device."
                    : null}
            </div>
            {resource === "error" &&
              ((tool !== "unlock" && tool !== "protect") ||
                sourceStage === "empty" ||
                (tool === "unlock" ? !UnlockPanel : !ProtectPanel)) && (
                <button
                  onClick={() => {
                    setResource("loading");
                    setRetry(retry + 1);
                  }}
                >
                  Retry loading
                </button>
              )}
            {tool !== "unlock" && tool !== "protect" && (
              <div
                className="document-input"
                onDragOver={(e) => {
                  if (e.dataTransfer.types.includes("Files"))
                    e.preventDefault();
                }}
                onDrop={(e) => {
                  if (e.dataTransfer.files.length) {
                    e.preventDefault();
                    if (e.dataTransfer.files.length !== 1) {
                      setMessage("Choose one PDF for this tool.");
                      return;
                    }
                    importPdf(e.dataTransfer.files[0]!);
                  }
                }}
              >
                <FilePicker
                  inputRef={picker}
                  key={taskKey}
                  id="pdf-file"

                  accept=".pdf,application/pdf"
                  disabled={!!busy || photoBusy || packing}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    event.target.value = "";
                    if (file) importPdf(file);
                  }}
                >
                  Choose a PDF
                </FilePicker>
                <p className="limits">
                  One PDF · up to 30 MiB · 200 pages · no upload
                </p>
                <details className="input-support">
                  <summary>File support</summary>
                  <p>
                    Opens ordinary, unencrypted PDFs with supported links,
                    bookmarks, forms and comments. Complex signatures, scripts
                    or very large pages may be refused with a reason.
                  </p>
                </details>
              </div>
            )}
            {tool !== "raster" &&
              current?.previewFeatures.includes("standard") &&
              currentRevision && (
                <button
                  className="secondary"
                  disabled={!!busy || photoBusy}
                  onClick={() =>
                    guard(() => setPendingOrdinary(currentRevision.file))
                  }
                >
                  Create ordinary PDF copy
                </button>
              )}
            {pendingOrdinary && (
              <ConfirmDialog
                title="Create an ordinary PDF copy"
                onCancel={() => setPendingOrdinary(null)}
                action={
                  <button onClick={() => void openCredentialCopy(true)}>
                    Create ordinary copy without standard claims
                  </button>
                }
              >
                <p>
                  Changing this document cannot preserve a verified PDF/A, PDF/X
                  or PDF/UA compliance claim. Create an ordinary PDF with those
                  declarations removed?
                </p>
                <p>
                  Page content, supported structure and output colour settings
                  will be retained. Your original file stays unchanged. The new
                  copy is not certified to the original standard.
                </p>
              </ConfirmDialog>
            )}
            {pendingCredential && (
              <ConfirmDialog
                title="Create a copy without Content Credentials"
                onCancel={() => setPendingCredential(null)}
                action={
                  <button onClick={() => void openCredentialCopy()}>
                    Create copy without credentials
                  </button>
                }
              >
                <p>
                  This PDF contains C2PA Content Credentials. Splitting or
                  changing it makes those credentials inapplicable to the new
                  file.
                </p>
                <p>
                  Continue to create a new PDF without the original credentials.
                  The new PDF will have no retained C2PA proof of its origin.
                  Your original file stays unchanged.
                </p>
              </ConfirmDialog>
            )}
            {splitting && current && currentRevision && SplitPanel && (
              <Suspense fallback={<ToolLoading />}>
                <SplitPanel
                  key={currentRevision.id}
                  ref={splitPanel}
                  file={currentRevision.file}
                  preview={current}
                  pages={current.doc.numPages}
                  retained={sessionBytes(taskState)}
                  existingNames={Object.values(taskState.present.documents).map(
                    (d) => d.file.name,
                  )}
                  existingResults={
                    taskState.present.results.filter(
                      (id) => taskState.present.documents[id]?.splitChild,
                    ).length
                  }
                  publish={(files, signal, pageCounts) =>
                    publishSplit(files, signal, currentRevision, pageCounts)
                  }
                  onClose={closeTask}
                  onDirty={setPhotoDirty}
                  onBusy={setPhotoBusy}
                />
              </Suspense>
            )}
            {screen === "result" && (
              <Completion
                title={
                  {
                    ppt: "Your PDF is ready",
                    pdfword: "Your Word document is ready",
                    word: "Your PDF is ready",
                    excel: "Your PDF is ready",
                    unlock: "Your unlocked PDF is ready",
                    protect: "Your protected PDF is ready",
                    numbers: "Your numbered PDF is ready",
                    watermark: "Your watermarked PDF is ready",
                    raster: "Your images are ready",
                    sign: "Your signed PDF is ready",
                    compress: compressionSummary?.alreadyOptimized
                      ? "This PDF is already optimized"
                      : "Your compressed PDF is ready",
                    photos: "Your images are now a PDF",
                    combine: "Your PDFs have been merged",
                    organize: "Your PDF has been organized",
                    rotate: "Your rotated PDF is ready",
                    split: "Your PDF has been split",
                    read: "Your PDF is ready",
                  }[tool]
                }
                imageResult={rasterResult}
                files={
                  protectResult
                    ? [protectResult.file]
                    : unlockResult
                      ? [unlockResult.file]
                      : rasterResult
                        ? [rasterResult.file]
                        : deliveryIds
                            .map((id) => taskState.present.documents[id]?.file)
                            .filter((file): file is File => !!file)
                }
                pages={
                  protectResult?.pages ??
                  unlockResult?.pages ??
                  deliveryIds.reduce(
                    (sum, id) =>
                      sum +
                      (taskState.present.documents[id]?.pageIds?.length ?? 0),
                    0,
                  )
                }
                packing={packing}
                disabled={packing || !!busy || photoBusy}
                notice={downloadNotice}
                compression={tool === "compress" ? compressionSummary : null}
                restart={() => chooseTool(tool)}
                download={() => {
                  if (protectResult) {
                    download(protectResult.file, protectResult.file.name);
                    return;
                  }
                  if (unlockResult) {
                    download(unlockResult.file, unlockResult.file.name);
                    return;
                  }
                  if (rasterResult) {
                    download(rasterResult.file, rasterResult.file.name);
                    return;
                  }
                  if (deliveryIds.length > 1) void saveAll();
                  else {
                    const result =
                      taskStateRef.current.present.documents[deliveryIds[0]!];
                    if (result) download(result.file, result.file.name);
                  }
                }}
              />
            )}
            {compressing &&
              CompressPanel &&
              current &&
              currentRevision &&
              !current.previewFeatures.includes("standard") && (
                <Suspense fallback={<ToolLoading />}>
                  <CompressPanel
                    key={`${taskKey}-${currentRevision.id}`}
                    ref={compressPanel}
                    file={currentRevision.file}
                    pages={current.doc.numPages}
                    replace={() => {
                      resetTask();
                      setCompressing(false);
                      setScreen("task");
                      setTaskKey((key) => key + 1);
                    }}
                    apply={async (file, summary, signal) => {
                      const ok = await run(file, 1, {
                        generated: true,
                        label: "Compress PDF",
                        signal,
                        expectedPages: current.doc.numPages,
                      });
                      if (ok) setCompressionSummary(summary);
                      return ok;
                    }}
                    onDirty={setPhotoDirty}
                    onBusy={setPhotoBusy}
                  />
                </Suspense>
              )}
            {numbering &&
              NumberPanel &&
              current &&
              currentRevision &&
              !current.previewFeatures.includes("standard") && (
                <NumberPanel
                  key={`${taskKey}-${currentRevision.id}`}
                  ref={numberPanel}
                  file={currentRevision.file}
                  preview={current}
                  pageIds={currentRevision.pageIds ?? []}
                  retainedFiles={sessionFiles(taskState)}
                  apply={(file, ids, signal) =>
                    run(file, 1, {
                      generated: true,
                      label: "Add page numbers",
                      pageIds: ids,
                      signal,
                      expectedPages: current.doc.numPages,
                    })
                  }
                  onClose={closeTask}
                  onDirty={setPhotoDirty}
                  onBusy={setPhotoBusy}
                />
              )}
            {watermarking &&
              WatermarkPanel &&
              current &&
              currentRevision &&
              !current.previewFeatures.includes("standard") && (
                <WatermarkPanel
                  key={`${taskKey}-${currentRevision.id}`}
                  ref={watermarkPanel}
                  file={currentRevision.file}
                  preview={current}
                  pageIds={currentRevision.pageIds ?? []}
                  retainedFiles={sessionFiles(taskState)}
                  apply={(file, ids, signal) =>
                    run(file, 1, {
                      generated: true,
                      label: "Add watermark",
                      pageIds: ids,
                      signal,
                      expectedPages: current.doc.numPages,
                    })
                  }
                  onClose={closeTask}
                  onDirty={setPhotoDirty}
                  onBusy={setPhotoBusy}
                />
              )}
            {rastering &&
              RasterPanel &&
              current &&
              currentRevision &&
              engine.current && (
                <RasterPanel
                  key={`${taskKey}-${currentRevision.id}`}
                  ref={rasterPanel}
                  file={currentRevision.file}
                  preview={current}
                  engine={engine.current}
                  publish={(result) => {
                    completed.current = true;
                    setRasterResult(result);
                    clearPreview();
                    setPhotoDirty(false);
                    setScreen("result");
                  }}
                  replace={() => chooseTool("raster")}
                  onClose={closeTask}
                  onDirty={setPhotoDirty}
                  onBusy={setPhotoBusy}
                />
              )}
            {signing && current && currentRevision && SignPanel && (
              <Suspense fallback={<ToolLoading />}>
                <SignPanel
                  key={`${taskKey}-${currentRevision.id}`}
                  ref={signPanel}
                  file={currentRevision.file}
                  preview={current}
                  apply={(file, signal) =>
                    run(file, 1, { generated: true, label: "Sign PDF", signal })
                  }
                  onDirty={setPhotoDirty}
                  onBusy={setPhotoBusy}
                />
              </Suspense>
            )}
            {screen === "task" &&
              organizing &&
              tool === "rotate" &&
              current &&
              currentRevision?.pageIds &&
              RotatePanel && (
                <RotatePanel
                  key={taskKey}
                  ref={organizePanel}
                  file={currentRevision.file}
                  preview={current}
                  pageIds={currentRevision.pageIds}
                  retainedFiles={sessionFiles(taskState)}
                  apply={(file, pageIds, signal) =>
                    run(file, 1, {
                      generated: true,
                      label: "Rotate PDF",
                      pageIds,
                      signal,
                    })
                  }
                  onClose={closeTask}
                  onDirty={setPhotoDirty}
                  onBusy={setPhotoBusy}
                />
              )}
            {organizing &&
              tool !== "rotate" &&
              current &&
              currentRevision?.pageIds &&
              OrganizePanel && (
                <Suspense fallback={<ToolLoading />}>
                  <OrganizePanel
                    key={taskKey}
                    ref={organizePanel}
                    file={currentRevision.file}
                    preview={current}
                    pageIds={currentRevision.pageIds}
                    retainedFiles={sessionFiles(taskState)}
                    apply={(file, pageIds, signal) =>
                      run(file, 1, {
                        generated: true,
                        label: "Organize pages",
                        pageIds,
                        signal,
                      })
                    }
                    onClose={closeTask}
                    onDirty={setPhotoDirty}
                    onBusy={setPhotoBusy}
                  />
                </Suspense>
              )}
            {tool === "protect" &&
              screen === "task" &&
              sourceStage === "empty" && (
                <SourcePicker
                  kind="protect"
                  select={(files) => {
                    if (files.length !== 1) {
                      setMessage("Choose one PDF for this tool.");
                      return;
                    }
                    selectSources(files);
                  }}
                />
              )}
            {tool === "protect" &&
              screen === "task" &&
              sourceStage !== "empty" &&
              !ProtectPanel &&
              resource !== "error" && (
                <section className="photo-task">
                  <p role="status">Opening your PDF…</p>
                  <button
                    className="secondary"
                    onClick={() => {
                      resetTask();
                      setTaskKey((key) => key + 1);
                    }}
                  >
                    Cancel task
                  </button>
                </section>
              )}
            {tool === "protect" &&
              screen === "task" &&
              sourceStage !== "empty" &&
              ProtectPanel && (
                <ProtectPanel
                  key={taskKey}
                  ref={protectPanel}
                  seed={sourceFiles}
                  consume={sourceConsumed}
                  pause={!!pendingSourceAction}
                  replace={() => {
                    resetTask();
                    setTaskKey((key) => key + 1);
                  }}
                  onDirty={setPhotoDirty}
                  onBusy={setPhotoBusy}
                  publish={(file, pages) => {
                    completed.current = true;
                    setProtectResult({ file, pages });
                    setPhotoDirty(false);
                    setScreen("result");
                  }}
                />
              )}
            {tool === "unlock" &&
              screen === "task" &&
              sourceStage === "empty" && (
                <SourcePicker
                  kind="unlock"
                  select={(files) => {
                    if (files.length !== 1) {
                      setMessage("Choose one PDF for this tool.");
                      return;
                    }
                    selectSources(files);
                  }}
                />
              )}
            {tool === "unlock" &&
              screen === "task" &&
              sourceStage !== "empty" &&
              !UnlockPanel &&
              resource !== "error" && (
                <section className="photo-task">
                  <p role="status">Opening your PDF…</p>
                  <button
                    className="secondary"
                    onClick={() => {
                      resetTask();
                      setTaskKey((key) => key + 1);
                    }}
                  >
                    Cancel task
                  </button>
                </section>
              )}
            {tool === "unlock" &&
              screen === "task" &&
              sourceStage !== "empty" &&
              UnlockPanel && (
                <UnlockPanel
                  key={taskKey}
                  ref={unlockPanel}
                  seed={sourceFiles}
                  consume={sourceConsumed}
                  pause={!!pendingSourceAction}
                  replace={() => {
                    resetTask();
                    setTaskKey((key) => key + 1);
                  }}
                  onDirty={setPhotoDirty}
                  onBusy={setPhotoBusy}
                  publish={(file, pages) => {
                    completed.current = true;
                    setUnlockResult({ file, pages });
                    setPhotoDirty(false);
                    setScreen("result");
                  }}
                />
              )}
            {combining && sourceStage === "empty" && !combineSeed && (
              <SourcePicker kind="combine" select={selectSources} />
            )}
            {combining &&
              (sourceStage !== "empty" || combineSeed) &&
              !Combine && <ToolLoading />}
            {combining &&
              Combine &&
              (sourceStage !== "empty" || combineSeed) && (
                <Combine
                  key={taskKey}
                  ref={combinePanel}
                  ready={resource === "ready"}
                  seed={combineSeed}
                  seedFiles={sourceFiles}
                  onSeedConsumed={() => sourceConsumed(sourceFiles)}
                  pauseInitialInput={!!pendingSourceAction}
                  previewFile={openPreview}
                  thumbnail={async (file, signal) => {
                    await enginePreparation.current;
                    if (!engine.current) throw Error("Not ready");
                    return firstPageThumbnail(engine.current, file, signal);
                  }}
                  retainedFiles={sessionFiles(taskState)}
                  apply={async (file, signal) => {
                    const ok = await run(file, 1, {
                      generated: true,
                      label: "Combine PDFs",
                      signal,
                    });
                    if (ok) setCombineSeed(undefined);
                    return ok;
                  }}
                  onClose={closeTask}
                  onDirty={setPhotoDirty}
                  onBusy={setPhotoBusy}
                />
              )}
            {photos && sourceStage === "empty" && (
              <SourcePicker kind="photos" select={selectSources} />
            )}
            {photos &&
              sourceStage !== "empty" &&
              !Photo &&
              resource !== "error" && <ToolLoading />}
            {photos && sourceStage !== "empty" && Photo && (
              <Suspense fallback={<ToolLoading />}>
                <Photo
                  key={taskKey}
                  ref={photoPanel}
                  ready={resource === "ready"}
                  seedFiles={sourceFiles}
                  onSeedConsumed={() => sourceConsumed(sourceFiles)}
                  pauseInitialInput={!!pendingSourceAction}
                  retainedBytes={sessionBytes(taskState)}
                  apply={(file, signal) =>
                    run(file, 1, { generated: true, signal })
                  }
                  onClose={closeTask}
                  onDirty={setPhotoDirty}
                  onBusy={setPhotoBusy}
                />
              </Suspense>
            )}
            {!!busy && (
              <div className="busy" role="status">
                <p>{busy}</p>
                <button className="secondary" onClick={cancel}>
                  Cancel
                </button>
              </div>
            )}
            {!!message && screen !== "result" && (
              <p className="message" role="alert">
                {message}
              </p>
            )}
          </aside>
          <div ref={host} hidden />
          {screen === "preview" && currentRevision && (
            <section className="reader-entry">
              <button onClick={() => openPreview(currentRevision.file)}>
                Open preview
              </button>
              <button className="secondary" onClick={clear}>
                Close document
              </button>
            </section>
          )}
        </div>
        {screen === "home" && <SeoContent tool={null} />}
        {pristineTask && publicTool && <SeoContent tool={publicTool} />}
        <footer className="site-footer">
          <div className="footer-brand">
            <a href="/" className="footer-wordmark">
              <span className="brand-mark" aria-hidden="true">
                S
              </span>
              <span className="brand-wordmark">
                <span>Smart</span>
                <strong>PDF</strong>
              </span>
            </a>
            <p>
              PDF tools on your device, plus clearly marked cloud Word and
              PowerPoint and PDF to Word conversion.
            </p>
            <span className="australia-badge">Proudly built in Australia</span>
          </div>
          <nav aria-label="PDF tools" className="footer-column footer-tools">
            <strong>PDF tools</strong>
            <div
              className="footer-tool-links"
              style={{
                gridTemplateRows: `repeat(${Math.ceil(publicTools.length / 2)}, auto)`,
              }}
            >
              {publicTools.map((id) => (
                <a key={id} href={toolPaths[id]}>
                  {toolCatalog[id].title}
                </a>
              ))}
            </div>
          </nav>
          <div className="footer-column footer-contact">
            <strong>Support &amp; information</strong>
            <a href="/privacy/">Privacy</a>
            <a href="/notices/index.html" target="_blank" rel="noreferrer">
              Third-party notices
            </a>
            <a href="https://smartworks.au" target="_blank" rel="noreferrer">
              A SmartWorks product ↗
            </a>
          </div>
          <div className="footer-bottom">
            <span>© 2026 Smart PDF</span>
            <span aria-hidden="true">·</span>
            <span>
              Contact:{" "}
              <a href="mailto:hi@smartpdf.com.au">hi@smartpdf.com.au</a>
            </span>
          </div>
        </footer>
      </main>
    </div>
  );
}
