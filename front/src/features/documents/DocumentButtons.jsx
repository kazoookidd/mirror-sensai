import { Button } from "../../components/ui/Button/Button.jsx";
import { Dropdown } from "../../components/ui/Dropdown/Dropdown.jsx";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { IconButton } from "../../components/ui/IconButton/IconButton.jsx";

export function ImportButton({ importing, onClick, className }) {
  return (
    <Button variant="primary" icon="upload" disabled={Boolean(importing)} onClick={onClick} className={className}>
      {importing ? "Importing..." : "Import a document"}
    </Button>
  );
}

export function QueryButton({ label, onClick }) {
  return <Button icon="message" onClick={onClick} title="Ask SENSAI in a new chat, searching only these documents">{label}</Button>;
}

export function DocumentMenu({ item, view, actions }) {
  const menu = [
    { label: "Rename", icon: <Icon name="pencil" size={16} />, onSelect: () => actions.startRename(item, view) },
    { label: "Delete", icon: <Icon name="trash" size={16} />, danger: true, onSelect: () => actions.remove(item) },
  ];
  return (
    <Dropdown floating compact align="right" items={menu} trigger={({ open, toggle }) => (
      <IconButton icon="ellipsis" label={`Options for ${item.source}`} aria-haspopup="listbox" aria-expanded={open} onClick={toggle} />
    )} />
  );
}
