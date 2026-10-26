import { useEffect, useState } from "react";
import { Button } from "../../../components/ui/Button/Button.jsx";
import { IconButton } from "../../../components/ui/IconButton/IconButton.jsx";
import { TestTag } from "../../../components/feedback/TestTag/TestTag.jsx";
import styles from "./Messages.module.css";

const COPIED_MS = 1500;

export function MessageActions({ text }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return undefined;
    const timer = setTimeout(() => setCopied(false), COPIED_MS);
    return () => clearTimeout(timer);
  }, [copied]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      // Clipboard refused (insecure context): nothing to show.
    }
  };

  return (
    <div className={styles.actions}>
      {copied
        ? <IconButton icon="check" iconSize={14} iconDisplay={16} label="Copied" onClick={copy} />
        : <IconButton icon="copy" label="Copy the answer" onClick={copy} />}
      <IconButton icon="refresh" label="Regenerate" test />
      <span className="separator separator--small" aria-hidden="true" />
      <Button variant="ghost" icon="file-text" disabled title="[TEST] Sources from the HR documents: not available yet">
        View sources <TestTag />
      </Button>
    </div>
  );
}
