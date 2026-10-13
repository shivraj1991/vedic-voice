/** Readable change-history lines from content_audit diffs. */

/** One line per changed field: `field: before → after`. */
export function describeDiff(diff: Record<string, unknown>): string[] {
  return Object.entries(diff).map(([field, value]) => {
    if (field === 'morphology' && Array.isArray(value) && value.length === 2) {
      const [before, after] = value.map((m) => chosenLabel(m));
      return `reading: ${before} → ${after}`;
    }
    if (Array.isArray(value) && value.length === 2) {
      const [before, after] = value.map((v) => short(v));
      return `${field}: ${before} → ${after}`;
    }
    return `${field}: ${short(value)}`;
  });
}

function short(v: unknown): string {
  const s = typeof v === 'string' ? v : JSON.stringify(v);
  return s.length > 80 ? `${s.slice(0, 77)}…` : s;
}

/** Morphology diffs are large JSON; what changes in review is the chosen reading. */
function chosenLabel(m: unknown): string {
  const chosen = (m as { chosen?: { label?: string } } | null)?.chosen;
  return chosen?.label ?? '(not chosen)';
}
