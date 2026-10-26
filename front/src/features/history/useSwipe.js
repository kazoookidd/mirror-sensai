import { useRef, useState } from "react";

const ACTIONS_WIDTH = 152;
const OPEN_THRESHOLD = 60;
const TAP_DISTANCE = 8;

export function useSwipe() {
  const [offset, setOffset] = useState(0);
  const [dragging, setDragging] = useState(false);
  const start = useRef({ x: 0, offset: 0 });
  const moved = useRef(false);

  const handlers = {
    onPointerDown(event) {
      if (event.pointerType === "mouse") return;
      start.current = { x: event.clientX, offset };
      moved.current = false;
      setDragging(true);
    },
    onPointerMove(event) {
      if (!dragging) return;
      const delta = event.clientX - start.current.x;
      if (Math.abs(delta) > TAP_DISTANCE) moved.current = true;
      setOffset(Math.min(0, Math.max(-ACTIONS_WIDTH, start.current.offset + delta)));
    },
    onPointerUp() {
      if (!dragging) return;
      setDragging(false);
      setOffset((value) => (value < -OPEN_THRESHOLD ? -ACTIONS_WIDTH : 0));
    },
  };
  handlers.onPointerCancel = handlers.onPointerUp;

  return {
    offset,
    dragging,
    handlers,
    close: () => setOffset(0),
    wasSwipe: () => moved.current,
  };
}
