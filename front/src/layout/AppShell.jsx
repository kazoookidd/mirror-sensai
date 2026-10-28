import { cx } from "../lib/cx.js";
import { BackAppBar, RootAppBar, TabBar } from "./MobileBars.jsx";
import { Sidebar } from "./Sidebar.jsx";
import { useSlideDirection, useTabSwipe } from "./useSlide.js";
import styles from "./AppShell.module.css";

export function AppShell({ nav, scroll, children }) {
  const direction = useSlideDirection(nav.active);
  const swipe = useTabSwipe(nav.active, nav.tabs);

  return (
    <div className={styles.app}>
      <div className={styles.wide}><Sidebar /></div>
      <div className={styles.column}>
        <div className={styles.narrow}>
          {nav.mobile === "back" ? <BackAppBar title={nav.title} back={nav.back} actions={nav.actions} /> : <RootAppBar />}
        </div>
        <main className={cx(styles.main, scroll && styles.scroll, styles[direction])} {...swipe}>{children}</main>
        {nav.tabs && <div className={styles.narrow}><TabBar /></div>}
      </div>
    </div>
  );
}
