import { Link, NavLink } from "react-router-dom";
import { RoleBadge } from "../components/ui/Badge/Badge.jsx";
import { Brand } from "../components/ui/Brand/Brand.jsx";
import { Icon } from "../components/ui/Icon/Icon.jsx";
import { IconButton } from "../components/ui/IconButton/IconButton.jsx";
import { ModelSelect } from "../features/ollama/ModelSelect/ModelSelect.jsx";
import { useApp } from "../context/AppContext.jsx";
import { isHr, sectionsFor } from "./sections.js";
import styles from "./MobileBars.module.css";

export function RootAppBar() {
  const { user } = useApp();
  return (
    <header className={styles.appBar}>
      <div className={styles.left}>
        <Link to="/chat" aria-label="SENSAI, home"><Brand /></Link>
        {isHr(user) && <RoleBadge />}
      </div>
      <div className={styles.right}>
        <ModelSelect variant="chip" align="right" />
        <IconButton icon="settings" label="Settings" to="/settings" />
      </div>
    </header>
  );
}

export function BackAppBar({ title, back, actions }) {
  return (
    <header className={`${styles.appBar} ${styles.back}`}>
      <div className={styles.left}>
        <IconButton icon="chevron-left" label="Back" to={back} />
        <h1 className={`${styles.title} text-heading truncate`}>{title}</h1>
      </div>
      {actions}
    </header>
  );
}

export function TabBar() {
  const { user } = useApp();
  return (
    <nav className={styles.tabBar} aria-label="Main navigation">
      {sectionsFor(user).map((section) => (
        <NavLink key={section.id} to={section.to} className={styles.tab}>
          <Icon name={section.icon} size={22} />
          {section.shortLabel ?? section.label}
        </NavLink>
      ))}
    </nav>
  );
}
