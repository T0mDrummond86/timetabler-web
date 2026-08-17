/** Render a QR code to inline SVG markup, locally.
 *
 * Never a third-party chart service: the two callers encode an internal
 * timetable URL and a TOTP secret respectively, and neither should leave the
 * deployment to be drawn.
 *
 * Always black on white regardless of theme — a QR is read by a camera, and
 * inverting it in dark mode stops some scanners cold.
 */
import qrcode from "qrcode-generator";

export function qrSvgMarkup(text: string, size = 148, label = "QR code"): string {
  // Type 0 = pick the smallest version that fits; "M" tolerates a little
  // screen glare and printing.
  const qr = qrcode(0, "M");
  qr.addData(text);
  qr.make();
  const count = qr.getModuleCount();
  const cell = size / count;
  let path = "";
  for (let r = 0; r < count; r++) {
    for (let c = 0; c < count; c++) {
      if (qr.isDark(r, c)) {
        path += `M${(c * cell).toFixed(2)},${(r * cell).toFixed(2)}h${cell.toFixed(2)}v${cell.toFixed(2)}h-${cell.toFixed(2)}z`;
      }
    }
  }
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" ` +
    `viewBox="0 0 ${size} ${size}" role="img" aria-label="${label}">` +
    `<rect width="${size}" height="${size}" fill="#ffffff"/>` +
    `<path d="${path}" fill="#000000"/></svg>`
  );
}
