"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { getStorageSlotImages, type StorageSlotImages } from "@/libs/api/sauli";

export default function StoredItemImages({ itemId }: { itemId: string }) {
  const [images, setImages] = useState<StorageSlotImages | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const [failed, setFailed] = useState<string[]>([]);

  useEffect(() => {
    let active = true;
    getStorageSlotImages(itemId)
      .then((result) => { if (active) { setImages(result); setError(null); setFailed([]); } })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : "Item photos are unavailable."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [itemId, retry]);

  function reload() {
    setLoading(true);
    setError(null);
    setRetry((value) => value + 1);
  }

  const sides = [
    { label: "Side 1", url: images?.front_image_url },
    { label: "Side 2", url: images?.back_image_url },
  ];
  return <section className="admin-item-images" aria-label="Stored item photos" aria-busy={loading}>
    <div className="admin-item-images-heading"><h3>Captured item</h3>{(error || failed.length > 0) && <button type="button" onClick={reload} disabled={loading}>Retry photos</button>}</div>
    {loading ? <p role="status">Loading item photos…</p> : error ? <p role="alert">{error}</p> : <div className="admin-item-images-grid">
      {sides.map(({ label, url }) => <div key={label}><span>{label}</span><div className="admin-item-image-frame">
        {url && !failed.includes(label) ? <Image src={url} alt={`${label} of the stored item`} fill unoptimized sizes="(max-width: 700px) 45vw, 250px" className="object-contain" onError={() => setFailed((items) => [...items, label])} /> : <p>Photo unavailable</p>}
      </div></div>)}
    </div>}
  </section>;
}
