import { useEffect, useState } from "react";
import { shares } from "../../api/shares.js";
import { ErrorBanner } from "../../components/feedback/ErrorBanner/ErrorBanner.jsx";
import { Button } from "../../components/ui/Button/Button.jsx";
import { Dialog } from "../../components/ui/Dialog/Dialog.jsx";
import { InputBox } from "../../components/ui/Field/Field.jsx";
import { formatDate, parseUtc } from "../../lib/format.js";
import styles from "./ShareDialog.module.css";

const COPIED_MS = 1500;

export function shareUrl(token) {
  return `${window.location.origin}${window.location.pathname}#/share/${token}`;
}

export function ShareDialog({ conversationId, onClose }) {
  const [share, setShare] = useState(undefined);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    shares.get(conversationId).then((data) => setShare(data.share), (failure) => setError(failure.message));
  }, [conversationId]);

  useEffect(() => {
    if (!copied) return undefined;
    const timer = setTimeout(() => setCopied(false), COPIED_MS);
    return () => clearTimeout(timer);
  }, [copied]);

  const run = async (action) => {
    setWorking(true);
    setError("");
    try {
      setShare((await action(conversationId)).share);
    } catch (failure) {
      setError(failure.message);
    } finally {
      setWorking(false);
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl(share.token));
      setCopied(true);
    } catch {
      // Clipboard refused (insecure context): the link stays selectable in the field.
    }
  };

  return (
    <Dialog title="Share this chat" onClose={onClose} className={styles.panel}>
      <div className={styles.body}>
        <header className={styles.header}>
          <h2 className="text-heading">Share this chat</h2>
          <p className={styles.text}>
            Anyone with the link can read this version of the chat, without logging in. The link shows the chat as it is
            when you create it: later messages are not added. It expires after 7 days.
          </p>
        </header>
        {error && <ErrorBanner title="Sharing failed">{error}</ErrorBanner>}
        {share && (
          <>
            <div className={styles.link}>
              <InputBox small mono readOnly value={shareUrl(share.token)} aria-label="Public link" className={styles.url}
                onFocus={(event) => event.target.select()} />
              <Button variant="primary" icon={copied ? "check" : "copy"} iconSize={copied ? 14 : 16} onClick={copy}>
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
            <p className={styles.note}>Expires on {formatDate(parseUtc(share.expires_at))}.</p>
          </>
        )}
        {share
          ? (
            <footer className={styles.stopRow}>
              <Button variant="ghost" className={styles.stop} disabled={working} onClick={() => run(shares.remove)}>Stop sharing</Button>
            </footer>
          )
          : (
            <footer className={styles.footer}>
              <Button variant="primary" icon="link" disabled={working || share === undefined} onClick={() => run(shares.create)}>
                Create link
              </Button>
            </footer>
          )}
      </div>
    </Dialog>
  );
}
