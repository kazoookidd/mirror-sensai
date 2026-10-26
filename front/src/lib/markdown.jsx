import styles from "./markdown.module.css";

const HEADING = /^#{1,6}\s+(.*)$/;
const BOLD_LINE = /^\*\*([^*]+)\*\*:?$/;
const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*(\d+)[.)]\s+(.*)$/;
const INLINE = /(\*\*[^*]+\*\*|`[^`]+`)/g;

function inline(text) {
  return text.split(INLINE).filter(Boolean).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) return <code key={index}>{part.slice(1, -1)}</code>;
    return part;
  });
}

function takeWhile(lines, start, pattern) {
  let end = start;
  while (end < lines.length && pattern.test(lines[end])) end += 1;
  return lines.slice(start, end);
}

function isParagraphLine(line) {
  return line.trim() && !HEADING.test(line) && !BULLET.test(line) && !NUMBERED.test(line);
}

function block(lines, index) {
  const line = lines[index];
  const heading = line.match(HEADING) || line.match(BOLD_LINE);
  if (heading) return [<p key={index} className={styles.heading}>{heading[1]}</p>, 1];

  if (BULLET.test(line)) {
    const items = takeWhile(lines, index, BULLET);
    return [
      <ul key={index} className={styles.list}>
        {items.map((item, i) => (
          <li key={i} className={styles.item}>
            <span className={styles.bullet} aria-hidden="true" />
            <span>{inline(item.match(BULLET)[1])}</span>
          </li>
        ))}
      </ul>,
      items.length,
    ];
  }

  if (NUMBERED.test(line)) {
    const items = takeWhile(lines, index, NUMBERED);
    return [
      <ol key={index} className={styles.list}>
        {items.map((item, i) => {
          const [, number, text] = item.match(NUMBERED);
          return (
            <li key={i} className={styles.item}>
              <span className={styles.number}>{number}.</span>
              <span>{inline(text)}</span>
            </li>
          );
        })}
      </ol>,
      items.length,
    ];
  }

  let next = index;
  while (next < lines.length && isParagraphLine(lines[next])) next += 1;
  const paragraph = lines.slice(index, next);
  return [
    <p key={index}>
      {paragraph.map((text, i) => (
        <span key={i}>{i > 0 && <br />}{inline(text)}</span>
      ))}
    </p>,
    paragraph.length,
  ];
}

export function Markdown({ text }) {
  const lines = text.replace(/\r/g, "").split("\n");
  const blocks = [];
  let index = 0;
  while (index < lines.length) {
    if (!lines[index].trim()) {
      index += 1;
      continue;
    }
    const [element, used] = block(lines, index);
    blocks.push(element);
    index += used;
  }
  return <div className={styles.prose}>{blocks}</div>;
}
