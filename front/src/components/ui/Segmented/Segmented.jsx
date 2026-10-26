import styles from "./Segmented.module.css";

export function Segmented({ label, options, value, onChange }) {
  return (
    <div className={styles.group} role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button key={option.value} className={styles.option} type="button" role="radio"
          aria-checked={option.value === value} onClick={() => onChange(option.value)}>
          {option.icon}{option.label}
        </button>
      ))}
    </div>
  );
}
