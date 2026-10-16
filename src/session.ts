import { PHOTO_LIMITS, photoCopy } from "./photos/model";
export type DocumentRevision = {
  id: string;
  file: File;
  generated: boolean;
  label: string;
  pageIds?: string[];
  splitChild?: boolean;
};
export type Workspace = {
  documents: Record<string, DocumentRevision>;
  activeId: string | null;
  results: string[];
};
/** Only the current task's source and published results are retained. */
export type Session = { present: Workspace };
export const emptySession = (): Session => ({
  present: { documents: {}, activeId: null, results: [] },
});
export const currentDocument = (s: Session) =>
  s.present.activeId ? s.present.documents[s.present.activeId] : undefined;
export function sessionFiles(s: Session): File[] {
  return [...new Set(Object.values(s.present.documents).map((d) => d.file))];
}
export const sessionBytes = (s: Session) =>
  sessionFiles(s).reduce((n, f) => n + f.size, 0);
export function commitWorkspace(_s: Session, after: Workspace): Session {
  const kept = new Set([
    ...after.results,
    ...(after.activeId ? [after.activeId] : []),
  ]);
  const next = {
    present: {
      ...after,
      documents: Object.fromEntries(
        Object.entries(after.documents).filter(([id]) => kept.has(id)),
      ),
    },
  };
  if (sessionBytes(next) > PHOTO_LIMITS.sessionBytes)
    throw new Error(photoCopy.budget);
  return next;
}
export function commitDocument(
  s: Session,
  document: DocumentRevision,
): Session {
  return commitWorkspace(s, {
    activeId: document.id,
    documents: { [document.id]: document },
    results: [],
  });
}
