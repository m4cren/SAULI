"use client";

import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Button from "@/app/components/Button";
import Icon from "@/app/components/Icon";
import { useClaimant } from "@/hooks/useClaimant";

export default function SearchPromptForm() {
  const { state, setDraft } = useClaimant();
  const [preview, setPreview] = useState<{ name: string; url: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview.url); }, [preview]);

  function onPhotoChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Choose an image file for the optional photo.");
      return;
    }
    setPreview({ name: file.name, url: URL.createObjectURL(file) });
    setDraft({ ...state.searchDraft, photoName: file.name });
    setError(null);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (state.searchDraft.description.trim().length < 4) {
      setError("Describe your item in at least four characters.");
      return;
    }
    setError(null);
    router.push("/search/filters");
  }

  return (
    <form onSubmit={submit} className="client-card p-4">
      <label htmlFor="lost-description" className="mb-4 flex items-center gap-2 text-[19px] font-bold text-[#092b35]"><span aria-hidden="true" className="text-[24px] leading-none text-[#299f93]">✦</span>Ask SAULI</label>
      <textarea id="lost-description" rows={9} maxLength={501} value={state.searchDraft.description} onChange={(event) => { setDraft({ ...state.searchDraft, description: event.target.value }); setError(null); }} placeholder="Example: Black wallet with a small silver logo, last seen near the library on August 21." className="client-field resize-y bg-[#f1faf9] p-4 leading-[1.45]" />
      {preview && <div className="mb-3 mt-3 flex items-center gap-2 rounded-xl border border-[#d7edeb] p-2"><span role="img" aria-label="Selected item preview" className="size-12 shrink-0 rounded-lg bg-cover bg-center" style={{ backgroundImage: `url(${JSON.stringify(preview.url)})` }} /><span className="min-w-0 truncate text-xs">{preview.name}</span></div>}
      <div className="mb-4 mt-3 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2"><label className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-xl border border-[#c9dcdf] bg-white px-3 text-sm font-semibold text-[#0b474f] focus-within:outline-2 focus-within:outline-[#0b474f]"><Icon name="camera" size={18} />Add photo<input type="file" accept="image/*" onChange={onPhotoChange} className="sr-only" /></label><span className="text-xs text-[#74858d]">Optional</span></div>
        <span aria-live="polite" className="shrink-0 text-xs text-[#74858d]">{state.searchDraft.description.length}/501</span>
      </div>
      {error && <p role="alert" className="mb-2 text-sm text-red-700">{error}</p>}
      <Button type="submit" className="client-primary-button w-full gap-2">Find my lost item <Icon name="search" size={22} /></Button>
    </form>
  );
}
