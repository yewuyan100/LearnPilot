import { Ellipsis } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

export type ActionMenuItem = {
  label: string;
  onSelect: () => void;
  destructive?: boolean;
  disabled?: boolean;
};

export function ActionMenu({
  label,
  items,
  className = "",
}: {
  label: string;
  items: ActionMenuItem[];
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  return <div ref={root} className={`action-menu ${className}`.trim()}>
    <button
      type="button"
      className="action-menu__trigger"
      aria-label={label}
      aria-haspopup="menu"
      aria-expanded={open}
      aria-controls={menuId}
      onClick={() => setOpen((value) => !value)}
    >
      <Ellipsis size={19}/>
    </button>
    {open && <div id={menuId} className="action-menu__popover" role="menu">
      {items.map((item) => <button
        key={item.label}
        type="button"
        role="menuitem"
        className={item.destructive ? "is-destructive" : ""}
        disabled={item.disabled}
        onClick={() => {
          setOpen(false);
          item.onSelect();
        }}
      >{item.label}</button>)}
    </div>}
  </div>;
}
