"use client";

import { useContext } from "react";
import { ClaimantContext } from "@/providers/ClaimantProvider";

export function useClaimant() {
  const context = useContext(ClaimantContext);
  if (!context) throw new Error("useClaimant must be used inside ClaimantProvider.");
  return context;
}
