import { Link, NavLink } from "react-router-dom";
import { Brand } from "../components/ui/Brand/Brand.jsx";
import { Icon } from "../components/ui/Icon/Icon.jsx";
import { IconButton } from "../components/ui/IconButton/IconButton.jsx";
import { ModelSelect } from "../features/ollama/ModelSelect/ModelSelect.jsx";
import { SECTIONS } from "./sections.js";
import styles from "./MobileBars.module.css";

export function RootAppBar() {
  return (
    <header className={styles.appBar}>
      <Link to="/chat" aria-label="SENSAI, home"><Brand /></Link>
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
  return (
    <nav className={styles.tabBar} aria-label="Main navigation">
      {SECTIONS.map((section) => (
        <NavLink key={section.id} to={section.to} className={styles.tab}>
          <Icon name={section.icon} size={22} />
          {section.label}
        </NavLink>
      ))}
    </nav>
  );
}
