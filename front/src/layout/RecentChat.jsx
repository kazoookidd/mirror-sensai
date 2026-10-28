import { useState } from "react";
import { NavLink } from "react-router-dom";
import { Dropdown } from "../components/ui/Dropdown/Dropdown.jsx";
import { Icon } from "../components/ui/Icon/Icon.jsx";
import { IconButton } from "../components/ui/IconButton/IconButton.jsx";
import { EditableTitle } from "../features/history/EditableTitle.jsx";
import { cx } from "../lib/cx.js";
import styles from "./RecentChat.module.css";

export function RecentChat({ conversation, actions }) {
  const [renaming, setRenaming] = useState(false);
  const menu = [
    { label: "Rename", icon: <Icon name="pencil" size={16} />, onSelect: () => setRenaming(true) },
    { label: "Delete", icon: <Icon name="trash" size={16} />, danger: true, onSelect: () => actions.remove(conversation) },
  ];

  if (renaming) {
    return (
      <li className={styles.item}>
        <EditableTitle title={conversation.title} editing onDone={(title) => {
          setRenaming(false);
          if (title) actions.rename(conversation, title);
        }} />
      </li>
    );
  }
  return (
    <li className={styles.item}>
      <NavLink to={`/chat/${conversation.id}`} className={styles.link} title={conversation.title}>
        {conversation.title}
      </NavLink>
      <Dropdown floating compact align="right" items={menu} className={styles.more} trigger={({ open, toggle }) => (
        <IconButton icon="ellipsis" label={`Options for ${conversation.title}`} aria-haspopup="listbox"
          aria-expanded={open} className={cx(styles.trigger, open && styles.open)} onClick={toggle} />
      )} />
    </li>
  );
}
