import { useCallback, useEffect, useState } from "react";
import { ErrorBanner } from "../../components/feedback/ErrorBanner/ErrorBanner.jsx";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { AppShell } from "../../layout/AppShell.jsx";
import { Page, PageHeader } from "../../layout/Page.jsx";
import { documents as documentsApi } from "../../api/documents.js";
import { ImportButton, QueryButton } from "./DocumentButtons.jsx";
import { DropZone, EmptyBase } from "./DropZone.jsx";
import { FileCards } from "./FileCards.jsx";
import { FileTable } from "./FileTable.jsx";
import { useAskSelection } from "./useAskSelection.js";
import { useImport } from "./useImport.js";
import styles from "./DocumentsPage.module.css";

function ImportResults({ results }) {
  return results.map((result) => (result.ok
    ? <p key={result.name} className="info-note" role="status"><Icon name="check" size={14} />{result.name} imported: {result.chunks} {result.chunks === 1 ? "chunk" : "chunks"} indexed.</p>
    : <ErrorBanner key={result.name} title={`${result.name} was not imported`}>{result.error}</ErrorBanner>));
}

export function DocumentsPage() {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [selection, setSelection] = useState(() => new Set());
  const askSelection = useAskSelection();
  const [askError, setAskError] = useState(null);
  const ask = () => askSelection(selection).catch((error) => setAskError(error.message));

  const refresh = useCallback(() => {
    documentsApi.list().then((next) => { setData(next); setFailed(false); }).catch(() => setFailed(true));
  }, []);
  const upload = useImport(refresh);
  const [renaming, setRenaming] = useState(null);
  const [actionError, setActionError] = useState(null);

  const forget = (source) => setSelection((current) => {
    const next = new Set(current);
    next.delete(source);
    return next;
  });
  const run = async (source, work) => {
    setActionError(null);
    try {
      await work();
      forget(source);
    } catch (error) {
      setActionError({ source, message: error.message });
    }
    refresh();
  };
  const actions = {
    renaming,
    startRename: (item, view) => setRenaming(`${view}:${item.source}`),
    rename: (item, name) => {
      setRenaming(null);
      if (name)
        run(item.source, () => documentsApi.rename(item.source, name));
    },
    remove: (item) => {
      if (!window.confirm(`Delete "${item.source}" from the knowledge base? SENSAI will no longer answer from it.`))
        return;
      run(item.source, () => documentsApi.remove(item.source));
    },
  };
  const zone = { importing: upload.importing, onPick: upload.open, onDrop: upload.importFiles };

  useEffect(refresh, [refresh]);

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
            {selection.size > 0 && <span className="desktop-only"><QueryButton label={`Ask about the selection · ${selection.size}`} onClick={ask} /></span>}
            <ImportButton className="desktop-only" importing={upload.importing} onClick={upload.open} />
          </>} />
        <ImportButton className="mobile-only" importing={upload.importing} onClick={upload.open} />
        <input {...upload.inputProps} aria-label="Choose documents to import" />
        <ImportResults results={upload.results} />
        {askError && <ErrorBanner title="The selection could not be searched">{askError}</ErrorBanner>}
        {actionError && <ErrorBanner title={`${actionError.source} was not changed`}>{actionError.message}</ErrorBanner>}
        {failed && <p className="info-note"><Icon name="alert" size={16} />Could not read the knowledge base.</p>}
        {data && !items.length && <EmptyBase {...zone} />}
        {items.length > 0 && <>
          <DropZone {...zone} />
          <div className={`${styles.listHeader} desktop-only`}>
            <div className={styles.listTitle}>
              <h2 className="text-heading">Imported documents</h2>
              <span className="text-caption text-secondary">{items.length}</span>
            </div>
            <p className={styles.info}><Icon name="database" size={14} />Chunking and embeddings run locally with {data.embed_model}</p>
          </div>
          <FileTable items={items} selection={selection} onToggle={toggle} onToggleAll={toggleAll} actions={actions} />
          <FileCards items={items} selection={selection} onToggle={toggle} actions={actions} onAsk={ask} />
        </>}
      </Page>
    </AppShell>
  );
}
