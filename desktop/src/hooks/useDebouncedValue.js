import { useEffect, useState } from "react";

export function useDebouncedValue(value, delayMs = 120) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setDebouncedValue(value);
    }, Math.max(0, Number(delayMs) || 0));
    return () => window.clearTimeout(timeoutId);
  }, [delayMs, value]);

  return debouncedValue;
}
