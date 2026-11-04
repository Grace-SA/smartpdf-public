import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";

export const wordRuntimePaths = [
  "package.json",
  "pnpm-lock.yaml",
  "pnpm-workspace.yaml",
  "patches/pdf-lib@1.17.1.patch",
  "server/word/service.mjs",
  "server/word/pdf-check.mjs",
  "server/word/runner.py",
  "server/word/preflight.py",
  "server/word/doctor.py",
  "server/word/core_build.py",
  "server/word/font_inventory.py",
  "server/excel/preflight.py",
  "config/excel-core.stirling-3.2.2.json",
  "infra/word/nginx.conf",
  "infra/word/origin.conf.template",
  "infra/word/core.Dockerfile",
  "infra/word/smartpdf-word.service",
  "config/word-fonts.stirling-3.2.2.json",
  "config/word-core.stirling-3.2.2.json",
  "vendor-licenses/stirling-integration.txt",
];

const digest = (bytes) =>
  crypto.createHash("sha256").update(bytes).digest("hex");

export function prepareWordRuntime(source, folder) {
  const files = wordRuntimePaths.map((name) => {
    const file = path.join(source, name);
    if (!fs.existsSync(file) || !fs.lstatSync(file).isFile())
      throw new Error(`Missing regular Word runtime file: ${name}`);
    const bytes = fs.readFileSync(file);
    return { path: name, bytes: bytes.length, sha256: digest(bytes) };
  });
  const runner = fs.readFileSync(
    path.join(source, "server/word/runner.py"),
    "utf8",
  );
  const image = runner.match(/^IMAGE = '(sha256:[a-f0-9]{64})'$/m)?.[1];
  if (!image) throw new Error("Word runtime must use a fixed image digest.");
  const core = JSON.parse(
    fs.readFileSync(
      path.join(source, "config/word-core.stirling-3.2.2.json"),
      "utf8",
    ),
  );
  if (
    core.flavor !== "core" ||
    core.imageId !== image ||
    !/^[a-f0-9]{64}$/.test(core.jar?.sha256 || "") ||
    !/@sha256:[a-f0-9]{64}$/.test(core.baseImage || "") ||
    core.dockerfileSha256 !==
      digest(fs.readFileSync(path.join(source, "infra/word/core.Dockerfile")))
  )
    throw new Error(
      "Word runtime core provenance does not match the approved image.",
    );
  const fonts = JSON.parse(
    fs.readFileSync(
      path.join(source, "config/word-fonts.stirling-3.2.2.json"),
      "utf8",
    ),
  );
  if (!fonts.profile || !Array.isArray(fonts.fonts) || !fonts.fonts.length)
    throw new Error("Missing Word font inventory.");
  const archive = path.join(folder, "word-runtime.tar");
  if (fs.existsSync(archive))
    throw new Error("Word runtime archive already exists.");
  execFileSync(
    "tar",
    ["-cf", archive, "-C", source, "--", ...wordRuntimePaths],
    {
      stdio: "pipe",
    },
  );
  const bytes = fs.readFileSync(archive);
  return {
    image,
    core,
    fontProfile: fonts.profile,
    fontFiles: fonts.fonts.length,
    archive: {
      path: "word-runtime.tar",
      bytes: bytes.length,
      sha256: digest(bytes),
    },
    files,
    install: "pnpm install --prod --frozen-lockfile --ignore-scripts",
    deployed: false,
  };
}
