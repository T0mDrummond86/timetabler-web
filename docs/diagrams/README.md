# Diagrams

The pictures in `../ARCHITECTURE.md` are generated from the `.mmd` files here,
so the source and the image never drift apart.

- `*.mmd` — the diagram source (Mermaid)
- `*.png` — for pasting into slides, documents and email
- `*.svg` — for anywhere that should stay sharp at any size

## Changing a diagram

Edit the `.mmd` file, then re-render from this folder:

    npx --yes @mermaid-js/mermaid-cli -i architecture-overview.mmd \
      -o architecture-overview.png -c mmdc-config.json -p puppeteer.json -b white -s 2

Repeat with `-o ...svg` for the vector version. `puppeteer.json` points at the
copy of Google Chrome installed on the machine, which is what does the drawing.

No install step beyond Node and Chrome — `npx` fetches the renderer each time.
