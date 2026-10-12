"use client";

import { useEffect, useState } from "react";
import { listMissingReports, type MissingReportApi } from "@/libs/api/sauli";

export default function useMissingReports() {
  const [reports, setReports] = useState<MissingReportApi[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    void listMissingReports().then((result) => {
      if (active) { setReports(result); setError(false); }
    }).catch(() => {
      if (active) setError(true);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [attempt]);

  function refresh() {
    setLoading(true);
    setAttempt((value) => value + 1);
  }

  return { reports, loading, error, refresh };
}
