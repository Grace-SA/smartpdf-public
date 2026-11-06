import { readSheets } from "./workbook";
self.onmessage = (event: MessageEvent<ArrayBuffer>) => {
  try {
    self.postMessage({ sheets: readSheets(new Uint8Array(event.data)) });
  } catch {
    self.postMessage({
      error:
        "Choose a valid, unencrypted XLSX workbook with up to 50 worksheets.",
    });
  }
};
