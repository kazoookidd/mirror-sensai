import { useState } from "react";
import { Button } from "../../../components/ui/Button/Button.jsx";
import { Icon } from "../../../components/ui/Icon/Icon.jsx";
import styles from "./Messages.module.css";

// [X4] A question from the assistant: one click on a choice, or a free answer. The answer is sent as
// the user's next message.
function QuestionForm({ field, busy, onAnswer }) {
  const [text, setText] = useState("");
  const send = (event) => {
    event.preventDefault();
    if (text.trim()) onAnswer(text.trim());
  };
  return (
    <>
      {field.options.length > 0 && (
        <div className={styles.formOptions}>
          {field.options.map((option) => (
            <Button key={option.value} disabled={busy} onClick={() => onAnswer(option.label)}>{option.label}</Button>
          ))}
        </div>
      )}
      <form className={styles.formFree} onSubmit={send}>
        <input className={styles.formControl} aria-label="Your answer" disabled={busy} value={text}
          placeholder={field.options.length ? "Or answer in your own words" : "Your answer"}
          onChange={(event) => setText(event.target.value)} />
        <Button type="submit" variant="primary" disabled={busy || !text.trim()}>Send</Button>
      </form>
    </>
  );
}

function Control({ field, value, disabled, onChange }) {
  const common = { id: `form-${field.name}`, className: styles.formControl, disabled, value,
    "aria-invalid": Boolean(field.error) || undefined, onChange: (event) => onChange(event.target.value) };
  if (field.kind === "choice") {
    return (
      <select {...common}>
        <option value="">Choose…</option>
        {field.options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    );
  }
  return <input {...common} type={field.kind === "date" ? "date" : "text"} />;
}

// [X4] A form to complete. A leave request with something missing: submitting it files the request,
// with exactly these values, checked again by the server. A form of the model (ask_form): the answers
// go back to the assistant as the user's next message.
function ActionForm({ form, busy, onSubmit, onCancel }) {
  const [values, setValues] = useState(() => Object.fromEntries(form.fields.map((field) => [field.name, field.value])));
  const [errors, setErrors] = useState(() => Object.fromEntries(form.fields.filter((field) => field.error).map((field) => [field.name, field.error])));
  const submit = async (event) => {
    event.preventDefault();
    setErrors((await onSubmit(values)) ?? {});
  };
  return (
    <form className={styles.formFields} onSubmit={submit} noValidate>
      {form.fields.map((field) => (
        <div key={field.name} className={styles.formField}>
          <label className={styles.formLabel} htmlFor={`form-${field.name}`}>
            {field.label}{!field.required && <span className={styles.formOptional}> (optional)</span>}
          </label>
          <Control field={{ ...field, error: errors[field.name] }} value={values[field.name]} disabled={busy}
            onChange={(value) => setValues((current) => ({ ...current, [field.name]: value }))} />
          {errors[field.name] && <p className={styles.formError} role="alert">{errors[field.name]}</p>}
        </div>
      ))}
      {errors._form && <p className={styles.formError} role="alert">{errors._form}</p>}
      <footer className={styles.confirmationFooter}>
        <p className={styles.confirmationHint}>
          {form.kind === "answers" ? "Your answers are sent to the assistant." : "Nothing is done until you submit."}
        </p>
        <div className={styles.confirmationButtons}>
          <Button disabled={busy} onClick={onCancel}>Cancel</Button>
          <Button type="submit" variant="primary" icon="check" iconSize={14} disabled={busy}>{form.submit_label}</Button>
        </div>
      </footer>
    </form>
  );
}

export function FormCard({ title, plan, form, busy, onSubmit, onAnswer, onCancel }) {
  return (
    <section className={styles.confirmation} aria-label={title}>
      <p className={styles.confirmationTitle}><Icon name={form.kind === "question" ? "message" : "file-text"} size={16} />{title}</p>
      <p className={styles.formQuestion}>{plan}</p>
      {form.kind === "question"
        ? <QuestionForm field={form.fields[0]} busy={busy} onAnswer={onAnswer} />
        : <ActionForm form={form} busy={busy} onSubmit={onSubmit} onCancel={onCancel} />}
    </section>
  );
}
