import { createElement, lazy } from "react";

export function lazyNamedExport(loader, exportName) {
  return lazy(() => loader().then((module) => ({ default: module[exportName] })));
}

export function createPreloadableNamedExport(loader, exportName) {
  let loadedComponent = null;
  let pendingModule = null;

  function load() {
    if (!pendingModule) {
      pendingModule = loader().then((module) => {
        loadedComponent = module[exportName];
        return { default: module[exportName] };
      });
    }
    return pendingModule;
  }

  const LazyComponent = lazy(load);

  function PreloadableComponent(props) {
    if (loadedComponent) {
      const Component = loadedComponent;
      return createElement(Component, props);
    }
    return createElement(LazyComponent, props);
  }

  PreloadableComponent.preload = load;
  return PreloadableComponent;
}

export function scheduleIdleTask(callback, options = {}) {
  const {
    idleTimeout = 400,
    fallbackDelay = 120,
  } = options;
  if (typeof window === "undefined") {
    return () => {};
  }
  if (typeof window.requestIdleCallback === "function") {
    const handle = window.requestIdleCallback(callback, { timeout: idleTimeout });
    return () => window.cancelIdleCallback?.(handle);
  }
  const handle = window.setTimeout(callback, fallbackDelay);
  return () => window.clearTimeout(handle);
}
