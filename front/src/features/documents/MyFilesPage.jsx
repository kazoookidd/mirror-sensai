import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "../../components/ui/Button/Button.jsx";
import { Checkbox } from "../../components/ui/Checkbox/Checkbox.jsx";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { IconButton } from "../../components/ui/IconButton/IconButton.jsx";
import { AppShell } from "../../layout/AppShell.jsx";
import { Page, PageHeader } from "../../layout/Page.jsx";
import { attachments as attachmentsApi } from "../../api/attachments.js";
import { documents as documentsApi } from "../../api/documents.js";
import { fileType, formatShortDate, formatSize, parseUtc } from "../../lib/format.js";
import { QueryButton } from "./DocumentButtons.jsx";
import { FileName } from "./FileName.jsx";
import { useAskSelection } from "./useAskSelection.js";
import styles from "./MyFilesPage.module.css";

function Section({ title, count, description, children }) {
  return (
    <section className={styles.section}>
      <div className={styles.sectionHeader}>
        <h2 className="text-heading">{title}</h2>
        {count != null && <span className="text-caption text-secondary">{count}</span>}
      </div>
      <p className={styles.description}>{description}</p>
      {children}
    </section>
  );
}

function JoinedFiles({ items, onDelete }) {
  if (!items.length) {
    return (
      <div className={styles.empty}>
        <p>No file yet. In a chat, join your contract or a letter with the paperclip <Icon name="paperclip" size={16} display={14} className={styles.inline} />: SENSAI answers from it in that chat only.</p>
        <Button icon="plus" to="/chat">New chat</Button>
      </div>
    );
  }
  return (
    <ul className={styles.list}>
      {items.map((item) => (
        <li key={item.id} className={styles.card}>
          <FileName source={item.source} meta={`${formatSize(item.size)} · ${formatShortDate(parseUtc(item.created_at))}`} iconSize={16} />
          <Link to={`/chat/${item.conversation_id}`} className={styles.chat} title={item.conversation_title}>
            <Icon name="message" size={16} display={14} />
            <span className="truncate">{item.conversation_title}</span>
          </Link>
          <IconButton icon="trash" label={`Delete ${item.source}`} onClick={() => onDelete(item)} />
        </li>
      ))}
    </ul>
  );
}

function SharedDocuments({ items }) {
  const [selection, setSelection] = useState(() => new Set());
  const [askError, setAskError] = useState(null);
  const askSelection = useAskSelection();
  if (!items.length) return <p className={styles.description}>HR has not added any document yet.</p>;
  const toggle = (source) => setSelection((current) => {
    const next = new Set(current);
    if (next.has(source))
      next.delete(source);
    else next.add(source);
    return next;
  });
  return (
    <>
      {selection.size > 0 && (
        <div className={styles.selectionBar}>
          <span>{selection.size} document{selection.size > 1 ? "s" : ""} selected</span>
          <QueryButton label="Ask about the selection" onClick={() => askSelection(selection).catch((error) => setAskError(error.message))} />
        </div>
      )}
      {askError && <p className="info-note" role="alert"><Icon name="alert" size={16} />{askError}</p>}
      <ul className={styles.list}>
        {items.map((item) => (
          <li key={item.source} className={styles.card} data-selected={selection.has(item.source)}>
            <Checkbox checked={selection.has(item.source)} onChange={() => toggle(item.source)} aria-label={`Select ${item.source}`} />
            <FileName source={item.source} meta={`${fileType(item.source)} · ${formatSize(item.size)}`} iconSize={16} />
          </li>
        ))}
      </ul>
    </>
  );
}

export function MyFilesPage() {
  const [joined, setJoined] = useState(null);
  const [shared, setShared] = useState(null);
  const [failed, setFailed] = useState(false);
  const [deleteFailed, setDeleteFailed] = useState(null);

  useEffect(() => {
    attachmentsApi.mine().then((data) => setJoined(data.attachments)).catch(() => setFailed(true));
    documentsApi.list().then((data) => setShared(data.documents)).catch(() => setFailed(true));
  }, []);

  const remove = async (item) => {
    if (!window.confirm(`Delete "${item.source}"? The chat "${item.conversation_title}" will no longer use it.`)) return;
    setDeleteFailed(null);
    try {
      await attachmentsApi.remove(item.id);
      setJoined((list) => list.filter((other) => other.id !== item.id));
    } catch {
      setDeleteFailed(item.source);
    }
  };

  return (
    <AppShell nav={{ active: "files", mobile: "root", tabs: true }} scroll>
      <Page>
        <PageHeader title="My files" subtitle="The files you joined to your chats, and the HR documents SENSAI answers from." />
        {failed && <p className="info-note"><Icon name="alert" size={16} />Could not read your files.</p>}
        {joined && (
          <Section title="Joined to my chats" count={joined.length}
            description="Only you can see them, and only their chat uses them. Deleting a chat deletes its files too.">
            {deleteFailed && <p className="info-note" role="alert"><Icon name="alert" size={16} />Could not delete {deleteFailed}.</p>}
            <JoinedFiles items={joined} onDelete={remove} />
          </Section>
        )}
        {shared && (
          <Section title="HR documents" count={shared.length}
            description="Shared with every employee and kept up to date by HR. SENSAI searches them for every answer; tick some to ask about them only.">
            <SharedDocuments items={shared} />
          </Section>
        )}
      </Page>
    </AppShell>
  );
}
