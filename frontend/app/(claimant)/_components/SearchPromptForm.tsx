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
    <form onSubmit={submit} className="mt-[44px] rounded-[12px] bg-white p-[15px] shadow-[0_3px_4px_rgba(0,0,0,0.15)]">
      <label htmlFor="lost-description" className="block text-[16px] font-semibold tracking-[0.04em]">Ask SAULI</label>
      <textarea id="lost-description" maxLength={501} value={state.searchDraft.description} onChange={(event) => { setDraft({ ...state.searchDraft, description: event.target.value }); setError(null); }} placeholder="Example: Black wallet with a small silver logo, dropped 12 o’clock past August 21" className="mt-1 h-[154px] w-full resize-none rounded-md border-0 bg-transparent text-[17px] leading-[1.35] text-[#333] outline-none placeholder:text-[#8d8d8d] focus-visible:ring-2 focus-visible:ring-[var(--sauli-brand)]" />
      {preview && <div className="mb-3 flex items-center gap-2 rounded-md border border-[var(--sauli-border)] p-2"><span role="img" aria-label="Selected item preview" className="size-12 shrink-0 rounded bg-cover bg-center" style={{ backgroundImage: `url(${JSON.stringify(preview.url)})` }} /><span className="min-w-0 truncate text-xs">{preview.name}</span></div>}
      <div className="mb-2 flex items-center justify-between">
        <label className="inline-flex min-h-11 cursor-pointer items-center rounded-md border border-[var(--sauli-border)] px-3 text-xs tracking-[0.08em] focus-within:outline-2 focus-within:outline-[var(--sauli-brand)]">+ Photo<input type="file" accept="image/*" onChange={onPhotoChange} className="sr-only" /></label>
        <span aria-live="polite" className="text-[11px] text-[#8e8e8e]">{state.searchDraft.description.length}/501</span>
      </div>
      {error && <p role="alert" className="mb-2 text-sm text-red-700">{error}</p>}
      <Button type="submit" className="w-full gap-2">Find my lost item <Icon name="search" size={22} /></Button>
    </form>
  );
}
