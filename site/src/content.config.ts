import { defineCollection, z } from "astro:content";
import type { Loader, LoaderContext } from "astro/loaders";
import fs from "node:fs/promises";
import { fileURLToPath } from "node:url";

// Source of truth stays in ../markdown (written by the Python scraper in
// scraper/core.py). Every field is derived from the body text at render
// time (see src/lib/meta.ts) since the scraper writes plain markdown with
// no frontmatter.
const MARKDOWN_DIR = new URL("../../markdown/", import.meta.url);

// The scraper puts "- Source: ... / - Scraped: ..." right under the H1.
// That reads better at the bottom of the page (and "Scraped" reads harsh
// for a public-facing page), so move it there and relabel it — without
// touching the scraper's output on disk.
function moveMetaToBottom(raw: string): string {
	const match = raw.match(/^(#[^\n]*\n)\n((?:-\s+(?:Source|Scraped):.*\n)+)\n?/);
	if (!match) return raw;
	const [full, heading, metaBlock] = match;
	const rest = raw.slice(full.length);
	const relabeled = metaBlock.replace(/^-\s+Scraped:/m, "- Archived:");
	return `${heading}\n${rest.trimEnd()}\n\n---\n\n${relabeled.trimEnd()}\n`;
}

// write_markdown() in scraper/core.py always emits a "### <category>"
// subheading under "## References", and for every current source the only
// category is literally "References" — producing a duplicated heading.
// Collapse that specific case; leave genuinely distinct categories
// (e.g. "Additional Technical References") alone.
function collapseDuplicateReferencesHeading(raw: string): string {
	return raw.replace(/^## References\n\n### References\n/m, "## References\n\n");
}

// The scraper's prose sometimes cites references inline as bare "[3]"
// markers (matching data/json's reference[2].ref_id "ref-3", 1-indexed) but
// writes them as plain text, not links. Turn them into anchors pointing at
// the matching bullet in the References list, numbered in document order.
function linkReferenceMarkers(html: string): string {
	const refsHeadingMatch = html.match(/<h2[^>]*id="references"[^>]*>[\s\S]*?<\/h2>/);
	if (!refsHeadingMatch) return html;
	const refsStart = refsHeadingMatch.index! + refsHeadingMatch[0].length;
	const before = html.slice(0, refsStart);
	let refsSection = html.slice(refsStart);
	let n = 0;
	refsSection = refsSection.replace(/<li>/g, () => `<li id="ref-${++n}">`);
	const linkedBefore = before.replace(/\[(\d+)\]/g, (marker, num) =>
		Number(num) <= n ? `<a class="ref-marker" href="#ref-${num}">${marker}</a>` : marker,
	);
	return linkedBefore + refsSection;
}

function protocolsLoader(): Loader {
	return {
		name: "protocols-loader",
		load: async (context: LoaderContext) => {
			const dir = fileURLToPath(MARKDOWN_DIR);
			const files = await fs.readdir(dir);
			context.store.clear();
			for (const file of files) {
				if (!file.endsWith(".md")) continue;
				const id = file.replace(/\.md$/, "");
				const fileURL = new URL(file, MARKDOWN_DIR);
				const raw = await fs.readFile(fileURLToPath(fileURL), "utf-8");
				const body = collapseDuplicateReferencesHeading(moveMetaToBottom(raw));
				const rendered = await context.renderMarkdown(body, { fileURL });
				rendered.html = linkReferenceMarkers(rendered.html);
				const data = await context.parseData({ id, data: {} });
				context.store.set({ id, body, data, rendered });
			}
		},
	};
}

const protocols = defineCollection({
	loader: protocolsLoader(),
	schema: z.object({}).passthrough(),
});

// The scraper's canonical structured snapshot: data/json/<domain>/<slug>.json
// (see scraper/models.py PageRecord). Used for the vial/bac-water counts —
// more reliable than re-parsing the markdown's prose Supplies section.
const DATA_JSON_DIR = new URL("../../data/json/", import.meta.url);

async function walkJsonFiles(dir: string): Promise<string[]> {
	const entries = await fs.readdir(dir, { withFileTypes: true });
	const files: string[] = [];
	for (const entry of entries) {
		const full = `${dir}/${entry.name}`;
		if (entry.isDirectory()) files.push(...(await walkJsonFiles(full)));
		else if (entry.name.endsWith(".json")) files.push(full);
	}
	return files;
}

function suppliesLoader(): Loader {
	return {
		name: "supplies-loader",
		load: async (context: LoaderContext) => {
			const dir = fileURLToPath(DATA_JSON_DIR);
			const files = await walkJsonFiles(dir);
			context.store.clear();
			for (const filePath of files) {
				const id = filePath.split("/").pop()!.replace(/\.json$/, "");
				const raw = await fs.readFile(filePath, "utf-8");
				const json = JSON.parse(raw);
				const data = await context.parseData({ id, data: json });
				context.store.set({ id, data });
			}
		},
	};
}

const supplyLineSchema = z.object({
	item: z.string(),
	schedule: z.string().nullable().optional(),
	label: z.string(),
	quantity_text: z.string(),
	quantity: z.number().nullable().optional(),
	unit: z.string().nullable().optional(),
});

const supplies = defineCollection({
	loader: suppliesLoader(),
	schema: z.object({
		peptide: z.string().optional(),
		vial_size_text: z.string().optional(),
		supplies: z.array(supplyLineSchema).default([]),
	}).passthrough(),
});

export const collections = { protocols, supplies };
