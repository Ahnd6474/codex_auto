import { createContext, useContext, useMemo } from "react";
import { LANGUAGE_OPTIONS, detectInitialLanguage, normalizeLanguage, translate } from "./locale";
import { usePersistentState } from "./hooks/usePersistentState";

const I18nContext = createContext(null);

export function I18nProvider({ children }) {
  const [storedLanguage, setStoredLanguage] = usePersistentState("codex-auto:language", detectInitialLanguage());
  const language = normalizeLanguage(storedLanguage);

  const value = useMemo(
    () => ({
      language,
      languageOptions: LANGUAGE_OPTIONS,
      setLanguage(nextLanguage) {
        setStoredLanguage(normalizeLanguage(nextLanguage));
      },
      t(key, params = {}) {
        return translate(language, key, params);
      },
    }),
    [language, setStoredLanguage],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const value = useContext(I18nContext);
  if (!value) {
    throw new Error("useI18n must be used within an I18nProvider.");
  }
  return value;
}
