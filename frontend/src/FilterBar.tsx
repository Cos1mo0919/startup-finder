import { ChevronDown, ChevronUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export type FilterOption = {value: string; label: string; count?: number};
export type Filter = {
  key: string;
  /** Accessible name of the option panel, e.g. "Yil". */
  name: string;
  /** Chip text while nothing is chosen, e.g. "Yil: barchasi". */
  placeholder: string;
  /** Chip text prefix once a value is chosen, e.g. "Yil: " (empty for Davr). */
  prefix: string;
  value: string;
  options: FilterOption[];
  onChange: (value: string) => void;
};

/** Filter chips whose options open in a panel under the chip row (no native select popup). */
export function FilterBar({filters}: {filters: Filter[]}) {
  const [openKey, setOpenKey] = useState<string | null>(null);
  const chipsRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const open = filters.find(filter => filter.key === openKey) || null;

  useEffect(() => {
    if (!openKey) return;
    const onPointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (chipsRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setOpenKey(null);
    };
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setOpenKey(null); };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("pointerdown", onPointer); document.removeEventListener("keydown", onKey); };
  }, [openKey]);

  const choose = (filter: Filter, value: string) => {
    setOpenKey(null);
    if (value !== filter.value) filter.onChange(value);
  };

  return <>
    <div className="filter-chips" role="group" aria-label="Filtrlar" ref={chipsRef}>
      {filters.map(filter => {
        const selected = filter.options.find(option => option.value === filter.value && option.value !== "");
        const isOpen = openKey === filter.key;
        return <button key={filter.key} type="button" data-filter={filter.key}
          className={`filter-chip${selected ? " is-active" : ""}${isOpen ? " is-open" : ""}`}
          aria-haspopup="listbox" aria-expanded={isOpen} aria-controls={isOpen ? `filter-panel-${filter.key}` : undefined}
          onClick={() => setOpenKey(isOpen ? null : filter.key)}>
          {selected ? filter.prefix + selected.label : filter.placeholder}
          {isOpen ? <ChevronUp size={14} aria-hidden="true"/> : <ChevronDown size={14} aria-hidden="true"/>}
        </button>;
      })}
    </div>
    {open && <div className="filter-panel" id={`filter-panel-${open.key}`} role="listbox" aria-label={open.name} ref={panelRef}>
      {open.options.map(option => {
        const active = option.value === open.value;
        return <button key={option.value || "all"} type="button" role="option" aria-selected={active}
          className={`filter-option${active ? " is-selected" : ""}`} onClick={() => choose(open, option.value)}>
          {option.label}
          {option.count !== undefined && <> <span className="filter-count">{option.count} ta</span></>}
        </button>;
      })}
    </div>}
  </>;
}
