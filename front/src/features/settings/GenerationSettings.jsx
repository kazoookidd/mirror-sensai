import { useState } from "react";
import { InputBox } from "../../components/ui/Field/Field.jsx";
import { Slider } from "../../components/ui/Slider/Slider.jsx";
import { settings as settingsApi } from "../../api/settings.js";
import { formatDecimal } from "../../lib/format.js";
import { Setting } from "./Section.jsx";
import styles from "./GenerationSettings.module.css";

const MAX_TEMPERATURE = 2;
const DEFAULT_TEMPERATURE = 0.8;
const SLIDER_KEYS = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown"];

export function GenerationSettings({ values, onSaved }) {
  const [temperature, setTemperature] = useState(values.temperature);
  const [length, setLength] = useState(values.num_predict ?? "");
  const [error, setError] = useState("");

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
      <Setting name="Temperature" description="Lower: more factual answers." className={styles.temperature}>
        <div className={styles.slider}>
          <Slider min={0} max={MAX_TEMPERATURE} step={0.1} value={temperature ?? DEFAULT_TEMPERATURE}
            aria-label="Temperature"
            onChange={(event) => setTemperature(Number(event.target.value))}
            onPointerUp={(event) => save("temperature", event.target.value)}
            onKeyUp={(event) => SLIDER_KEYS.includes(event.key) && save("temperature", event.target.value)} />
          <span className={styles.value} title={temperature === null ? "Default value of the model" : undefined}>
            {temperature === null ? "default" : formatDecimal(temperature)}
          </span>
        </div>
      </Setting>
      <Setting inline name="Max length" description="Maximum number of generated tokens (num_predict).">
        <InputBox small mono type="number" min={1} step={1} inputMode="numeric" placeholder="default"
          aria-label="Max length" className={styles.number} value={length}
          onChange={(event) => setLength(event.target.value)}
          onBlur={() => save("num-predict", String(length).trim() || "default")} />
      </Setting>
      {error && <p className={styles.error} role="alert">{error}</p>}
    </>
  );
}
