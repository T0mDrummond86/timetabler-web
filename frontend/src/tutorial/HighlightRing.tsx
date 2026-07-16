/** Pulsing outline around the element a tutorial step points at.
 *
 * Follows the target's bounding rect on a rAF loop (handles sticky headers,
 * scrolling, zoom). Renders nothing when the target isn't in the DOM — the
 * panel copy tells the user where to go instead of showing a stray ring.
 */
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

type Rect = { top: number; left: number; width: number; height: number };

export function HighlightRing({ target, flash }: { target?: string; flash: number }) {
  const [rect, setRect] = useState<Rect | null>(null);

  useEffect(() => {
    if (!target) {
      setRect(null);
      return;
    }
    let raf = 0;
    let last = "";
    const tick = () => {
      const el = document.querySelector(`[data-tutorial-id="${target}"]`);
      if (!el) {
        if (last !== "gone") {
          last = "gone";
          setRect(null);
        }
      } else {
        const r = el.getBoundingClientRect();
        const key = `${Math.round(r.top)}:${Math.round(r.left)}:${Math.round(r.width)}:${Math.round(r.height)}`;
        const visible = r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight;
        if (!visible) {
          if (last !== "gone") {
            last = "gone";
            setRect(null);
          }
        } else if (key !== last) {
          last = key;
          setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
        }
      }
      raf = window.requestAnimationFrame(tick);
    };
    raf = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(raf);
  }, [target]);

  if (!rect) return null;
  return createPortal(
    <div
      className={`tutorial-ring${flash > 0 ? " tutorial-ring-flash" : ""}`}
      // key on flash so re-clicking "Show me" restarts the animation
      key={flash}
      style={{
        top: rect.top - 5,
        left: rect.left - 5,
        width: rect.width + 10,
        height: rect.height + 10,
      }}
      aria-hidden="true"
    />,
    document.body,
  );
}
