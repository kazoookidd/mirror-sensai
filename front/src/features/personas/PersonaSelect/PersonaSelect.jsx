import { useApp } from "../../../context/AppContext.jsx";
import { Icon } from "../../../components/ui/Icon/Icon.jsx";
import { Select } from "../../../components/ui/Select/Select.jsx";

export function PersonaSelect({ variant = "sm", align = "left", placement, block }) {
  const { personas, persona, choosePersona } = useApp();
  const current = personas.find((item) => item.id === persona);
  const items = [
    ...personas.map((item) => ({
      label: item.name,
      hint: item.description,
      icon: <Icon name="users" size={16} display={14} />,
      selected: item.id === persona,
      meta: item.id === persona ? <Icon name="check" size={14} /> : null,
      onSelect: () => choosePersona(item.id),
    })),
    "separator",
    { footer: "The chat history is kept when you switch" },
  ];

  return (
    <Select label="Active persona" value={current?.name ?? "Persona"} items={items} variant={variant}
      align={align} placement={placement} block={block} leading={<Icon name="users" size={16} />} />
  );
}
