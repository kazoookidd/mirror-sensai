import { useEffect, useState } from "react";
import { Button } from "../../components/ui/Button/Button.jsx";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { ModelSelect } from "../ollama/ModelSelect/ModelSelect.jsx";
import { OllamaStatus } from "../ollama/OllamaStatus/OllamaStatus.jsx";
import { PersonaSelect } from "../personas/PersonaSelect/PersonaSelect.jsx";
import { Segmented } from "../../components/ui/Segmented/Segmented.jsx";
import { Switch } from "../../components/ui/Switch/Switch.jsx";
import { TestTag } from "../../components/feedback/TestTag/TestTag.jsx";
import { useApp } from "../../context/AppContext.jsx";
import { settings as settingsApi } from "../../api/settings.js";
import { getTheme, setTheme } from "../../lib/theme.js";
import { GenerationSettings } from "./GenerationSettings.jsx";
import { Section, Setting } from "./Section.jsx";
import styles from "./SettingsSections.module.css";

const THEMES = [
  { value: "light", label: "Light", icon: <Icon name="sun" size={14} /> },
  { value: "dark", label: "Dark", icon: <Icon name="moon" size={14} /> },
  { value: "system", label: "System", icon: <Icon name="monitor" size={14} /> },
];

export function SettingsSections() {
  const { ollama, refreshStatus } = useApp();
  const [values, setValues] = useState(null);
  const [theme, chooseTheme] = useState(getTheme);

  useEffect(() => {
    settingsApi.get().then(setValues).catch(() => setValues({ temperature: null, num_predict: null }));
  }, []);

  return (
    <>
      <Section title="AI model" description="Model run by Ollama to generate the answers.">
        <Setting name="Default model" description="Used for new chats.">
          <ModelSelect variant="md" align="right" block />
        </Setting>
        <Setting name="Persona" description="The HR role SENSAI plays. The chat history is kept.">
          <PersonaSelect variant="md" align="right" block />
        </Setting>
        <div className={styles.connection}>
          <div className={styles.label}>
            <p className={styles.name}>Ollama connection</p>
            <p className={styles.url}>{ollama.url || "http://localhost:11434"}</p>
          </div>
          <OllamaStatus online="Connected" offline="Offline" className={styles.status} />
          <Button icon="refresh" className={styles.check} onClick={refreshStatus}>
            <span className="desktop-only">Check</span>
            <span className="mobile-only">Check connection</span>
          </Button>
        </div>
      </Section>

      <Section title="Generation" description="Options sent to Ollama with every request.">
        {values && <GenerationSettings values={values} onSaved={setValues} />}
      </Section>

      <Section title="Interface" description="Appearance and display of the answers.">
        <Setting name="Theme" description="Follows the system by default.">
          <Segmented label="Theme" options={THEMES} value={theme}
            onChange={(value) => { setTheme(value); chooseTheme(value); }} />
        </Setting>
        <Setting inline name="Show sources" description="Lists the passages used when the HR documents are searched.">
          <TestTag />
          <Switch checked disabled readOnly aria-label="Show sources (not available yet)" title="[TEST] Not available yet" />
        </Setting>
      </Section>
    </>
  );
}
