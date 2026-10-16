declare module "libheif-js/libheif-wasm/libheif-bundle.mjs" {
  type HeifImage = {
    get_width(): number;
    get_height(): number;
    display(
      data: ImageData,
      callback: (result: ImageData | null) => void,
    ): void;
    free(): void;
  };
  export default function libheif(): Promise<{
    HeifDecoder: new () => { decode(bytes: Uint8Array): HeifImage[] };
  }>;
}
