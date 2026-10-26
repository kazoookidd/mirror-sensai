import { useEffect, useRef, useState } from "react";
import { InputBox } from "../../components/ui/Field/Field.jsx";

export function EditableTitle({ title, editing, onDone, className, as: Tag = "p", ...props }) {
  const [value, setValue] = useState(title);
  const input = useRef(null);
  const finished = useRef(false);

  useEffect(() => {
    if (!editing) return;
    finished.current = false;
    setValue(title);
    input.current.focus();
    input.current.select();
  }, [editing, title]);

  const finish = (save) => {
    if (finished.current) return;  // leaving the field after Enter must not save twice
    finished.current = true;
    const next = value.trim();
    onDone(save && next && next !== title ? next : null);
  };

  if (!editing) return <Tag className={className} {...props}>{title}</Tag>;
  return (
    <InputBox ref={input} small value={value} maxLength={120} aria-label="New title"
      onClick={(event) => event.stopPropagation()}
      onChange={(event) => setValue(event.target.value)}
      onBlur={() => finish(true)}
      onKeyDown={(event) => {
        if (event.key === "Enter") finish(true);
        if (event.key === "Escape") finish(false);
      }} />
  );
}
