import { useState } from "react";
import { Button } from "../../components/ui/Button/Button.jsx";
import { Dropdown } from "../../components/ui/Dropdown/Dropdown.jsx";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { IconButton } from "../../components/ui/IconButton/IconButton.jsx";
import { downloadChat, FORMATS } from "./download.js";
import { ShareDialog } from "./ShareDialog.jsx";
import styles from "./ChatActions.module.css";

export function ChatActions({ conversationId, disabled, compact }) {
  const [sharing, setSharing] = useState(false);
  const save = (format) => downloadChat(conversationId, format).catch((failure) => window.alert(`Export failed: ${failure.message}`));
  const items = [
    { heading: "Download as" },
    ...FORMATS.map((format) => ({
      label: format.label, meta: `.${format.id}`, icon: <Icon name="file-text" size={16} />, onSelect: () => save(format.id),
    })),
  ];

  return (
    <div className={styles.actions}>
      <Dropdown floating compact align="right" items={items} trigger={({ open, toggle }) => (compact
        ? <IconButton icon="download" label="Export" aria-haspopup="listbox" aria-expanded={open} disabled={disabled} onClick={toggle} />
        : <Button variant="ghost" icon="download" aria-haspopup="listbox" aria-expanded={open} disabled={disabled} onClick={toggle}>
            Export
          </Button>)} />
      {compact
        ? <IconButton icon="link" label="Share" disabled={disabled} onClick={() => setSharing(true)} />
        : <Button variant="ghost" icon="link" disabled={disabled} onClick={() => setSharing(true)}>Share</Button>}
      {sharing && <ShareDialog conversationId={conversationId} onClose={() => setSharing(false)} />}
    </div>
  );
}
