import { useCallback, useContext, useEffect, useId, useRef, useState } from "react";
import { createContext } from "react";

type DropdownGroupApi = {
  register: (id: string, close: () => void) => () => void;
  notifyOpen: (id: string) => void;
};

export const DropdownGroupContext = createContext<DropdownGroupApi | null>(null);

export function useDropdown() {
  const group = useContext(DropdownGroupContext);
  const dropdownId = useId();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  const close = useCallback(() => setOpen(false), []);

  const openMenu = useCallback(() => {
    group?.notifyOpen(dropdownId);
    setOpen(true);
  }, [group, dropdownId]);

  const toggle = useCallback(() => {
    if (open) close();
    else openMenu();
  }, [open, close, openMenu]);

  useEffect(() => {
    return group?.register(dropdownId, close);
  }, [group, dropdownId, close]);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    function onPointerDown(e: PointerEvent) {
      const el = wrapRef.current;
      if (el && !el.contains(e.target as Node)) close();
    }
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [open, close]);

  return { open, close, toggle, openMenu, wrapRef };
}
