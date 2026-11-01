import Icon from "@/app/components/Icon";

export default function SearchTip() {
  return <aside className="client-info-card mt-5 flex items-start gap-3 p-4 text-[14px] leading-[1.4]"><span aria-hidden="true" className="flex size-10 shrink-0 items-center justify-center rounded-full bg-white text-[#0b8080]"><Icon name="lightbulb" size={28} /></span><span><strong className="mb-1 block text-[16px] text-[#0b474f]">Help SAULI find a better match</strong><span className="text-[#4f6974]">Include the color, brand, last-seen location, date, and one unique feature.</span></span></aside>;
}
