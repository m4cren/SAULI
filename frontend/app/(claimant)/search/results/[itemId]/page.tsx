import ItemMatchDetails from "./_components/ItemMatchDetails";

export default async function Page({ params }: { params: Promise<{ itemId: string }> }) {
  const { itemId } = await params;
  return <ItemMatchDetails itemId={itemId} />;
}
