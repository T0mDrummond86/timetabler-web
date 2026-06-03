import { useCallback, useMemo, useRef, type ReactNode } from "react";
import { DropdownGroupContext } from "../hooks/useDropdown";

export function DropdownGroup({ children }: { children: ReactNode }) {
  const registry = useRef(new Map<string, () => void>());

  const register = useCallback((id: string, close: () => void) => {
    registry.current.set(id, close);
    return () => {
      registry.current.delete(id);
    };
  }, []);

  const notifyOpen = useCallback((id: string) => {
    registry.current.forEach((close, key) => {
      if (key !== id) close();
    });
  }, []);

  const value = useMemo(() => ({ register, notifyOpen }), [register, notifyOpen]);

  return <DropdownGroupContext.Provider value={value}>{children}</DropdownGroupContext.Provider>;
}
