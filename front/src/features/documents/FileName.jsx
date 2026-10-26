import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { fileType } from "../../lib/format.js";
import styles from "./FileName.module.css";

export function FileName({ source, meta, iconSize }) {
  return (
    <span className={styles.name}>
      <span className={styles.icon} data-size={iconSize} aria-hidden="true">
        <Icon name={fileType(source) === "TXT" ? "file" : "file-text"} size={iconSize} />
      </span>
      <span className={styles.text}>
        <span className={styles.title} title={source}>{source}</span>
        <span className={styles.meta}>{meta}</span>
      </span>
    </span>
  );
}
