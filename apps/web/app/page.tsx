export default function HomePage() {
  return (
    <main className="container mx-auto flex min-h-screen flex-col items-center justify-center gap-6 px-6 py-12">
      <div className="max-w-2xl space-y-4 text-center">
        <p className="text-sm uppercase tracking-widest text-muted-foreground">
          pre-alpha · scaffolding
        </p>
        <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">Krititva AI</h1>
        <p className="text-lg text-muted-foreground">
          Open-source project management for software agencies with a contextual multi-agent AI
          layer. Dual Waterfall / Agile per project, fully local by default.
        </p>
        <p className="text-sm text-muted-foreground">
          M0 Foundation is in progress. See <code>docs/krititva-roadmap.md</code>.
        </p>
      </div>
    </main>
  );
}
