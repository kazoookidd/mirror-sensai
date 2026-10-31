import { Icon } from "../../../components/ui/Icon/Icon.jsx";
import styles from "./Messages.module.css";

export function MessageSources({ sources }) {
  return (
    <ol className={styles.sources} aria-label="Sources of the answer">
      {sources.map((source, index) => (
        <li key={index} className={styles.source}>
          <div className={styles.sourceHeader}>
            <Icon name="file-text" size={14} />
            <span className={`${styles.sourceName} truncate`} title={source.source}>
              {source.source}{source.page != null && `, p. ${source.page}`}
            </span>
            <span className={styles.sourceScore}
              title={`Relevance ${source.score.toFixed(2)}: meaning ${source.semantic.toFixed(2)}, keywords ${source.keyword.toFixed(2)}`}>
              {Math.round(source.score * 100)} %
            </span>
          </div>
          <p className={styles.sourceExcerpt}>{source.excerpt}</p>
        </li>
      ))}
    </ol>
  );
}
