/** A very small markdown renderer, for help articles only.
 *
 * A full markdown library would be several times the size of every article put
 * together. The articles are ours, so the subset they use is a closed set:
 * paragraphs, bullets, numbered steps, bold, italic, inline code, internal
 * links of the form [text](#article-id), and screenshots as
 * ![alt](/help/name.png) on a line of their own. Anything outside that renders as plain text rather than
 * breaking, which is the right failure for a help page.
 */
import { Fragment, type ReactNode } from "react";

type Props = {
  markdown: string;
  /** Called for [text](#article-id) links, to move the panel to that article. */
  onNavigate: (articleId: string) => void;
};

/** Split one line into bold / code / link runs. */
function renderInline(line: string, onNavigate: (id: string) => void): ReactNode[] {
  const parts: ReactNode[] = [];
  // Bold is matched before italic, or "**x**" would be read as an empty italic
  // followed by stray asterisks. The articles quote UI labels as *Admin export*
  // constantly, so italic is not optional decoration here.
  const pattern =
    /\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\(#([a-z0-9-]+)\)|\*([^*\n]+)\*/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = pattern.exec(line)) !== null) {
    if (match.index > last) parts.push(line.slice(last, match.index));
    const [, bold, code, linkText, linkTarget, italic] = match;
    if (bold !== undefined) {
      parts.push(<strong key={key++}>{bold}</strong>);
    } else if (code !== undefined) {
      parts.push(<code key={key++}>{code}</code>);
    } else if (italic !== undefined) {
      parts.push(<em key={key++}>{italic}</em>);
    } else if (linkText !== undefined && linkTarget !== undefined) {
      parts.push(
        <button
          key={key++}
          type="button"
          className="help-inline-link"
          onClick={() => onNavigate(linkTarget)}
        >
          {linkText}
        </button>,
      );
    }
    last = pattern.lastIndex;
  }
  if (last < line.length) parts.push(line.slice(last));
  return parts;
}

export function HelpMarkdown({ markdown, onNavigate }: Props) {
  const blocks: ReactNode[] = [];
  const lines = markdown.split(/\r?\n/);
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) {
      i++;
      continue;
    }

    // Headings
    const heading = /^(#{2,4})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const text = renderInline(heading[2], onNavigate);
      blocks.push(
        level === 2 ? (
          <h3 key={key++}>{text}</h3>
        ) : (
          <h4 key={key++}>{text}</h4>
        ),
      );
      i++;
      continue;
    }

    // A screenshot on its own line. Checked before the paragraph branch, or it
    // would be swallowed as prose and rendered as literal markdown.
    const image = /^!\[([^\]]*)\]\(([^)\s]+)\)$/.exec(line.trim());
    if (image) {
      const [, alt, src] = image;
      blocks.push(
        <figure key={key++} className="help-figure">
          {/* Deliberately not loading="lazy". The panel swaps article content
              without scrolling, so a lazy image sits unloaded as a 1px hairline
              until the reader happens to scroll -- which looks broken. At most
              one image per article, already downloaded once and cached, so
              there is nothing to defer. */}
          <img src={src} alt={alt} decoding="async" className="help-shot" />
        </figure>,
      );
      i++;
      continue;
    }

    // Bulleted list — items may wrap onto continuation lines.
    if (/^[-*]\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && (/^[-*]\s+/.test(lines[i]) || /^\s{2,}\S/.test(lines[i]))) {
        if (/^[-*]\s+/.test(lines[i])) {
          items.push(lines[i].replace(/^[-*]\s+/, ""));
        } else {
          items[items.length - 1] = `${items[items.length - 1]} ${lines[i].trim()}`;
        }
        i++;
      }
      blocks.push(
        <ul key={key++}>
          {items.map((item, n) => (
            <li key={n}>{renderInline(String(item), onNavigate)}</li>
          ))}
        </ul>,
      );
      continue;
    }

    // Numbered steps, same wrapping rule.
    if (/^\d+\.\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && (/^\d+\.\s+/.test(lines[i]) || /^\s{2,}\S/.test(lines[i]))) {
        if (/^\d+\.\s+/.test(lines[i])) {
          items.push(lines[i].replace(/^\d+\.\s+/, ""));
        } else {
          items[items.length - 1] = `${items[items.length - 1]} ${lines[i].trim()}`;
        }
        i++;
      }
      blocks.push(
        <ol key={key++}>
          {items.map((item, n) => (
            <li key={n}>{renderInline(String(item), onNavigate)}</li>
          ))}
        </ol>,
      );
      continue;
    }

    // Paragraph: consume until a blank line or the start of another block.
    const paragraph: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^[-*]\s+/.test(lines[i]) &&
      !/^\d+\.\s+/.test(lines[i]) &&
      !/^#{2,4}\s+/.test(lines[i]) &&
      !/^!\[[^\]]*\]\([^)\s]+\)$/.test(lines[i].trim())
    ) {
      paragraph.push(lines[i].trim());
      i++;
    }
    blocks.push(<p key={key++}>{renderInline(paragraph.join(" "), onNavigate)}</p>);
  }

  return <Fragment>{blocks}</Fragment>;
}
