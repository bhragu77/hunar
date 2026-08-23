export function PlaceholderPage({ title, phase }: { title: string; phase: number }) {
  return (
    <div className="flex flex-col gap-2 p-8">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="text-muted-foreground">Coming in Phase {phase}.</p>
    </div>
  );
}
