/**
 * The scraper writes plain markdown with no frontmatter — title, source
 * URL, and scrape timestamp all live in the body text itself. Pull them
 * back out here so pages/cards can use them without re-parsing markdown
 * everywhere.
 */
export interface ProtocolMeta {
  title: string;
  sourceUrl: string | null;
  archivedAt: string | null;
  peptide: string | null;
  vialSize: string | null;
  vialSizeMg: number | null;
  /** "5 mg Vial" -> "5 mg" — the amount of material, not the container. */
  amountLabel: string | null;
  /** "BPC-157 (5 mg Vial)" -> "BPC-157 (5 mg)" — for page titles/headers. */
  displayTitle: string;
}

export function parseProtocolMeta(body: string, id: string): ProtocolMeta {
  const titleMatch = body.match(/^#\s+(.+)$/m);
  const sourceMatch = body.match(/^-\s+Source:\s*<?(\S+?)>?\s*$/m);
  // moveMetaToBottom() in content.config.ts relabels the scraper's raw
  // "Scraped:" line to "Archived:" before this ever runs.
  const archivedMatch = body.match(/^-\s+Archived:\s*(.+)$/m);

  // Titles look like "BPC-157 (5 mg Vial)" — split peptide name from vial size.
  const title = titleMatch?.[1]?.trim() ?? id;
  const sizeMatch = title.match(/^(.+?)\s*\(([^)]+)\)\s*$/);
  const vialSize = sizeMatch?.[2]?.trim() ?? null;
  const mgMatch = vialSize?.match(/([\d.]+)/);
  const peptide = sizeMatch?.[1]?.trim() ?? title;
  const amountLabel = vialSize?.replace(/\s*vial\s*$/i, "").trim() || vialSize;

  return {
    title,
    sourceUrl: sourceMatch?.[1]?.trim() ?? null,
    archivedAt: archivedMatch?.[1]?.trim() ?? null,
    peptide,
    vialSize,
    vialSizeMg: mgMatch ? Number(mgMatch[1]) : null,
    amountLabel,
    displayTitle: sizeMatch && amountLabel ? `${peptide} (${amountLabel})` : title,
  };
}
