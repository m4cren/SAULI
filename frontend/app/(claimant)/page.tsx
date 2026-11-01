import SearchPromptForm from "./_components/SearchPromptForm";
import SearchTip from "./_components/SearchTip";
import MissingReportsShortcut from "./_components/MissingReportsShortcut";
import ClientHero from "@/app/components/ClientHero";

export default function Page() {
  return (
    <>
      <ClientHero title="What did you lose?" subtitle="Describe what you remember and SAULI will search for possible matches." />
      <main className="client-content client-overlap">
        <SearchPromptForm />
        <MissingReportsShortcut />
        <SearchTip />
      </main>
    </>
  );
}
