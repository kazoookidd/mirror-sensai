import { useEffect, useRef, useState } from "react";
import { Brand } from "../../components/ui/Brand/Brand.jsx";
import { Button } from "../../components/ui/Button/Button.jsx";
import { Checkbox } from "../../components/ui/Checkbox/Checkbox.jsx";
import { Field } from "../../components/ui/Field/Field.jsx";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { OllamaStatus } from "../ollama/OllamaStatus/OllamaStatus.jsx";
import { useApp } from "../../context/AppContext.jsx";
import { auth } from "./api.js";
import styles from "./LoginPage.module.css";

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
      <header className={styles.header}>
        <Brand />
        <OllamaStatus online="Ollama connected" offline="Ollama offline" />
      </header>
      <main className={styles.main}>
        <section className={styles.card} aria-labelledby="login-title">
          <form className={styles.form} noValidate onSubmit={submit}>
            <div className={styles.intro}>
              <p className={styles.eyebrow}>{"< hr assistant />"}</p>
              <h1 id="login-title" className="text-display">Log in</h1>
              <p className="text-body text-secondary">Log in with the account created by your HR team.</p>
            </div>
            {error && (
              <div className={styles.alert} role="alert">
                <Icon name="alert" size={16} className={styles.alertIcon} />
                <p>{error.message}</p>
              </div>
            )}
            <div className={styles.fields}>
              <Field ref={emailInput} label="Email address" id="login-email" leading={["mail", 20, 16]}
                inputMode="email" autoComplete="username" placeholder="camille.martin@entreprise.fr"
                value={email} onChange={(event) => setEmail(event.target.value)} />
              <Field ref={passwordInput} label="Password" id="login-password" type="password" reveal
                leading={["lock", 16]} autoComplete="current-password" value={password}
                onChange={(event) => setPassword(event.target.value)} error={error?.password}
                help={error?.password ? "Check upper and lower case, then try again." : null} />
              <label className={styles.remember}>
                <Checkbox checked={remember} onChange={(event) => setRemember(event.target.checked)} />
                Stay logged in on this device
              </label>
            </div>
            <Button variant="primary" large block icon="log-in" type="submit" disabled={sending}>Log in</Button>
            <p className={styles.help}>
              Forgot your password? <strong>Contact the HR team</strong> to reset it.
            </p>
          </form>
        </section>
      </main>
      <footer className={styles.footer}>
        <p className="privacy-note"><Icon name="cpu" size={14} />Local model · HR data stays on your machine</p>
      </footer>
    </div>
  );
}
