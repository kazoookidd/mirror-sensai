import { cx } from "../lib/cx.js";
import styles from "./Page.module.css";

export function Page({ width = "wide", children }) {
  return <div className={cx(styles.page, styles[width])}>{children}</div>;
}

export function PageHeader({ title, subtitle, mobileSubtitle, subtitleDesktopOnly, actions, titleExtra, hideTitleOnMobile }) {
  return (
    <header className={styles.header}>
      <div className={styles.title}>
        <div className={styles.titleLine}>
          <h1 className={cx("text-display", hideTitleOnMobile && "desktop-only")}>{title}</h1>
          {titleExtra}
        </div>
        {subtitle && (
          <p className={cx(styles.subtitle, subtitleDesktopOnly && "desktop-only")}>
            <span className={mobileSubtitle ? "desktop-only" : undefined}>{subtitle}</span>
            {mobileSubtitle && <span className="mobile-only">{mobileSubtitle}</span>}
          </p>
        )}
      </div>
      {actions && <div className={styles.actions}>{actions}</div>}
    </header>
  );
}
