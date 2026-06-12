import { useEffect, useState, type RefObject } from "react";

export type GridFitMetrics = {
  /** Slot height that fills the container at 100% zoom. */
  fitSlotHeight: number;
  containerHeight: number;
};

/** Measure grid scroll area so the full day can expand to fill it at default zoom. */
export function useGridFitMetrics(
  containerRef: RefObject<HTMLElement | null>,
  numSlots: number,
  headerHeight: number,
  enabled: boolean,
): GridFitMetrics | null {
  const [metrics, setMetrics] = useState<GridFitMetrics | null>(null);

  useEffect(() => {
    if (!enabled) {
      setMetrics(null);
      return;
    }
    const el = containerRef.current;
    if (!el) return;

    const measure = () => {
      const containerHeight = el.clientHeight;
      const bodyHeight = containerHeight - headerHeight;
      if (containerHeight > 0 && bodyHeight > 0 && numSlots > 0) {
        setMetrics({
          containerHeight,
          fitSlotHeight: Math.max(6, Math.floor(bodyHeight / numSlots)),
        });
      }
    };

    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [containerRef, numSlots, headerHeight, enabled]);

  return metrics;
}
