import { cx } from "../../../lib/cx.js";
import styles from "./Slider.module.css";

export function Slider({ min, max, value, className, ...props }) {
  const fill = `${((value - min) / (max - min)) * 100}%`;
  return (
    <input className={cx(styles.slider, className)} type="range" min={min} max={max} value={value}
      style={{ "--fill": fill }} {...props} />
  );
}
