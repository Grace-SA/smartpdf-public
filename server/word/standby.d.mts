export type Standby = { name: string; token: string };
type Job = {
  kind?: "word" | "excel";
  state: string;
  options?: { revisionView?: string };
};
export function createStandby(options: {
  root: string;
  run: (
    job: { directory: string; warmToken?: string; discardToken?: string },
    update: (value: { standby?: Standby }) => void,
  ) => Promise<void>;
  broken: (error: unknown) => void;
}): {
  ensure: () => void;
  pause: () => Promise<void>;
  resume: () => void;
  ready: () => boolean;
  release: (ready: Standby | undefined) => Promise<void>;
  take: (job: Job) => Promise<Standby | undefined>;
  cancel: (job: Job) => Promise<void>;
  close: () => Promise<void>;
};
