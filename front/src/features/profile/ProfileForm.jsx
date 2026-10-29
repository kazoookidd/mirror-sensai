import { useEffect, useState } from "react";
import { Button } from "../../components/ui/Button/Button.jsx";
import { Field, FieldHelp, FieldLabel } from "../../components/ui/Field/Field.jsx";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { Segmented } from "../../components/ui/Segmented/Segmented.jsx";
import { profile as profileApi } from "../../api/profile.js";
import { ContextPreview, tokenEstimate } from "./ContextPreview.jsx";
import styles from "./ProfileForm.module.css";

// Same limits as back/Memories/Profile.py, which checks them again.
const MAX_TEXT = 80;
const MAX_INSTRUCTIONS = 1000;
const EMPTY = { name: "", role: "", department: "", language: "", tone: "", instructions: "" };
const DEPARTMENTS = [
  { value: "", label: "Not specified" },
  ...["Human resources", "Customer support", "Management", "Sales", "Engineering"].map((value) => ({ value, label: value })),
];
const LANGUAGES = [
  { value: "", label: "Same as my messages" },
  { value: "French", label: "French" },
  { value: "English", label: "English" },
];
const TONES = [{ value: "", label: "Default" }, { value: "concise", label: "Concise" }, { value: "detailed", label: "Detailed" }];

function SelectField({ id, label, options, value, onChange }) {
  // A value set elsewhere (/profile in the CLI) stays selectable.
  const choices = options.some((option) => option.value === value) ? options : [...options, { value, label: value }];
  return (
    <div className={styles.field}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <select id={id} className={styles.select} value={value} onChange={(event) => onChange(event.target.value)}>
        {choices.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </div>
  );
}

const same = (a, b) => Object.keys(EMPTY).every((key) => a[key] === b[key]);

export function ProfileForm({ onCancel }) {
  const [saved, setSaved] = useState(null);
  const [account, setAccount] = useState(null);
  const [profile, setProfile] = useState(EMPTY);
  const [status, setStatus] = useState({ saving: false, message: "", error: "" });
  const [previewOpen, setPreviewOpen] = useState(false);

  useEffect(() => {
    let active = true;
    profileApi.get()
      .then((data) => { if (active) { setSaved(data.profile); setProfile(data.profile); setAccount(data.account); } })
      .catch((failure) => { if (active) { setSaved(EMPTY); setStatus({ saving: false, message: "", error: failure.message }); } });
    return () => { active = false; };
  }, []);

  const update = (key) => (value) => {
    setProfile((current) => ({ ...current, [key]: value }));
    setStatus((current) => ({ ...current, message: "" }));
  };

  const save = async (event) => {
    event.preventDefault();
    setStatus({ saving: true, message: "", error: "" });
    try {
      const data = await profileApi.save(profile);
      setSaved(data.profile);
      setProfile(data.profile);
      setStatus({ saving: false, message: "Saved. It applies to your next message.", error: "" });
    } catch (failure) {
      setStatus({ saving: false, message: "", error: failure.message });
    }
  };

  const loading = saved === null;
  const changed = !loading && !same(profile, saved);

  return (
    <div className={styles.layout}>
      <div className={styles.columns}>
        <form className={styles.form} onSubmit={save} aria-busy={loading}>
          <section className={styles.section}>
            <header className={styles.sectionHeader}>
              <h2 className="text-heading">You</h2>
              <p className="text-small text-secondary">Used to adapt the answers to your situation.</p>
            </header>
            {account && (
              <div className={styles.account}>
                <span>Account type</span>
                <span className={styles.accountRole}>{account.label}</span>
                <p className={`text-small text-secondary ${styles.accountHelp}`}>
                  Set when the account was created (HR accounts in the terminal, employee accounts on the web).
                  It cannot be changed here.
                </p>
              </div>
            )}
            <div className={`${styles.row} ${styles.stack}`}>
              <Field id="profile-name" label="Full name" placeholder="Camille Martin" maxLength={MAX_TEXT}
                value={profile.name} onChange={(event) => update("name")(event.target.value)} />
              <Field id="profile-role" label="Job title" placeholder="Customer support manager" maxLength={MAX_TEXT}
                value={profile.role} onChange={(event) => update("role")(event.target.value)} />
            </div>
            <div className={styles.row}>
              <SelectField id="profile-department" label="Department" options={DEPARTMENTS} value={profile.department}
                onChange={update("department")} />
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
              <FieldHelp>Do not add sensitive information: it is sent to the model with every message.</FieldHelp>
            </div>
          </section>
          <button className={`${styles.contextLink} mobile-only`} type="button" aria-expanded={previewOpen}
            onClick={() => setPreviewOpen((open) => !open)}>
            <span className={styles.contextLabel}><Icon name="cpu" size={16} />View the injected context</span>
            <span className={styles.contextTokens}>≈ {tokenEstimate(profile)} tokens</span>
          </button>
          {previewOpen && <div className="mobile-only"><ContextPreview profile={profile} /></div>}
          {(status.error || status.message) && (
            <p className={status.error ? styles.error : styles.saved} role={status.error ? "alert" : "status"}>
              {status.error || status.message}
            </p>
          )}
          <div className={styles.actions}>
            <Button onClick={onCancel} className="desktop-only">{changed ? "Cancel" : "Close"}</Button>
            <Button variant="primary" type="submit" disabled={!changed || status.saving}>
              {status.saving ? "Saving…" : "Save"}
            </Button>
          </div>
        </form>
        <div className="desktop-only"><ContextPreview profile={profile} /></div>
      </div>
    </div>
  );
}
