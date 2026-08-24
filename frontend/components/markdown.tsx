import type { ReactNode } from "react";
import { Fragment } from "react";

// A small, dependency-free renderer for the subset of Markdown docs/attendance-design.md
// actually uses: headers, paragraphs, bold/inline code, unordered lists, and tables. Not a
// general Markdown engine - just enough to render one design doc without adding a package.

function renderInline(text: string): ReactNode[] {
  const tokens: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      tokens.push(<Fragment key={key++}>{text.slice(lastIndex, match.index)}</Fragment>);
    }
    const token = match[0];
    if (token.startsWith("**")) {
      tokens.push(<strong key={key++}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("*")) {
      tokens.push(<em key={key++}>{token.slice(1, -1)}</em>);
    } else {
      tokens.push(
        <code key={key++} className="rounded bg-muted px-1 py-0.5 text-[0.85em]">
          {token.slice(1, -1)}
        </code>,
      );
    }
    lastIndex = match.index + token.length;
  }
  if (lastIndex < text.length) {
    tokens.push(<Fragment key={key++}>{text.slice(lastIndex)}</Fragment>);
  }
  return tokens;
}

function parseTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((cell) => cell.trim());
}

export function Markdown({ content }: { content: string }) {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === "") {
      i++;
      continue;
    }

    const headerMatch = /^(#{1,6})\s+(.*)$/.exec(line);
    if (headerMatch) {
      const level = headerMatch[1].length;
      const text = headerMatch[2];
      const sizeClass =
        level === 1
          ? "text-2xl font-semibold tracking-tight mt-2"
          : level === 2
            ? "text-xl font-semibold tracking-tight mt-8"
            : level === 3
              ? "text-lg font-semibold mt-6"
              : "text-base font-semibold mt-4";
      const Tag = (`h${Math.min(level, 6)}` as unknown) as "h1" | "h2" | "h3" | "h4" | "h5" | "h6";
      blocks.push(
        <Tag key={key++} className={sizeClass}>
          {renderInline(text)}
        </Tag>,
      );
      i++;
      continue;
    }

    // Table: a header row, a "---|---" separator row, then body rows.
    if (line.trim().startsWith("|") && lines[i + 1]?.trim().match(/^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$/)) {
      const header = parseTableRow(line);
      const rows: string[][] = [];
      let j = i + 2;
      while (j < lines.length && lines[j].trim().startsWith("|")) {
        rows.push(parseTableRow(lines[j]));
        j++;
      }
      blocks.push(
        <div key={key++} className="my-4 overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                {header.map((cell, idx) => (
                  <th key={idx} className="border-b px-3 py-2 text-left font-medium">
                    {renderInline(cell)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIdx) => (
                <tr key={rowIdx} className="border-b last:border-b-0">
                  {row.map((cell, cellIdx) => (
                    <td key={cellIdx} className="px-3 py-2 align-top">
                      {renderInline(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      i = j;
      continue;
    }

    // Unordered list (- item). A soft-wrapped continuation line (no leading "-", not blank,
    // not the start of another block) is appended to the previous item instead of starting a
    // new paragraph - Markdown source commonly wraps a long bullet across lines.
    if (/^\s*-\s+/.test(line)) {
      const items: string[] = [];
      let j = i;
      while (j < lines.length && lines[j].trim() !== "") {
        if (/^\s*-\s+/.test(lines[j])) {
          items.push(lines[j].replace(/^\s*-\s+/, ""));
          j++;
        } else if (!/^#{1,6}\s+/.test(lines[j]) && !lines[j].trim().startsWith("|") && items.length > 0) {
          items[items.length - 1] += ` ${lines[j].trim()}`;
          j++;
        } else {
          break;
        }
      }
      blocks.push(
        <ul key={key++} className="my-3 ml-5 list-disc space-y-1.5">
          {items.map((item, idx) => (
            <li key={idx}>{renderInline(item)}</li>
          ))}
        </ul>,
      );
      i = j;
      continue;
    }

    // Paragraph: consume until a blank line or the start of another block type.
    const paragraphLines: string[] = [];
    let j = i;
    while (
      j < lines.length &&
      lines[j].trim() !== "" &&
      !/^#{1,6}\s+/.test(lines[j]) &&
      !/^\s*-\s+/.test(lines[j]) &&
      !lines[j].trim().startsWith("|")
    ) {
      paragraphLines.push(lines[j]);
      j++;
    }
    blocks.push(
      <p key={key++} className="leading-relaxed text-muted-foreground">
        {renderInline(paragraphLines.join(" "))}
      </p>,
    );
    i = j;
  }

  return <div className="flex flex-col gap-1">{blocks}</div>;
}
