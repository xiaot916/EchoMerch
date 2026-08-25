function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\"/g, "&quot;").replace(/'/g, "&#39;")
}

function inlineMarkdown(value: string): string {
  let html = escapeHtml(value)
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
  html = html.replace(/__(.+?)__/g, "<strong>$1</strong>")
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>")
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
  return html
}

export function renderMarkdown(value: unknown): string {
  const source = String(value || "").replace(/\r\n?/g, "\n").trim()
  if (!source) return ""
  const lines = source.split("\n")
  const output: string[] = []
  let paragraph: string[] = []
  let listType: "ul" | "ol" | null = null
  let tableRows: string[][] = []

  const closeParagraph = () => {
    if (paragraph.length) {
      output.push(`<p>${paragraph.map(inlineMarkdown).join("<br>")}</p>`)
      paragraph = []
    }
  }
  const closeList = () => {
    if (listType) output.push(`</${listType}>`)
    listType = null
  }
  const closeTable = () => {
    if (!tableRows.length) return
    const [header, ...body] = tableRows
    output.push(`<div class="ai-markdown-table"><table><thead><tr>${header.map((cell) => `<th>${inlineMarkdown(cell)}</th>`).join("")}</tr></thead><tbody>${body.map((row) => `<tr>${header.map((_, index) => `<td>${inlineMarkdown(row[index] || "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`)
    tableRows = []
  }

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index].trim()
    const next = lines[index + 1]?.trim() || ""
    if (!line) {
      closeParagraph(); closeList(); closeTable(); continue
    }
    if (/^(?:\*\s*){3,}$|^(?:-\s*){3,}$|^(?:_\s*){3,}$/.test(line)) {
      closeParagraph(); closeList(); closeTable(); output.push("<hr>"); continue
    }
    if (/^>\s?/.test(line)) {
      closeParagraph(); closeList(); closeTable()
      const quoteLines = [line.replace(/^>\s?/, "")]
      while (index + 1 < lines.length && /^>\s?/.test(lines[index + 1].trim())) {
        index += 1
        quoteLines.push(lines[index].trim().replace(/^>\s?/, ""))
      }
      output.push(`<blockquote>${quoteLines.map(inlineMarkdown).join("<br>")}</blockquote>`)
      continue
    }
    const tableMatch = line.match(/^\|(.+)\|$/)
    if (tableMatch) {
      closeParagraph(); closeList()
      if (/^\|?\s*:?-{3,}/.test(next)) {
        tableRows.push(tableMatch[1].split("|").map((cell) => cell.trim()))
        index += 1
        continue
      }
      if (tableRows.length) {
        tableRows.push(tableMatch[1].split("|").map((cell) => cell.trim()))
        continue
      }
    }
    if (tableRows.length) closeTable()
    const heading = line.match(/^(#{1,6})\s+(.+)$/)
    if (heading) { closeParagraph(); closeList(); output.push(`<h${heading[1].length}>${inlineMarkdown(heading[2])}</h${heading[1].length}>`); continue }
    const unordered = line.match(/^[-*]\s+(.+)$/)
    const ordered = line.match(/^\d+[.)]\s+(.+)$/)
    if (unordered || ordered) {
      closeParagraph()
      const type = unordered ? "ul" : "ol"
      if (listType !== type) { closeList(); output.push(`<${type}>`); listType = type }
      output.push(`<li>${inlineMarkdown((unordered || ordered)![1])}</li>`)
      continue
    }
    closeList()
    if (/^```/.test(line)) {
      while (index + 1 < lines.length && !/^\s*```/.test(lines[index + 1])) index += 1
      index += 1
      continue
    }
    paragraph.push(line)
  }
  closeParagraph(); closeList(); closeTable()
  return output.join("")
}
