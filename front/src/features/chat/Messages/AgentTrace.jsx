import { useState } from "react";
import { Icon } from "../../../components/ui/Icon/Icon.jsx";
import styles from "./Messages.module.css";

// [A1] How the answer was reached: what the agent thought, which tool it called, what came back.
const LABELS = { thought: "Thought", action: "Action", observation: "Result", tool_error: "Failed", note: "Note" };

function summary(steps, streaming) {
  const last = steps.at(-1);
  if (streaming && last?.kind === "action") return `${last.text}…`;
  if (streaming) return "Reasoning…";
  const calls = steps.filter((step) => step.kind === "action").length;
  return `Reasoning · ${calls} tool call${calls === 1 ? "" : "s"}`;
}

export function AgentTrace({ steps, streaming }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={styles.trace}>
      <button type="button" className={styles.traceToggle} aria-expanded={open} onClick={() => setOpen(!open)}>
        <Icon name="chevron-down" size={14} className={open ? styles.traceChevronOpen : styles.traceChevron} />
        <span>{summary(steps, streaming)}</span>
      </button>
      {open && (
        <ol className={styles.traceSteps}>
          {steps.map((step, index) => (
            <li key={index} className={styles.traceStep}>
              <span className={step.kind === "tool_error" ? styles.traceKindError : styles.traceKind}>
                {LABELS[step.kind] ?? step.kind}
              </span>
              <p className={step.kind === "observation" ? styles.traceOutput : styles.traceText}>{step.text}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
