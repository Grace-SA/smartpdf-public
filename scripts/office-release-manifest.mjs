import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  prepareWordRuntime,
  wordRuntimePaths,
} from "./word-release-manifest.mjs";

export const officeRuntimePaths = [
  "server/office/service.mjs",
  "server/office/admission.mjs",
  "server/pdfword/service.mjs",
  "server/pdfword/docx-check.mjs",
  "server/pdfword/runner.py",
  "server/pdfword/worker.py",
  "server/pdfword/doctor.py",
  "server/pdfword/Dockerfile",
  "server/pdfword/requirements.txt",
  "config/pdfword-runtime.json",
  "server/ppt/service.mjs",
  "server/ppt/runner.py",
  "server/ppt/preflight.py",
  "server/ppt/svg_check.py",
  "server/ppt/layout.py",
  "server/ppt/export_uno.py",
  "server/ppt/doctor.py",
  "server/ppt/Dockerfile",
  "config/ppt-core.stirling-3.2.2.json",
  "infra/office/smartpdf-office.service",
];
const digest = (bytes) =>
  crypto.createHash("sha256").update(bytes).digest("hex");
export function prepareOfficeRuntime(source, folder) {
  const files = [...wordRuntimePaths, ...officeRuntimePaths].map((name) => {
    const file = path.join(source, name);
    if (!fs.existsSync(file) || !fs.lstatSync(file).isFile())
      throw Error(`Missing regular Office runtime file: ${name}`);
    const bytes = fs.readFileSync(file);
    return { path: name, bytes: bytes.length, sha256: digest(bytes) };
  });
  const ppt = JSON.parse(
    fs.readFileSync(
      path.join(source, "config/ppt-core.stirling-3.2.2.json"),
      "utf8",
    ),
  );
  if (
    ppt.flavor !== "core" ||
    !/^sha256:[a-f0-9]{64}$/.test(ppt.imageId) ||
    !/^sha256:[a-f0-9]{64}$/.test(ppt.baselineImageId) ||
    ppt.dockerfileSha256 !==
      digest(fs.readFileSync(path.join(source, "server/ppt/Dockerfile")))
  )
    throw Error(
      "PPT runtime core provenance does not match the approved image recipe",
    );
  const pdfword = JSON.parse(
    fs.readFileSync(path.join(source, "config/pdfword-runtime.json"), "utf8"),
  );
  if (
    !/^sha256:[a-f0-9]{64}$/.test(pdfword.imageId) ||
    pdfword.ocr !== false ||
    pdfword.scope !== "simple-native-text-only" ||
    pdfword.requirementsSha256 !==
      digest(
        fs.readFileSync(path.join(source, "server/pdfword/requirements.txt")),
      ) ||
    pdfword.dockerfileSha256 !==
      digest(fs.readFileSync(path.join(source, "server/pdfword/Dockerfile")))
  )
    throw Error(
      "PDF to Word runtime provenance does not match the reviewed image recipe",
    );
  const archive = path.join(folder, "office-runtime.tar");
  if (fs.existsSync(archive))
    throw Error("Office runtime archive already exists");
  const word = prepareWordRuntime(source, folder);
  execFileSync(
    "tar",
    ["-cf", archive, "-C", source, "--", ...files.map((file) => file.path)],
    { stdio: "pipe" },
  );
  const bytes = fs.readFileSync(archive);
  return {
    word,
    ppt,
    pdfword,
    files,
    archive: {
      path: "office-runtime.tar",
      bytes: bytes.length,
      sha256: digest(bytes),
    },
    install: "pnpm install --prod --frozen-lockfile --ignore-scripts",
    sharedAdmission: true,
    deployed: false,
  };
}
