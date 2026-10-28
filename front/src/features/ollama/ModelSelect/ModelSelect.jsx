import { useApp } from "../../../context/AppContext.jsx";
import { Dot } from "../../../components/ui/Badge/Badge.jsx";
import { Icon } from "../../../components/ui/Icon/Icon.jsx";
import { Select } from "../../../components/ui/Select/Select.jsx";

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

  return (
    <Select label="Active model" value={model || "Model"} items={items} variant={variant} align={align}
      placement={placement} block={block} attention={!modelInstalled}
      leading={variant === "chip" ? <Dot tone={ollama.online ? "success" : "error"} /> : <Icon name="cpu" size={16} />}
      onOpen={() => !models.length && ollama.online && refreshModels()} />
  );
}
