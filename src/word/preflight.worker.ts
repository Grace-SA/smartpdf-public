import { inspectWordBytes } from "./preflight-core";
self.onmessage = async (event: MessageEvent<File>) => {
  try {
    self.postMessage({
      result: inspectWordBytes(new Uint8Array(await event.data.arrayBuffer())),
    });
  } catch {
    self.postMessage({
      error:
        "This document could not be checked locally. Save a new DOCX copy in Word and try again.",
    });
  }
};
