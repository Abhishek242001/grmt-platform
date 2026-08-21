export default function MarqueeBand({ items }: { items: string[] }) {
  const doubled = [...items, ...items];
  return (
    <div className="overflow-hidden whitespace-nowrap border-y border-[var(--color-accent-dark)] bg-[var(--color-accent)] text-white">
      <div className="animate-marquee inline-block py-3.5 font-display-bold text-xl">
        {doubled.map((item, i) => (
          <span key={i} className="mx-6">
            {item}
            <span className="ml-6">•</span>
          </span>
        ))}
      </div>
    </div>
  );
}
