const allowedKioskActions = [
  /^found-items\/(analyze|reconcile-review|confirm-and-store)$/,
  /^found-items\/[0-9a-f-]{36}\/(request-unlock|simulate-placement)$/,
  /^storage-slots\/availability$/,
  /^retrieval-sessions\/validate$/,
  /^retrieval-sessions\/[0-9a-f-]{36}\/(request-unlock|simulate-(completion|wrong-item|item-returned))$/,
  /^hardware\/(workflow|capture-light)$/,
];

export function isAllowedKioskAction(path: string): boolean {
  return allowedKioskActions.some((rule) => rule.test(path));
}
