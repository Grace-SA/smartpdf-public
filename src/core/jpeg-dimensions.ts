import { LIMITS, ProbeFailure } from "./contracts";

// Inspect markers without decoding pixels. Walk every scan so a later frame or
// DNL marker cannot change the dimensions after the first checked header.
export function checkJpegDimensions(
  bytes: Uint8Array,
  declaredWidth: number,
  declaredHeight: number,
): void {
  const invalid = (): never => {
    throw new ProbeFailure("INVALID_INPUT", "malformed");
  };
  const word = (at: number) => (bytes[at]! << 8) | bytes[at + 1]!;
  if (bytes.length < 4 || word(0) !== 0xffd8) invalid();
  let at = 2,
    frame = false,
    scan = false,
    entropy = false;
  while (at < bytes.length) {
    if (entropy) {
      while (at < bytes.length && bytes[at] !== 255) at++;
    }
    if (bytes[at++] !== 255) invalid();
    while (bytes[at] === 255) at++;
    if (at >= bytes.length) invalid();
    const marker = bytes[at++]!;
    if (entropy && (marker === 0 || (marker >= 0xd0 && marker <= 0xd7)))
      continue;
    entropy = false;
    if (marker === 0xd9) {
      if (!frame || !scan) invalid();
      return;
    }
    if (
      marker === 0 ||
      marker === 0xd8 ||
      marker === 0x01 ||
      (marker >= 0xd0 && marker <= 0xd7) ||
      marker === 0xdc
    )
      invalid();
    if (at + 2 > bytes.length) invalid();
    const length = word(at);
    if (length < 2 || at + length > bytes.length) invalid();
    if (
      marker >= 0xc0 &&
      marker <= 0xcf &&
      ![0xc4, 0xc8, 0xcc].includes(marker)
    ) {
      if (frame || ![0xc0, 0xc1, 0xc2].includes(marker) || length < 8)
        invalid();
      const height = word(at + 3),
        width = word(at + 5);
      const components = bytes[at + 7]!;
      if (
        bytes[at + 2] !== 8 ||
        ![1, 3, 4].includes(components) ||
        length !== 8 + 3 * components ||
        width === 0 ||
        height === 0
      )
        invalid();
      if (width * height > LIMITS.jpegPixels)
        throw new ProbeFailure("RESOURCE_LIMIT", "image");
      if (width !== declaredWidth || height !== declaredHeight) invalid();
      frame = true;
    }
    if (marker === 0xda) {
      if (!frame || length < 6 || length !== 6 + 2 * bytes[at + 2]!) invalid();
      scan = true;
      entropy = true;
    }
    at += length;
  }
  invalid();
}
