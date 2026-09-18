import type { ReactNode } from 'react';

interface MarkdownMessageProps {
  content: string;
  sourceRefs?: SourceReference[];
  onSourceClick?: (sourceId: string) => void;
  shouldHighlightBlock?: (text: string) => boolean;
}

export interface SourceReference {
  sourceId: string;
  number: number;
}

export function MarkdownMessage({
  content,
  sourceRefs = [],
  onSourceClick,
  shouldHighlightBlock,
}: MarkdownMessageProps) {
  const blocks = parseBlocks(resolveDownloadUrl(content));
  return (
    <div className="markdown-message">
      {blocks.map((block, index) =>
        renderBlock(block, index, sourceRefs, onSourceClick, shouldHighlightBlock),
      )}
    </div>
  );
}

type MarkdownBlock =
  | { type: 'heading'; level: 1 | 2 | 3 | 4 | 5 | 6; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'quote'; text: string }
  | { type: 'list'; ordered: boolean; items: string[] }
  | { type: 'code'; text: string }
  | { type: 'table'; headers: string[]; rows: string[][] };

function parseBlocks(markdown: string): MarkdownBlock[] {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n');
  const blocks: MarkdownBlock[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let code: string[] | null = null;

  function flushParagraph() {
    if (paragraph.length === 0) return;
    blocks.push({ type: 'paragraph', text: paragraph.join('\n') });
    paragraph = [];
  }

  function flushList() {
    if (!list) return;
    blocks.push({ type: 'list', ordered: list.ordered, items: list.items });
    list = null;
  }

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.trim().startsWith('```')) {
      flushParagraph();
      flushList();
      if (code) {
        blocks.push({ type: 'code', text: code.join('\n') });
        code = null;
      } else {
        code = [];
      }
      continue;
    }
    if (code) {
      code.push(line);
      continue;
    }

    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }

    const table = parseTable(lines, index);
    if (table) {
      flushParagraph();
      flushList();
      blocks.push({ type: 'table', headers: table.headers, rows: table.rows });
      index = table.nextIndex - 1;
      continue;
    }

    const heading = /^(#{1,6})\s+(.+)$/.exec(line);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({
        type: 'heading',
        level: heading[1].length as 1 | 2 | 3 | 4 | 5 | 6,
        text: heading[2],
      });
      continue;
    }

    const unordered = /^\s*[-*]\s+(.+)$/.exec(line);
    const ordered = /^\s*\d+[.)]\s+(.+)$/.exec(line);
    if (unordered || ordered) {
      flushParagraph();
      const isOrdered = Boolean(ordered);
      if (!list || list.ordered !== isOrdered) {
        flushList();
        list = { ordered: isOrdered, items: [] };
      }
      list.items.push((unordered ?? ordered)?.[1] ?? '');
      continue;
    }

    const quote = /^\s*>\s?(.+)$/.exec(line);
    if (quote) {
      flushParagraph();
      flushList();
      blocks.push({ type: 'quote', text: quote[1] });
      continue;
    }

    flushList();
    paragraph.push(line);
  }

  if (code) blocks.push({ type: 'code', text: code.join('\n') });
  flushParagraph();
  flushList();
  return blocks;
}

