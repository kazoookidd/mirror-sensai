import { useEffect } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { initials } from "../components/ui/Avatar/Avatar.jsx";
import { Brand } from "../components/ui/Brand/Brand.jsx";
import { Button } from "../components/ui/Button/Button.jsx";
import { Icon } from "../components/ui/Icon/Icon.jsx";
import { Dropdown } from "../components/ui/Dropdown/Dropdown.jsx";
import { ModelSelect } from "../features/ollama/ModelSelect/ModelSelect.jsx";
import { OllamaStatus } from "../features/ollama/OllamaStatus/OllamaStatus.jsx";
import { useApp } from "../context/AppContext.jsx";
import { cx } from "../lib/cx.js";
import { SECTIONS } from "./sections.js";
import styles from "./Sidebar.module.css";

const RECENT_COUNT = 12;

export function Sidebar() {
  const { user, conversations, refreshConversations, logout } = useApp();
  const location = useLocation();
  const navigate = useNavigate();
  const openAccount = (tab) => navigate(`/${tab}`, { state: { background: location } });
  const menu = [
    { heading: user.user_id },
    { label: "Profile", icon: <Icon name="users" size={16} />, onSelect: () => openAccount("profile") },
    { label: "Settings", icon: <Icon name="settings" size={16} />, onSelect: () => openAccount("settings") },
    "separator",
    { label: "Log out", danger: true, onSelect: logout },
  ];

  useEffect(() => {
    refreshConversations();
  }, [refreshConversations]);

  return (
    <aside className={styles.sidebar} aria-label="Sidebar">
      <div className={styles.header}>
        <Link to="/chat" aria-label="SENSAI, home"><Brand /></Link>
      </div>

      <div className={styles.block}>
        <Button variant="primary" block icon="plus" to="/chat">New chat</Button>
      </div>

      <nav className={styles.nav} aria-label="Main navigation">
        {SECTIONS.map((section) => (
          <NavLink key={section.id} to={section.to} className={styles.navItem}>
            <Icon name={section.icon} size={section.sidebarIcon} display={16} />{section.label}
          </NavLink>
        ))}
      </nav>

      <div className={styles.recent}>
        <p className={styles.recentLabel}>Recent</p>
        {conversations.length === 0 && <p className={styles.empty}>No chats yet.</p>}
        <ul className={styles.recentList}>
          {conversations.slice(0, RECENT_COUNT).map((conversation) => (
            <li key={conversation.id}>
              <NavLink to={`/chat/${conversation.id}`} className={styles.recentItem} title={conversation.title}>
                {conversation.title}
              </NavLink>
            </li>
          ))}
        </ul>
      </div>

      <div className={styles.footer}>
        <ModelSelect placement="top" block />
        <OllamaStatus className={styles.status} />
        <Dropdown block placement="top" items={menu} trigger={({ open, toggle }) => (
          <button type="button" className={cx(styles.account, open && styles.accountOpen)}
            aria-haspopup="listbox" aria-expanded={open} onClick={toggle}>
            <span className={styles.avatar} aria-hidden="true">{initials(user.user_id)}</span>
            <span className={cx(styles.accountName, "truncate")}>{user.user_id}</span>
            <Icon name="chevron-down" size={16} className={styles.chevron} />
          </button>
        )} />
      </div>
    </aside>
  );
}
