import { useEffect, useRef, useState } from "react";
import { Button } from "../../components/ui/Button/Button.jsx";
import { Checkbox } from "../../components/ui/Checkbox/Checkbox.jsx";
import { Field } from "../../components/ui/Field/Field.jsx";
import { useApp } from "../../context/AppContext.jsx";
import { auth } from "../../api/auth.js";
import styles from "./LoginPage.module.css";

// Same rules as check_new_account() in back/Memories/Auth.py, which checks them again.
const USER_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{2,39}$/;
const MIN_PASSWORD = 8;

function problem({ userId, email, password, confirm }) {
  if (!userId.trim() || !email.trim() || !password) return "Fill in every field.";
  if (!USER_ID.test(userId.trim()))
    return "The user id must be 3 to 40 characters: letters, digits, '.', '_' or '-'.";
  if (password.length < MIN_PASSWORD) return `The password must be at least ${MIN_PASSWORD} characters.`;
  if (password !== confirm) return "The two passwords are different.";
  return null;
}

// [M1] Signing up on the web creates an employee account; HR accounts are created in the CLI.
export function SignupForm({ onLogin }) {
  const { startSession } = useApp();
  const [values, setValues] = useState({ userId: "", email: "", password: "", confirm: "" });
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState(null);
  const [sending, setSending] = useState(false);
  const firstInput = useRef(null);

  useEffect(() => firstInput.current.focus(), []);

  const update = (key) => (event) => setValues((current) => ({ ...current, [key]: event.target.value }));

  const submit = async (event) => {
    event.preventDefault();
    const refused = problem(values);
    if (refused) {
      setError(refused);
      return;
    }
    setSending(true);
    try {
      await startSession(await auth.signup(values.userId.trim(), values.email.trim(), values.password, remember));
    } catch (failure) {
      setError([409, 422].includes(failure.status) ? failure.message : "The server is not responding. Try again in a moment.");
      setSending(false);
    }
  };

  return (
    <form className={styles.form} noValidate onSubmit={submit} aria-labelledby="signup-title">
      <div className={styles.intro}>
        <h1 id="signup-title" className={styles.title}>Create an account</h1>
        <p className={styles.subtitle}>An employee account, to ask your HR questions.</p>
      </div>
      <div className={styles.fields}>
        <Field ref={firstInput} label="User id" id="signup-user" leading={["users", 16]} className={styles.input}
          autoComplete="username" placeholder="camille.martin" value={values.userId} onChange={update("userId")} />
        <Field label="Email address" id="signup-email" leading={["mail", 20, 16]} className={styles.input}
          inputMode="email" autoComplete="email" placeholder="camille.martin@enterprise.com"
          value={values.email} onChange={update("email")} />
        <Field label="Password" id="signup-password" type="password" reveal leading={["lock", 16]} className={styles.input}
          autoComplete="new-password" placeholder={`At least ${MIN_PASSWORD} characters`}
          value={values.password} onChange={update("password")} />
        <Field label="Confirm the password" id="signup-confirm" type="password" leading={["lock", 16]}
          className={styles.input} autoComplete="new-password" placeholder="Password"
          value={values.confirm} onChange={update("confirm")} />
        <label className={styles.remember}>
          <Checkbox checked={remember} onChange={(event) => setRemember(event.target.checked)} />
          Stay logged in on this device
        </label>
      </div>
      {error && (
        <p className={styles.alert} role="alert">
          <span className={styles.alertDot} aria-hidden="true" />
          {error}
        </p>
      )}
      <Button variant="primary" large block type="submit" disabled={sending} aria-busy={sending} className={styles.submit}>
        {sending ? "Creating the account..." : "Create my account"}
      </Button>
      <p className={styles.help}>
        HR accounts are created by the HR team in the terminal.{" "}
        <button type="button" className={styles.switch} onClick={onLogin}>I already have an account</button>
      </p>
    </form>
  );
}
