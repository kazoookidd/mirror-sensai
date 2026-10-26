import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { SECTIONS } from "./sections.js";

const SWIPE_DISTANCE = 70;
const SWIPE_RATIO = 2;

let lastIndex = null;

export function useSlideDirection(active) {
  const index = SECTIONS.findIndex((section) => section.id === active);
  const [direction] = useState(() => {
    if (index < 0 || lastIndex === null || lastIndex === index) return "none";
    return index > lastIndex ? "forward" : "back";
  });
  useEffect(() => {
    if (index >= 0) lastIndex = index;
  }, [index]);
  return direction;
}

export function useTabSwipe(active, enabled) {
  const navigate = useNavigate();
  const start = useRef(null);
  if (!enabled)
    return {};

  return {
    onTouchStart(event) {
      const touch = event.touches[0];
      start.current = event.target.closest("[data-swipe-ignore], textarea, input")
        ? null : { x: touch.clientX, y: touch.clientY };
    },
    onTouchEnd(event) {
      if (!start.current) return;
      const touch = event.changedTouches[0];
      const dx = touch.clientX - start.current.x;
      const dy = touch.clientY - start.current.y;
      start.current = null;
      if (Math.abs(dx) < SWIPE_DISTANCE || Math.abs(dx) < SWIPE_RATIO * Math.abs(dy))
        return;
      const index = SECTIONS.findIndex((section) => section.id === active);
      const next = SECTIONS[index + (dx < 0 ? 1 : -1)];
      if (next)
        navigate(next.to);
    },
  };
}
