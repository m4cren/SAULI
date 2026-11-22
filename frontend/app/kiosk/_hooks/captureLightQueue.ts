export type CaptureLightSetter = (enabled: boolean) => Promise<unknown>;

export function createCaptureLightQueue(setLight: CaptureLightSetter) {
  let pending: Promise<void> = Promise.resolve();
  return (enabled: boolean) => {
    // A failed request is reported to its caller, but must not poison the
    // serialized queue and prevent a later OFF/safety request from running.
    pending = pending.catch(() => undefined)
      .then(() => setLight(enabled))
      .then(() => undefined);
    return pending;
  };
}
