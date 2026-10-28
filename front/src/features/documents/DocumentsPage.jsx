import { useEffect, useState } from "react";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { AppShell } from "../../layout/AppShell.jsx";
import { Page, PageHeader } from "../../layout/Page.jsx";
import { documents as documentsApi } from "../../api/documents.js";
import { ImportButton, QueryButton } from "./DocumentButtons.jsx";
import { DropZone, EmptyBase } from "./DropZone.jsx";
import { FileCards } from "./FileCards.jsx";
import { FileTable } from "./FileTable.jsx";
import styles from "./DocumentsPage.module.css";

export function DocumentsPage() {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [selection, setSelection] = useState(() => new Set());

  useEffect(() => {
    documentsApi.list().then(setData).catch(() => setFailed(true));
  }, []);

  const toggle = (source) => setSelection((current) => {
    const next = new Set(current);
    if (next.has(source)) next.delete(source);
    else next.add(source);
    return next;
  });
  const toggleAll = () => setSelection((current) => (
    current.size === data.documents.length ? new Set() : new Set(data.documents.map((item) => item.source))));

  const items = data?.documents ?? [];
  return (
    <AppShell nav={{ active: "documents", mobile: "root", tabs: true }} scroll>
      <Page>
        <PageHeader title="Knowledge base"
          subtitle="Import HR documents to enrich the answers of SENSAI."
          mobileSubtitle="Import HR documents to enrich the answers."
          actions={<>
            {selection.size > 0 && <span className="desktop-only"><QueryButton label={`Ask about the selection · ${selection.size}`} /></span>}
            <ImportButton className="desktop-only" />
          </>} />
        <ImportButton className="mobile-only" />
        {failed && <p className="info-note"><Icon name="alert" size={16} />Could not read the knowledge base.</p>}
        {data && !items.length && <EmptyBase />}
        {items.length > 0 && <>
          <DropZone />
          <div className={`${styles.listHeader} desktop-only`}>
            <div className={styles.listTitle}>
              <h2 className="text-heading">Imported documents</h2>
              <span className="text-caption text-secondary">{items.length}</span>
            </div>
            <p className={styles.info}><Icon name="database" size={14} />Chunking and embeddings run locally with {data.embed_model}</p>
          </div>
          <FileTable items={items} selection={selection} onToggle={toggle} onToggleAll={toggleAll} />
          <FileCards items={items} selection={selection} onToggle={toggle} />
        </>}
      </Page>
    </AppShell>
  );
}
