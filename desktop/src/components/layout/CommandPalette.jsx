import { memo, useEffect, useMemo, useRef, useState } from "react";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { useI18n } from "../../i18n";

function SearchIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-4.35-4.35" />
    </svg>
  );
}

function matchScore(text, query) {
  const lowerText = String(text || "").toLowerCase();
  const lowerQuery = String(query || "").toLowerCase();
  if (lowerText === lowerQuery) return 100;
  if (lowerText.startsWith(lowerQuery)) return 80;
  if (lowerText.includes(lowerQuery)) return 60;
  return 0;
}

function sameActions(previousActions = [], nextActions = []) {
  if (previousActions === nextActions) {
    return true;
  }
  if (!Array.isArray(previousActions) || !Array.isArray(nextActions) || previousActions.length !== nextActions.length) {
    return false;
  }
  for (let index = 0; index < previousActions.length; index += 1) {
    const previousAction = previousActions[index];
    const nextAction = nextActions[index];
    if (
      previousAction?.id !== nextAction?.id
      || previousAction?.label !== nextAction?.label
      || previousAction?.shortcut !== nextAction?.shortcut
      || previousAction?.category !== nextAction?.category
      || previousAction?.keywords !== nextAction?.keywords
    ) {
      return false;
    }
  }
  return true;
}

export const CommandPalette = memo(function CommandPalette({
  open,
  onClose,
  actions,
}) {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const inputRef = useRef(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const debouncedQuery = useDebouncedValue(query, 100);
  const indexedActions = useMemo(
    () => (actions || []).map((action) => ({
      ...action,
      labelText: String(action?.label || "").toLowerCase(),
      keywordsText: String(action?.keywords || "").toLowerCase(),
    })),
    [actions],
  );

  const filtered = useMemo(() => {
    if (!debouncedQuery.trim()) return indexedActions;
    const q = debouncedQuery.trim();
    return indexedActions
      .map((action) => ({ ...action, score: Math.max(matchScore(action.labelText, q), matchScore(action.keywordsText, q)) }))
      .filter((action) => action.score > 0)
      .sort((a, b) => b.score - a.score);
  }, [debouncedQuery, indexedActions]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setSelectedIndex(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [filtered.length]);

  useEffect(() => {
    if (!open) return undefined;

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        onClose();
        event.preventDefault();
        return;
      }
      if (event.key === "ArrowDown") {
        setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1));
        event.preventDefault();
        return;
      }
      if (event.key === "ArrowUp") {
        setSelectedIndex((i) => Math.max(i - 1, 0));
        event.preventDefault();
        return;
      }
      if (event.key === "Enter" && filtered.length > 0) {
        const action = filtered[selectedIndex];
        if (action?.onExecute) {
          action.onExecute();
          onClose();
        }
        event.preventDefault();
      }
    }

    window.addEventListener("keydown", handleKeyDown, true);
    return () => window.removeEventListener("keydown", handleKeyDown, true);
  }, [open, filtered, selectedIndex, onClose]);

  if (!open) return null;

  return (
    <>
      <div className="command-palette__backdrop" onClick={onClose} />
      <div className="command-palette">
        <div className="command-palette__input-row">
          <SearchIcon />
          <input
            ref={inputRef}
            className="command-palette__input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("action.search") || "Search actions..."}
            type="text"
            autoComplete="off"
            spellCheck={false}
          />
          <kbd className="command-palette__kbd">Esc</kbd>
        </div>
        <div className="command-palette__list" role="listbox">
          {filtered.length ? (
            filtered.map((action, index) => (
              <button
                key={action.id}
                className={`command-palette__item ${index === selectedIndex ? "command-palette__item--selected" : ""}`}
                onClick={() => {
                  action.onExecute?.();
                  onClose();
                }}
                onMouseEnter={() => setSelectedIndex(index)}
                role="option"
                aria-selected={index === selectedIndex}
                type="button"
              >
                <span className="command-palette__item-label">{action.label}</span>
                {action.shortcut ? <kbd className="command-palette__kbd">{action.shortcut}</kbd> : null}
                {action.category ? <span className="command-palette__item-category">{action.category}</span> : null}
              </button>
            ))
          ) : (
            <div className="command-palette__empty">{t("sidebar.emptyProjects") || "No results"}</div>
          )}
        </div>
      </div>
    </>
  );
}, (previousProps, nextProps) => (
  previousProps.open === nextProps.open
  && sameActions(previousProps.actions, nextProps.actions)
));
