export function checkDocx(
  file: string,
): Promise<{
  pages: number;
  sourceMarkers: number;
  images: number;
  tables: number;
}>;
