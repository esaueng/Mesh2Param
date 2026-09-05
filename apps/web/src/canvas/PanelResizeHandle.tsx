import { useRef, type KeyboardEvent, type PointerEvent } from "react";
import { PANEL_WIDTH, panelLayoutStore, usePanelLayout } from "./panelLayout";

/**
 * Drag handle on the command panel's inner edge. Pointer drags resize
 * continuously (with pointer capture, so a fast drag that leaves the strip
 * keeps resizing); arrow keys step the width for keyboard users; double
 * click restores the default. The width lives in the persisted panel layout.
 */
export function PanelResizeHandle() {
  const layout = usePanelLayout();
  const drag = useRef<{ pointerId: number; startX: number; startWidth: number } | null>(null);

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    drag.current = { pointerId: event.pointerId, startX: event.clientX, startWidth: layout.width };
    event.currentTarget.setPointerCapture(event.pointerId);
    event.currentTarget.dataset.dragging = "true";
    event.preventDefault();
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const state = drag.current;
    if (state === null || state.pointerId !== event.pointerId) return;
    // The panel sits on the right, so dragging left widens it.
    panelLayoutStore.setWidth(state.startWidth + (state.startX - event.clientX));
  };
  const onPointerEnd = (event: PointerEvent<HTMLDivElement>) => {
    if (drag.current?.pointerId !== event.pointerId) return;
    drag.current = null;
    delete event.currentTarget.dataset.dragging;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? PANEL_WIDTH.step * 4 : PANEL_WIDTH.step;
    if (event.key === "ArrowLeft" || event.key === "ArrowUp") panelLayoutStore.setWidth(layout.width + step);
    else if (event.key === "ArrowRight" || event.key === "ArrowDown") panelLayoutStore.setWidth(layout.width - step);
    else if (event.key === "Home") panelLayoutStore.setWidth(PANEL_WIDTH.max);
    else if (event.key === "End") panelLayoutStore.setWidth(PANEL_WIDTH.min);
    else if (event.key === "Enter") panelLayoutStore.resetWidth();
    else return;
    event.preventDefault();
  };

  return (
    <div
      className="panel-resize-handle"
      role="separator"
      aria-label="Resize command panel"
      aria-orientation="vertical"
      aria-valuemin={PANEL_WIDTH.min}
      aria-valuemax={PANEL_WIDTH.max}
      aria-valuenow={layout.width}
      title="Drag to resize · double-click to reset"
      tabIndex={0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerEnd}
      onPointerCancel={onPointerEnd}
      onDoubleClick={() => panelLayoutStore.resetWidth()}
      onKeyDown={onKeyDown}
    />
  );
}
