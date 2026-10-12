export function createScanLatch() {
  let detected = false;
  return {
    accept(): boolean {
      if (detected) return false;
      detected = true;
      return true;
    },
    hasAccepted(): boolean { return detected; },
  };
}

export function stopMediaTracks(stream: MediaStream | null): void {
  stream?.getTracks().forEach((track) => track.stop());
}
