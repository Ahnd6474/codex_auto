import { useEffect, useState } from "react";

export function usePersistentState(key, initialValue) {
  const [value, setValue] = useState(() => {
    if (typeof window === "undefined") {
      return initialValue;
    }
    try {
      const stored = window.localStorage.getItem(key);
      return stored === null ? initialValue : JSON.parse(stored);
    } catch (_error) {
      return initialValue;
    }
  });

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch (_error) {
      // Ignore persistence failures and keep the UI usable.
    }
  }, [key, value]);

  return [value, setValue];
}
