import { forwardRef, useImperativeHandle, useLayoutEffect, useRef, useState } from "react";
import { CommandMenu } from "../CommandMenu/CommandMenu.jsx";
import { matchCommands } from "../CommandMenu/commands.js";
import { useApp } from "../../../context/AppContext.jsx";
import { cx } from "../../../lib/cx.js";
import { Icon } from "../../../components/ui/Icon/Icon.jsx";
import { IconButton } from "../../../components/ui/IconButton/IconButton.jsx";
import { ACCEPTED } from "../../documents/useImport.js";
import { Attachments } from "./Attachments.jsx";
import { ContextGauge } from "./ContextGauge.jsx";
import styles from "./Composer.module.css";

const PLACEHOLDER = "Ask SENSAI a question...";
const OFFLINE_PLACEHOLDER = "Connect Ollama to send a message";

export const Composer = forwardRef(function Composer({ onSend, onStop, busy, attachments = [], attaching = {}, onAttach, className }, ref) {
  const { ollama } = useApp();
  const [text, setText] = useState("");
  const [highlighted, setHighlighted] = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const input = useRef(null);
  const picker = useRef(null);
  const offline = !ollama.online;
  const commands = dismissed || busy ? [] : matchCommands(text);

  useImperativeHandle(ref, () => ({
    fill(value) {
      change(value);
      input.current.focus();
    },
    focus() {
      input.current?.focus({ preventScroll: true });
    },
  }), []);

  useLayoutEffect(() => {
    input.current.style.height = "auto";
    input.current.style.height = `${input.current.scrollHeight}px`;
  }, [text]);

  const change = (value) => {
    setText(value);
    setHighlighted(0);
    setDismissed(false);
  };

  const submit = (value = text) => {
    const message = value.trim();
    if (!message || busy || offline) return;
    change("");
    onSend(message);
  };

  const choose = (command, complete = false) => {
    if (command.args || complete) change(`${command.name} `);
    else submit(command.name);
    input.current.focus();
  };

  const onMenuKey = (event) => {
    const keys = {
      ArrowDown: () => setHighlighted((index) => (index + 1) % commands.length),
      ArrowUp: () => setHighlighted((index) => (index - 1 + commands.length) % commands.length),
      Enter: () => choose(commands[highlighted]),
      Tab: () => choose(commands[highlighted], true),
      Escape: () => setDismissed(true),
    };
    if (!keys[event.key] || (event.key === "Enter" && event.shiftKey)) return false;
    event.preventDefault();
    keys[event.key]();
    return true;
  };

  return (
    <div className={cx(styles.composer, offline && styles.disabled, !offline && text.trim() && styles.typing, className)}>
      {commands.length > 0 && (
        <CommandMenu commands={commands} highlighted={highlighted} onChoose={choose} onHighlight={setHighlighted} />
      )}
      <Attachments attachments={attachments} attaching={attaching} />
      <textarea
        ref={input}
        className={styles.input}
        rows={1}
        value={text}
        disabled={offline}
        placeholder={offline ? OFFLINE_PLACEHOLDER : PLACEHOLDER}
        aria-label="Message"
        onChange={(event) => change(event.target.value)}
        onKeyDown={(event) => {
          if (commands.length && onMenuKey(event)) return;
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            submit();
          }
        }}
      />
      <div className={styles.footer}>
        <div className={styles.tools}>
          <IconButton icon="paperclip" label="Attach a file to this chat" disabled={offline || Boolean(attaching.name)}
            onClick={() => picker.current.click()} />
          <input ref={picker} type="file" accept={ACCEPTED} multiple hidden aria-label="Choose files to attach"
            onChange={(event) => { onAttach([...event.target.files]); event.target.value = ""; }} />
          <button className={styles.knowledge} type="button" disabled aria-pressed="false" data-test-corner=""
            title="[TEST] Turn the HR documents on or off: not available yet (they are always searched)">
            <Icon name="database" size={16} /><span className="truncate">HR documents</span>
          </button>
        </div>
        <ContextGauge />
        {busy
          ? <IconButton icon="stop" label="Stop generating" variant="outline" onClick={onStop} />
          : <IconButton icon="arrow-up" label="Send" variant="primary" disabled={offline || !text.trim()} onClick={() => submit()} />}
      </div>
    </div>
  );
});
