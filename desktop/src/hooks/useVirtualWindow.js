import { useEffect, useMemo, useState } from "react";

const DEFAULT_VIEWPORT_HEIGHT = 320;

export function useVirtualWindow(items, {
  containerRef,
  itemHeight = 40,
  overscan = 4,
  enabled = true,
  defaultViewportHeight = DEFAULT_VIEWPORT_HEIGHT,
} = {}) {
  const safeItems = Array.isArray(items) ? items : [];
  const [viewportState, setViewportState] = useState({
    scrollTop: 0,
    viewportHeight: defaultViewportHeight,
  });

  useEffect(() => {
    if (!enabled) {
      setViewportState((current) => ({
        ...current,
        scrollTop: 0,
      }));
      return undefined;
    }
    const element = containerRef?.current || null;
    if (!element) {
      return undefined;
    }

    let frameId = null;
    const syncViewport = () => {
      frameId = null;
      setViewportState({
        scrollTop: element.scrollTop || 0,
        viewportHeight: element.clientHeight || defaultViewportHeight,
      });
    };
    const scheduleViewportSync = () => {
      if (frameId !== null) {
        return;
      }
      frameId = window.requestAnimationFrame(syncViewport);
    };

    syncViewport();
    element.addEventListener("scroll", scheduleViewportSync, { passive: true });
    window.addEventListener("resize", scheduleViewportSync);
    return () => {
      element.removeEventListener("scroll", scheduleViewportSync);
      window.removeEventListener("resize", scheduleViewportSync);
      if (frameId !== null) {
        window.cancelAnimationFrame(frameId);
      }
    };
  }, [containerRef, defaultViewportHeight, enabled, safeItems.length]);

  return useMemo(() => {
    if (!enabled || safeItems.length === 0) {
      return {
        startIndex: 0,
        endIndex: safeItems.length,
        visibleItems: safeItems,
        topSpacerHeight: 0,
        bottomSpacerHeight: 0,
      };
    }
    const safeItemHeight = Math.max(1, Number(itemHeight) || 1);
    const safeOverscan = Math.max(0, Number(overscan) || 0);
    const visibleCount = Math.max(
      1,
      Math.ceil((viewportState.viewportHeight || defaultViewportHeight) / safeItemHeight),
    );
    const startIndex = Math.max(
      0,
      Math.floor((viewportState.scrollTop || 0) / safeItemHeight) - safeOverscan,
    );
    const endIndex = Math.min(
      safeItems.length,
      startIndex + visibleCount + safeOverscan * 2,
    );
    return {
      startIndex,
      endIndex,
      visibleItems: safeItems.slice(startIndex, endIndex),
      topSpacerHeight: startIndex * safeItemHeight,
      bottomSpacerHeight: Math.max(0, (safeItems.length - endIndex) * safeItemHeight),
    };
  }, [defaultViewportHeight, enabled, itemHeight, overscan, safeItems, viewportState]);
}
