import { useState } from "react";
import { Segmented } from "../../components/ui/Segmented/Segmented.jsx";
import { Switch } from "../../components/ui/Switch/Switch.jsx";
import { settings as settingsApi } from "../../api/settings.js";
import { useApp } from "../../context/AppContext.jsx";
import { isHr } from "../../layout/sections.js";
import { Setting } from "./Section.jsx";
import styles from "./GenerationSettings.module.css";

const OUTPUT_MODES = [
  { value: "redact", label: "Redact" },
  { value: "refuse", label: "Refuse" },
];

export function PrivacySettings({ values, onSaved }) {
  const [error, setError] = useState("");
  const locked = !isHr(useApp().user);

  const save = async (name, value) => {
    try {
      await settingsApi.set(name, value);
      setError("");
      onSaved(await settingsApi.get());
    } catch (failure) {
      setError(failure.message);
    }
  };

  return (
    <>
      <Setting inline name="Content guardrails"
        description="Blocks questions about other employees or attempts to drop the rules, and screens answers for personal details.">
        <Switch checked={values.guardrails} aria-label="Content guardrails" disabled={locked}
          onChange={(event) => save("guardrails", event.target.checked ? "on" : "off")} />
      </Setting>
      <Setting name="Personal details in answers"
        description="When an answer contains an e-mail, a phone number, a social security number, an IBAN or a card number.">
        <Segmented label="Personal details in answers" options={OUTPUT_MODES}
          value={values.guardrails_output} disabled={locked}
          onChange={(value) => save("guardrails-output", value)} />
      </Setting>
      {locked && <p className={styles.hint}>Set by HR for every employee.</p>}
      {error && <p className={styles.error} role="alert">{error}</p>}
    </>
  );
}
