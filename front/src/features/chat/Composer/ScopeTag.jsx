import { Icon } from "../../../components/ui/Icon/Icon.jsx";
import { IconButton } from "../../../components/ui/IconButton/IconButton.jsx";
import { useApp } from "../../../context/AppContext.jsx";
import styles from "./Composer.module.css";

export function describeScope(scope) {
  return [...scope.sources, ...scope.types.map((type) => `.${type} files`)].join(", ");
}

export function ScopeTag() {
  const { documentScope, chooseScope } = useApp();
  if (!documentScope) return null;
  const scope = describeScope(documentScope);
  return (
    <div className={styles.attachments}>
      <span className={`${styles.attachment} ${styles.scope}`} title={`HR documents searched: ${scope}`}>
        <Icon name="search" size={16} display={14} />
        <span className="truncate">Searching only in {scope}</span>
        <IconButton icon="x" iconSize={16} iconDisplay={12} label="Search every HR document again" className={styles.scopeClear}
          onClick={() => chooseScope(null).catch(() => {})} />
      </span>
    </div>
  );
}
