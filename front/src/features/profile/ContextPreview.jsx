import { Icon } from "../../components/ui/Icon/Icon.jsx";
import styles from "./ContextPreview.module.css";

const CHARS_PER_TOKEN = 4;

function fields(profile) {
  return [["name", profile.name], ["job", profile.role], ["department", profile.service],
    ["language", profile.language], ["tone", profile.tone]].filter(([, value]) => value);
}

function contextText(profile) {
  const parts = ["[profile]", ...fields(profile).map(([key, value]) => `${key}: ${value}`)];
  if (profile.instructions.trim()) parts.push("", "[instructions]", profile.instructions.trim());
  return parts.join("\n");
}

export function tokenEstimate(profile) {
  return Math.round(contextText(profile).length / CHARS_PER_TOKEN);
}

export function ContextPreview({ profile }) {
  const instructions = profile.instructions.trim();
  return (
    <aside className={styles.preview}>
      <div className={styles.header}><Icon name="cpu" size={16} /><h2 className="text-heading">Injected context</h2></div>
      <p className="text-small text-secondary">Added to the system message at the start of every chat.</p>
      <pre className={styles.code}>
        <span className={styles.section}>[profile]</span>{"\n"}
        {fields(profile).map(([key, value]) => (
          <span key={key}><span className={styles.key}>{key}:</span> {value}{"\n"}</span>
        ))}
        {instructions && <>{"\n"}<span className={styles.section}>[instructions]</span>{"\n"}{instructions}</>}
      </pre>
      <p className={styles.tokens}><span>Estimated size</span><span>≈ {tokenEstimate(profile)} tokens</span></p>
    </aside>
  );
}
