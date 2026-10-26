import { useState } from "react";
import { Button } from "../../components/ui/Button/Button.jsx";
import { Field, FieldHelp, FieldLabel } from "../../components/ui/Field/Field.jsx";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { Segmented } from "../../components/ui/Segmented/Segmented.jsx";
import { TestTag } from "../../components/feedback/TestTag/TestTag.jsx";
import { ContextPreview, tokenEstimate } from "./ContextPreview.jsx";
import styles from "./ProfileForm.module.css";

const MAX_INSTRUCTIONS = 1000;
const SERVICES = ["Human resources", "Customer support", "Management", "Sales", "Engineering"];
const LANGUAGES = ["English", "French"];
const TONES = [{ value: "concise", label: "Concise" }, { value: "detailed", label: "Detailed" }];

function SelectField({ id, label, options, value, onChange }) {
  return (
    <div className={styles.field}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <select id={id} className={styles.select} value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => <option key={option}>{option}</option>)}
      </select>
    </div>
  );
}

export function ProfileForm({ onCancel }) {
  const [profile, setProfile] = useState({
    name: "", role: "", service: SERVICES[0], language: LANGUAGES[0], tone: "concise", instructions: "",
  });
  const [previewOpen, setPreviewOpen] = useState(false);
  const update = (key) => (value) => setProfile((current) => ({ ...current, [key]: value }));

  return (
    <div className={styles.layout}>
      <div className={styles.columns}>
        <form className={styles.form} onSubmit={(event) => event.preventDefault()}>
          <section className={styles.section}>
            <header className={styles.sectionHeader}>
              <h2 className="text-heading">You</h2>
              <p className="text-small text-secondary">Used to adapt the answers to your situation.</p>
            </header>
            <div className={`${styles.row} ${styles.stack}`}>
              <Field id="profile-name" label="Full name" placeholder="Camille Martin"
                value={profile.name} onChange={(event) => update("name")(event.target.value)} />
              <Field id="profile-role" label="Job title" placeholder="Customer support manager"
                value={profile.role} onChange={(event) => update("role")(event.target.value)} />
            </div>
            <div className={styles.row}>
              <SelectField id="profile-service" label="Department" options={SERVICES} value={profile.service} onChange={update("service")} />
              <SelectField id="profile-language" options={LANGUAGES} value={profile.language} onChange={update("language")}
                label={<><span className="desktop-only">Answer language</span><span className="mobile-only">Language</span></>} />
            </div>
          </section>
          <section className={styles.section}>
            <header className={styles.sectionHeader}>
              <h2 className="text-heading">Answers</h2>
              <p className="text-small text-secondary">How SENSAI should answer you.</p>
            </header>
            <div className={styles.tone}>
              <span>Tone<span className="mobile-only"> of the answers</span></span>
              <Segmented label="Tone of the answers" options={TONES} value={profile.tone} onChange={update("tone")} />
            </div>
            <div className={styles.field}>
              <FieldLabel htmlFor="profile-instructions"
                aside={<span className="text-caption text-secondary">{profile.instructions.length} / {MAX_INSTRUCTIONS}</span>}>
                Custom instructions
              </FieldLabel>
              <textarea id="profile-instructions" className={styles.textarea} maxLength={MAX_INSTRUCTIONS}
                placeholder="I manage a team of 6 people. Answer in a few sentences and always quote the article of the document used."
                value={profile.instructions} onChange={(event) => update("instructions")(event.target.value)} />
              <FieldHelp>Do not add sensitive information: it is sent to the model in every chat.</FieldHelp>
            </div>
          </section>
          <button className={`${styles.contextLink} mobile-only`} type="button" aria-expanded={previewOpen}
            onClick={() => setPreviewOpen((open) => !open)}>
            <span className={styles.contextLabel}><Icon name="cpu" size={16} />View the injected context</span>
            <span className={styles.contextTokens}>≈ {tokenEstimate(profile)} tokens</span>
          </button>
          {previewOpen && <div className="mobile-only"><ContextPreview profile={profile} /></div>}
          <div className={styles.actions}>
            <Button onClick={onCancel} className="desktop-only">Cancel</Button>
            <Button variant="primary" type="submit" disabled title="[TEST] The backend does not save the profile yet">
              Save <TestTag />
            </Button>
          </div>
        </form>
        <div className="desktop-only"><ContextPreview profile={profile} /></div>
      </div>
    </div>
  );
}
