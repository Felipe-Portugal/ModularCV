import { pickText, useApp } from "./ctx";
import { FactList } from "./FactsPage";
import { Card, Notice, Pill, ProblemList, StatusPill } from "./ui";

export default function SkillsPage() {
  const { m, lang, state } = useApp();
  if (!state) return null;
  if (!state.facts.present) return <Notice tone="neutral" title={m.workspace.factsMissing} />;
  if (!state.facts.valid) {
    return (
      <Notice tone="danger" title={m.workspace.factsInvalid}>
        <ProblemList items={state.facts.errors} />
      </Notice>
    );
  }
  const content = state.content;
  return (
    <div className="space-y-8">
      <p className="max-w-2xl text-base leading-relaxed text-ink2">{m.facts.introSkills}</p>

      <section className="space-y-3" aria-labelledby="cv-skills">
        <div>
          <h2 id="cv-skills" className="font-display text-lg font-semibold">{m.skills.fromContent}</h2>
          <p className="mt-1 text-sm text-ink2">{m.skills.fromContentNote}</p>
        </div>
        {!content.present && <Notice tone="neutral" title={m.skills.contentMissing} />}
        {content.present && !content.valid && (
          <Notice tone="warning" title={m.skills.contentInvalid}>
            <ProblemList items={content.errors} />
          </Notice>
        )}
        {content.valid &&
          (content.skills ?? []).map((cat) => (
            <Card key={cat.id} title={pickText(cat.title, lang)}>
              <ul className="space-y-4">
                {cat.items.map((item) => {
                  const ok = item.supports.length > 0 && item.supports.every((s) => s.status === "CONFIRMED");
                  return (
                    <li key={item.id} className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="font-medium">{pickText(item.text, lang)}</p>
                        <p className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-ink2">
                          {m.skills.supports}:
                          {item.supports.length === 0 && <span>{m.skills.unsupported}</span>}
                          {item.supports.map((s) => (
                            <span key={s.id} className="inline-flex items-center gap-1">
                              <code className="font-mono">{s.id}</code>
                              {s.status ? <StatusPill status={s.status} /> : <Pill tone="danger">?</Pill>}
                            </span>
                          ))}
                        </p>
                      </div>
                      <Pill tone={ok ? "success" : "warning"}>{ok ? m.skills.supportedOk : m.skills.supportedNo}</Pill>
                    </li>
                  );
                })}
              </ul>
            </Card>
          ))}
      </section>

      <section className="space-y-3" aria-labelledby="skill-facts">
        <h2 id="skill-facts" className="font-display text-lg font-semibold">{m.skills.factsTitle}</h2>
        <FactList group="skills" />
      </section>
    </div>
  );
}
