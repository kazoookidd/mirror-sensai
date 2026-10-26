import { useApp } from "../../../context/AppContext.jsx";
import { cx } from "../../../lib/cx.js";
import { Dot } from "../../../components/ui/Badge/Badge.jsx";
import { Dropdown } from "../../../components/ui/Dropdown/Dropdown.jsx";
import { Icon } from "../../../components/ui/Icon/Icon.jsx";
import styles from "./ModelSelect.module.css";

function plural(count) {
  return count > 1 ? "s" : "";
}

export function useModelItems(onChosen) {
  const { models, model, chooseModel } = useApp();
  const chat = models.filter((item) => !item.embedding);
  return [
    ...chat.map((item) => ({
      label: item.name,
      icon: <Icon name="cpu" size={14} />,
      selected: item.name === model,
      meta: item.name === model ? <Icon name="check" size={14} /> : null,
      onSelect: async () => {
        await chooseModel(item.name);
        onChosen?.(item.name);
      },
    })),
    ...(chat.length ? ["separator"] : []),
    { footer: chat.length ? `${chat.length} model${plural(chat.length)} installed locally` : "No model installed" },
  ];
}

export function ModelSelect({ variant = "sm", align = "left", placement, block }) {
  const { model, modelInstalled, ollama, models, refreshModels } = useApp();
  const items = useModelItems();
  const chip = variant === "chip";

  return (
    <Dropdown align={align} placement={placement} block={block} items={items} trigger={({ open, toggle }) => (
      <button
        type="button"
        className={cx(styles.select, styles[variant], block && styles.block, (open || !modelInstalled) && styles.attention)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="Active model"
        onClick={async () => {
          if (!models.length && ollama.online) await refreshModels();
          toggle();
        }}
      >
        <span className={styles.value}>
          {chip ? <Dot tone={ollama.online ? "success" : "error"} /> : <Icon name="cpu" size={16} />}
          <span className="truncate">{model || "Model"}</span>
        </span>
        <Icon name="chevron-down" size={chip ? 14 : 16} />
      </button>
    )} />
  );
}
