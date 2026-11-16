import js from "@eslint/js";
import ts from "typescript-eslint";
import hooks from "eslint-plugin-react-hooks";
export default ts.config(
  {
    ignores: [
      "dist/**",
      "dist-*/**",
      ".local-python/**",
      "test-results-*/**",
      "node_modules/**",
      "public/**",
      "test-results/**",
      "docs/private-samples/**",
      "releases/**",
    ],
  },
  js.configs.recommended,
  ...ts.configs.recommended,
  {
    files: ["tests/mobile/*.js"],
    languageOptions: {
      globals: {
        document: "readonly",
        window: "readonly",
        navigator: "readonly",
        screen: "readonly",
        devicePixelRatio: "readonly",
        performance: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        fetch: "readonly",
        URL: "readonly",
        Blob: "readonly",
      },
    },
  },
  {
    files: ["docs/ux/**/*.js"],
    languageOptions: {
      globals: {
        document: "readonly",
        window: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        structuredClone: "readonly",
      },
    },
    rules: { "no-useless-assignment": "off" },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: { "react-hooks": hooks },
    rules: { ...hooks.configs.recommended.rules },
  },
  {
    files: [
      "scripts/*.mjs",
      "scripts/excel/*.mjs",
      "infra/**/*.mjs",
      "server/**/*.mjs",
      "*.js",
    ],
    languageOptions: {
      globals: {
        console: "readonly",
        process: "readonly",
        Buffer: "readonly",
        TextEncoder: "readonly",
        URL: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
        AbortController: "readonly",
      },
    },
  },
  {
    files: [
      "scripts/diagnose-offline-files.mjs",
      "scripts/review-m0-m3-2026-10-08.mjs",
    ],
    languageOptions: {
      globals: {
        File: "readonly",
        FileReader: "readonly",
        document: "readonly",
      },
    },
  },
  {
    files: ["scripts/ux-preview-server.mjs"],
    languageOptions: { globals: { URL: "readonly" } },
  },
  {
    files: ["scripts/*.cjs"],
    languageOptions: {
      globals: { require: "readonly", process: "readonly" },
    },
    rules: { "@typescript-eslint/no-require-imports": "off" },
  },
);
