export type DoorId = "pocket-door" | "medium-door";

export function setDoorUnlocked(current: readonly DoorId[], door: DoorId, unlocked: boolean): DoorId[] {
  return unlocked ? current.includes(door) ? [...current] : [...current, door] : current.filter((item) => item !== door);
}
