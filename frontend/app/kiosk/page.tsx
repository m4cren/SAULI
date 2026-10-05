import KioskShell from "./_components/KioskShell";
import { KioskProvider } from "./_hooks/useKioskFlow";

export default function Page() {
  return <KioskProvider><KioskShell /></KioskProvider>;
}
