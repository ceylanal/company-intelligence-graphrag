import { Building2, Network, Scale, ShieldCheck } from "lucide-react";

export function EmptyState({ onPrompt }: { onPrompt: (prompt: string) => void }) {
  const prompts = [
    {
      icon: Building2,
      title: "Company profile",
      text: "Summarize ASELSAN's reported strategy and key risks.",
    },
    {
      icon: Scale,
      title: "Compare companies",
      text: "Compare Turkcell and Türk Hava Yolları using available annual-report evidence.",
    },
    {
      icon: Network,
      title: "Explore relationships",
      text: "What strategic relationships are present in the GraphRAG evidence for Koç Holding?",
    },
  ];
  return (
    <section className="empty-state">
      <div className="empty-icon">
        <ShieldCheck size={31} />
      </div>
      <p className="eyebrow">Citation-first company intelligence</p>
      <h1>Research companies with traceable evidence.</h1>
      <p className="empty-copy">
        Ask a question, follow the live research workflow, then inspect every supporting source.
      </p>
      <div className="prompt-grid">
        {prompts.map(({ icon: Icon, title, text }) => (
          <button key={title} onClick={() => onPrompt(text)}>
            <Icon size={18} />
            <strong>{title}</strong>
            <span>{text}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
