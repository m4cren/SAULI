import SearchPromptForm from "./_components/SearchPromptForm";
import SearchTip from "./_components/SearchTip";
import MissingReportsShortcut from "./_components/MissingReportsShortcut";

export default function Page() {
  return (
    <main className="sauli-page pt-[52px]">
      <h1 className="sauli-title">What did you lose?</h1>
      <p className="sauli-subtitle mt-1">Describe the item naturally. Add details you remember.</p>
      <SearchPromptForm />
      <MissingReportsShortcut />
      <SearchTip />
    </main>
  );
}
