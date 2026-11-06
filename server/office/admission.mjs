// One host-wide active converter. Word's clean standby is evicted before PPT.
export function createOfficeAdmission({ pauseWord, resumeWord }) {
  const queue = [];
  let active = false,
    broken = false,
    closed = false;
  const aborted = () =>
    Object.assign(new Error("Cancelled"), { name: "AbortError" });
  const unsafe = () =>
    Object.assign(new Error("Converter cleanup requires operator attention"), {
      unsafe: true,
    });
  function rejectQueue(error) {
    for (const ticket of queue.splice(0)) {
      ticket.signal.removeEventListener("abort", ticket.abort);
      ticket.reject(error);
    }
  }
  function poison() {
    broken = true;
    rejectQueue(unsafe());
  }
  function pump() {
    if (active || broken || closed || !queue.length) return;
    const ticket = queue.shift();
    active = true;
    ticket.entering = true;
    void (async () => {
      try {
        if (ticket.kind === "ppt") {
          try {
            await pauseWord();
          } catch (error) {
            throw Object.assign(
              new Error("Idle converter cleanup could not be verified", {
                cause: error,
              }),
              { unsafe: true },
            );
          }
        }
        if (ticket.signal.aborted) throw aborted();
        ticket.signal.removeEventListener("abort", ticket.abort);
        let released = false;
        ticket.resolve(async (healthy = true) => {
          if (released) return;
          released = true;
          try {
            if (!healthy) poison();
            if (
              healthy &&
              !broken &&
              !closed &&
              ticket.kind === "ppt" &&
              queue[0]?.kind !== "ppt"
            )
              await resumeWord();
          } catch {
            poison();
          } finally {
            active = false;
            pump();
          }
        });
      } catch (error) {
        ticket.signal.removeEventListener("abort", ticket.abort);
        if (error.unsafe) poison();
        if (
          !broken &&
          !closed &&
          ticket.kind === "ppt" &&
          queue[0]?.kind !== "ppt"
        ) {
          try {
            await resumeWord();
          } catch {
            poison();
          }
        }
        active = false;
        ticket.reject(error);
        pump();
      }
    })();
  }
  return {
    fail: poison,
    available: () => !broken && !closed,
    acquire(kind, signal) {
      if (broken) return Promise.reject(unsafe());
      if (closed || signal.aborted) return Promise.reject(aborted());
      return new Promise((resolve, reject) => {
        const ticket = { kind, signal, resolve, reject, entering: false };
        ticket.abort = () => {
          if (ticket.entering) return; // Cleanup must finish before another engine enters.
          const index = queue.indexOf(ticket);
          if (index >= 0) queue.splice(index, 1);
          signal.removeEventListener("abort", ticket.abort);
          reject(aborted());
        };
        signal.addEventListener("abort", ticket.abort, { once: true });
        queue.push(ticket);
        pump();
      });
    },
    close() {
      closed = true;
      rejectQueue(aborted());
    },
  };
}
