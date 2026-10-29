import { Icon } from "../../components/ui/Icon/Icon.jsx";
import styles from "./ContextPreview.module.css";

const CHARS_PER_TOKEN = 4;

// Same text as context_text() in back/Memories/Profile.py: the preview is what the model gets.
function fields(profile) {
  return [["name", profile.name], ["job", profile.role], ["department", profile.department],
    ["language", profile.language], ["tone", profile.tone]].map(([key, value]) => [key, value.trim()]).filter(([, value]) => value);
}

export function contextText(profile) {
  const lines = fields(profile).map(([key, value]) => `${key}: ${value}`);
  const instructions = profile.instructions.trim();
  if (!lines.length && !instructions) return "";
  const parts = ["[profile]", ...lines];
  if (instructions) parts.push("", "[instructions]", instructions);
  return parts.join("\n");
}

export function tokenEstimate(profile) {
  return Math.round(contextText(profile).length / CHARS_PER_TOKEN);
}

export function ContextPreview({ profile }) {
  const instructions = profile.instructions.trim();
  const empty = !contextText(profile);
  return (
    <aside className={styles.preview}>
      <div className={styles.header}><Icon name="cpu" size={16} /><h2 className="text-heading">Injected context</h2></div>
      <p className="text-small text-secondary">Added to the system message of every answer, whatever the persona.</p>
      {empty
        ? <p className="text-small text-secondary">Nothing yet: fill in a field to see what SENSAI will know about you.</p>
        : (
          <pre className={styles.code}>
            <span className={styles.section}>[profile]</span>{"\n"}
            {fields(profile).map(([key, value]) => (
              <span key={key}><span className={styles.key}>{key}:</span> {value}{"\n"}</span>
            ))}
            {instructions && <>{"\n"}<span className={styles.section}>[instructions]</span>{"\n"}{instructions}</>}
          </pre>
        )}
      <p className={styles.tokens}><span>Estimated size</span><span>≈ {tokenEstimate(profile)} tokens</span></p>
    </aside>
  );
}