function renderBlock(
  block: MarkdownBlock,
  index: number,
  sourceRefs: SourceReference[],
  onSourceClick?: (sourceId: string) => void,
  shouldHighlightBlock?: (text: string) => boolean,
) {
  switch (block.type) {
    case 'heading': {
      const Tag = `h${Math.min(block.level + 2, 6)}` as 'h3' | 'h4' | 'h5' | 'h6';
      return <Tag key={index}>{renderInline(block.text, sourceRefs, onSourceClick)}</Tag>;
    }
    case 'paragraph':
      return (
        <p className={highlightClass(block.text, shouldHighlightBlock)} key={index}>
          {renderInline(block.text, sourceRefs, onSourceClick)}
        </p>
      );
    case 'quote':
      return <blockquote key={index}>{renderInline(block.text, sourceRefs, onSourceClick)}</blockquote>;
    case 'list': {
      const Tag = block.ordered ? 'ol' : 'ul';
      return (
        <Tag key={index}>
          {block.items.map((item, itemIndex) => (
            <li key={`${index}-${itemIndex}`}>{renderInline(item, sourceRefs, onSourceClick)}</li>
          ))}
        </Tag>
      );
    }
    case 'code':
      return <pre key={index}><code>{block.text}</code></pre>;
    case 'table':
      return (
        <div className="markdown-table-wrap" key={index}>
          <table>
            <thead>
              <tr>
                {block.headers.map((header, headerIndex) => (
                  <th key={`${index}-h-${headerIndex}`}>
                    {renderInline(header, sourceRefs, onSourceClick)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, rowIndex) => (
                <tr key={`${index}-r-${rowIndex}`}>
                  {block.headers.map((_, cellIndex) => (
                    <td key={`${index}-r-${rowIndex}-${cellIndex}`}>
                      {renderInline(row[cellIndex] ?? '', sourceRefs, onSourceClick)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
  }
}

function highlightClass(
  text: string,
  shouldHighlightBlock?: (text: string) => boolean,
): string | undefined {
  return shouldHighlightBlock?.(text) ? 'is-highlighted' : undefined;
}

function parseTable(lines: string[], startIndex: number) {
  const header = splitTableRow(lines[startIndex]);
  const separator = splitTableRow(lines[startIndex + 1] ?? '');
  if (!header || !separator || header.length === 0 || separator.length !== header.length) {
    return null;
  }
  if (!separator.every((cell) => /^:?-{3,}:?$/.test(cell.trim()))) {
    return null;
  }

  const rows: string[][] = [];
  let nextIndex = startIndex + 2;
  while (nextIndex < lines.length) {
    const row = splitTableRow(lines[nextIndex]);
    if (!row || row.length === 0) break;
    rows.push(row);
    nextIndex += 1;
  }
  return { headers: header, rows, nextIndex };
}

function splitTableRow(line: string): string[] | null {
  const trimmed = line.trim();
  if (!trimmed.includes('|')) return null;
  return trimmed
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim());
}

function renderInline(
  text: string,
  sourceRefs: SourceReference[] = [],
  onSourceClick?: (sourceId: string) => void,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  const sourcePattern = sourceRefs.length
    ? sourceRefs.map((item) => escapeRegExp(item.sourceId)).join('|')
    : '';
  const pattern = new RegExp(
    `(\\[[^\\]]+\\]\\([^)]+\\)|\\*\\*[^*]+\\*\\*|\`[^\`]+\`${sourcePattern ? `|\\[?(?:${sourcePattern})\\]?` : ''})`,
    'g',
  );
  let lastIndex = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const token = match[0];
    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
    if (link) {
      nodes.push(
        <a key={match.index} href={resolveDownloadUrl(link[2])} target="_blank" rel="noreferrer">
          {resolveDownloadUrl(link[1])}
        </a>,
      );
    } else if (token.startsWith('**')) {
      nodes.push(<strong key={match.index}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith('`')) {
      nodes.push(<code key={match.index}>{token.slice(1, -1)}</code>);
    } else {
      const sourceId = token.replace(/^\[/, '').replace(/\]$/, '');
      const source = sourceRefs.find((item) => item.sourceId === sourceId);
      if (source) {
        nodes.push(
          <button
            className="source-citation"
            key={match.index}
            type="button"
            onClick={() => onSourceClick?.(source.sourceId)}
          >
            [{source.number}]
          </button>,
        );
      } else {
        nodes.push(token);
      }
    }
    lastIndex = match.index + token.length;
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes;
}

function resolveDownloadUrl(content: string): string {
  return content
    .replace(/\\?\{\s*\\?\{\s*download_(?:url|uri)\s*\\?\}\s*\\?\}/g, CLAIM_FORM_DOWNLOAD_URL)
    .replace(/\\?\{\s*download_(?:url|uri)\s*\\?\}/g, CLAIM_FORM_DOWNLOAD_URL)
    .replace(/%7Bdownload_(?:url|uri)%7D/gi, CLAIM_FORM_DOWNLOAD_URL);
}

const CLAIM_FORM_DOWNLOAD_URL = '/business-api/api/v1/claim-guides/application-form';

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
