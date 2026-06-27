import { Pipe, PipeTransform } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatMarkdownTables(text: string): string {
  const lines = text.split('\n');
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      const tableLines: string[] = [];
      while (i < lines.length) {
        const row = lines[i].trim();
        if (!row.startsWith('|') || !row.endsWith('|')) {
          break;
        }
        tableLines.push(row);
        i += 1;
      }
      if (tableLines.length >= 2) {
        const header = tableLines[0];
        const bodyRows = tableLines.slice(2);
        const headerCells = header
          .split('|')
          .map((c) => escapeHtml(c.trim()))
          .filter(Boolean);
        let html =
          '<table class="chat-md-table"><thead><tr>' +
          headerCells.map((c) => `<th>${c}</th>`).join('') +
          '</tr></thead><tbody>';
        for (const row of bodyRows) {
          const cells = row
            .split('|')
            .map((c) => escapeHtml(c.trim()))
            .filter(Boolean);
          html += '<tr>' + cells.map((c) => `<td>${c}</td>`).join('') + '</tr>';
        }
        html += '</tbody></table>';
        out.push(html);
        continue;
      }
      out.push(escapeHtml(line));
      i += 1;
      continue;
    }
    out.push(escapeHtml(line));
    i += 1;
  }

  return out.join('\n');
}

@Pipe({ name: 'chatFormattedText', standalone: true })
export class ChatFormattedTextPipe implements PipeTransform {
  constructor(private readonly sanitizer: DomSanitizer) {}

  transform(value: string | null | undefined): SafeHtml {
    if (!value?.trim()) {
      return '';
    }
    let html = formatMarkdownTables(value);
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\n/g, '<br>');
    return this.sanitizer.bypassSecurityTrustHtml(html);
  }
}
