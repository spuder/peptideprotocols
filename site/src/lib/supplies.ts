export interface SupplyLine {
	item: string;
	schedule?: string | null;
	label: string;
	quantity_text: string;
	quantity?: number | null;
	unit?: string | null;
}

export interface SupplyGroup {
	emoji: string;
	name: string;
	rows: { label: string; quantityText: string }[];
}

const WATER_RE = /water/i;
const NAD_RE = /nad\+?/i;

// 🧪 for peptide vials, 💧 for bac/sterile water — placeholder emoji until
// these get replaced with real icons in the supply box too.
function emojiFor(item: string): string {
	return WATER_RE.test(item) ? "💧" : "🧪";
}

/** Full breakdown for the protocol detail page, grouped by supply item. */
export function groupSupplies(lines: SupplyLine[]): SupplyGroup[] {
	const groups = new Map<string, SupplyGroup>();
	for (const line of lines) {
		const name = line.item.replace(/:\s*$/, "").trim();
		if (!groups.has(name)) groups.set(name, { emoji: emojiFor(name), name, rows: [] });
		groups.get(name)!.rows.push({ label: line.label, quantityText: line.quantity_text });
	}
	return [...groups.values()];
}

/**
 * Real vial photo (site/public/images/vials/, transparent background) for
 * the header hero image — gold-cap 3 mL by default, blue-cap amber 5 mL
 * specifically for NAD+. Water is intentionally not handled here yet.
 */
export function peptideVialImage(peptideName: string): { src: string; alt: string } {
	if (NAD_RE.test(peptideName)) {
		return { src: "/images/vials/peptide-5ml.png", alt: "5 mL vial" };
	}
	return { src: "/images/vials/peptide-3ml.png", alt: "3 mL vial" };
}

/** Compact single-line figure for index cards: first peptide-vial row and first water row. */
export function quickSupplyBadge(lines: SupplyLine[]): { peptide: string | null; water: string | null } {
	const peptideRow = lines.find((l) => /vial/i.test(l.item) && !WATER_RE.test(l.item));
	const waterRow = lines.find((l) => WATER_RE.test(l.item));
	return {
		peptide: peptideRow?.quantity_text ?? null,
		water: waterRow?.quantity_text ?? null,
	};
}

/**
 * "How long does one vial last?" derived from the same peptide-vial rows
 * as the badges above (e.g. "8 weeks ≈: 8 vials" → 1 week/vial). Uses the
 * longest-duration row available, since site-supplied vial counts are
 * rounded up to whole vials and the rounding error shrinks as a share of
 * the total the longer the duration — so it's the least distorted ratio.
 */
export function vialLifespanWeeks(lines: SupplyLine[]): number | null {
	let best: { weeks: number; vials: number } | null = null;
	for (const line of lines) {
		if (WATER_RE.test(line.item) || !/vial/i.test(line.item)) continue;
		const weeksMatch = line.label.match(/(\d+)\s*weeks?/i);
		if (!weeksMatch || !line.quantity) continue;
		const weeks = Number(weeksMatch[1]);
		if (!best || weeks > best.weeks) best = { weeks, vials: line.quantity };
	}
	return best ? best.weeks / best.vials : null;
}

export function formatVialLifespan(weeks: number | null): string | null {
	if (weeks == null || !isFinite(weeks) || weeks <= 0) return null;
	const nearestInt = Math.round(weeks);
	const isClean = Math.abs(weeks - nearestInt) < 0.08;
	if (isClean) return `Lasts ${nearestInt} week${nearestInt === 1 ? "" : "s"}`;
	if (weeks < 1) return `Lasts ~${Math.round(weeks * 7)} days`;
	return `Lasts ~${Math.round(weeks * 10) / 10} weeks`;
}
