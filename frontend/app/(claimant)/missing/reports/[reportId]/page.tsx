import MissingReportReview from "./_components/MissingReportReview";

export default async function Page({ params }: { params: Promise<{ reportId: string }> }) {
  const { reportId } = await params;
  return <MissingReportReview reportId={reportId} />;
}
