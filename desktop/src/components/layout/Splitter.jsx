import { useRef } from "react";

export function Splitter({ axis = "vertical", onResize, className = "", title }) {
  const draggingRef = useRef(false);

  function startDrag(event) {
    event.preventDefault();
    draggingRef.current = true;
    const startX = event.clientX;
    const startY = event.clientY;

    function handleMove(moveEvent) {
      if (!draggingRef.current) {
        return;
      }
      const delta = axis === "vertical" ? moveEvent.clientX - startX : moveEvent.clientY - startY;
      onResize(delta);
    }

    function handleUp() {
      draggingRef.current = false;
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    }

    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
  }

  return (
    <div
      className={`splitter splitter--${axis} ${className}`.trim()}
      onPointerDown={startDrag}
      role="separator"
      tabIndex={0}
      title={title || "Resize panel"}
      aria-orientation={axis === "vertical" ? "vertical" : "horizontal"}
    />
  );
}
