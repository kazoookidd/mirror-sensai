import { useEffect, useRef, useState } from "react";
import { Brand } from "../../components/ui/Brand/Brand.jsx";
import { Button } from "../../components/ui/Button/Button.jsx";
import { Checkbox } from "../../components/ui/Checkbox/Checkbox.jsx";
import { Field } from "../../components/ui/Field/Field.jsx";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { OllamaStatus } from "../ollama/OllamaStatus/OllamaStatus.jsx";
import { useApp } from "../../context/AppContext.jsx";
import { cx } from "../../lib/cx.js";
import { auth } from "../../api/auth.js";
import { ThemeToggle } from "./ThemeToggle.jsx";
import styles from "./LoginPage.module.css";

const TOPICS = [
  { name: "Leave", detail: "Paid leave, family events, public holidays" },
  { name: "Remote work", detail: "What the company agreement allows" },
  { name: "Onboarding", detail: "The first days of a new employee" },
];

export function LoginPage() {
  const { startSession } = useApp();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState(null);
  const [sending, setSending] = useState(false);
  const emailInput = useRef(null);
  const passwordInput = useRef(null);

  useEffect(() => emailInput.current.focus(), []);

  const submit = async (event) => {
    event.preventDefault();
    if (!email.trim() || !password) {
      setError({ message: "Enter your email address and your password." });
      return;
    }
    setSending(true);
    try {
      await startSession(await auth.login(email.trim(), password, remember));
    } catch (failure) {
      const wrong = failure.status === 401;
      setError({ message: wrong ? failure.message : "The server is not responding. Try again in a moment.", password: wrong });
      passwordInput.current.focus();
      setSending(false);
    }
  };

  return (
    <div className={styles.login}>
      <aside className={cx(styles.panel, "theme-dark")}>
        <div className={styles.panelTop}>
          <span className={styles.brand}><Brand /></span>
          <ThemeToggle className={styles.toggleNarrow} />
        </div>
        <div className={styles.pitch}>
          <p className={styles.headline}>Your HR questions,<br />answered from your own documents.</p>
          <p className={styles.lead}>
            SENSAI reads the company agreements and policies, and runs entirely on this machine.
          </p>
        </div>
        <ul className={styles.topics}>
          {TOPICS.map((topic) => (
            <li key={topic.name} className={styles.topic}>
              <span className={styles.topicName}>{topic.name}</span>
              <span className={styles.topicDetail}>{topic.detail}</span>
            </li>
          ))}
        </ul>
      </aside>

      <main className={styles.formPanel}>
        <ThemeToggle className={styles.toggleWide} />
        <form className={styles.form} noValidate onSubmit={submit} aria-labelledby="login-title">
          <div className={styles.intro}>
            <h1 id="login-title" className={styles.title}>Log in</h1>
            <p className={styles.subtitle}>Use the account created by your HR team.</p>
          </div>
          <div className={styles.fields}>
            <Field ref={emailInput} label="Email address" id="login-email" leading={["mail", 20, 16]} className={styles.input}
              inputMode="email" autoComplete="username" placeholder="test@enterprise.com"
              value={email} onChange={(event) => setEmail(event.target.value)} />
            <Field ref={passwordInput} label="Password" id="login-password" type="password" reveal leading={["lock", 16]}
              className={styles.input} autoComplete="current-password" placeholder="Password"
              value={password} onChange={(event) => setPassword(event.target.value)}
              error={error?.password} help={error?.password ? "Check upper and lower case, then try again." : null} />
            <label className={styles.remember}>
              <Checkbox checked={remember} onChange={(event) => setRemember(event.target.checked)} />
              Stay logged in on this device
            </label>
          </div>
          {error && (
            <p className={styles.alert} role="alert">
              <span className={styles.alertDot} aria-hidden="true" />
              {error.message}
            </p>
          )}
          <Button variant="primary" large block type="submit" disabled={sending} aria-busy={sending} className={styles.submit}>
            {sending ? "Logging in..." : "Log in"}
          </Button>
          <p className={styles.help}>Forgot your password? Contact the HR team to reset it.</p>
        </form>
        <footer className={styles.footer}>
          <OllamaStatus online="Ollama connected" offline="Ollama offline" />
          <span className={styles.footerNote}><Icon name="cpu" size={14} />HR data stays on this machine</span>
        </footer>
      </main>
    </div>
  );
}
