import { XMLValidator } from "fast-xml-parser";
import { entries, xmlBytes } from "../word/preflight-core";

self.onmessage = async (event: MessageEvent<File>) => {
  try {
    const bytes = new Uint8Array(await event.data.arrayBuffer());
    const list = entries(bytes, 60 * 1024 ** 2);
    const main = list.find((entry) => entry.name === "ppt/presentation.xml");
    const types = list.find((entry) => entry.name === "[Content_Types].xml");
    if (!main || !types)
      throw Error("Save a standard PPTX presentation before converting.");
    for (const entry of [main, types]) {
      const text = new TextDecoder("utf-8", { fatal: true }).decode(
        xmlBytes(bytes, entry),
      );
      if (
        /<!\s*(DOCTYPE|ENTITY)/i.test(text) ||
        XMLValidator.validate(text) !== true
      )
        throw Error(
          "The presentation contains invalid XML. Save a new PPTX in PowerPoint.",
        );
      if (
        entry === types &&
        (!text.includes(
          "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
        ) ||
          /macroEnabled|vbaProject/i.test(text))
      )
        throw Error("Save a standard, macro-free PPTX before converting.");
    }
    if (
      list.some((entry) =>
        /vbaProject|activeX|oleObject|_xmlsignatures/i.test(entry.name),
      )
    )
      throw Error(
        "Remove macros, active objects or digital signatures before converting.",
      );
    self.postMessage({ result: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    self.postMessage({
      error: /DOCX|document|package/i.test(message)
        ? "Choose a valid, unprotected PPTX up to 60 MiB."
        : message || "Choose a valid PPTX presentation.",
    });
  }
};
