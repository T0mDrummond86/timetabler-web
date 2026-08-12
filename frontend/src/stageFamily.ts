/** Grouping a split qualification back into the one thing it is.
 *
 * A stage is its own qualification record so it can be timetabled on its own,
 * but in a qualification list that is an implementation detail: the user wrote
 * one qualification and expects to see one. Every stage of a family shares a
 * parent id (stage one points at itself), so grouping is a single key.
 */
import type { Qualification } from "./api";

/** "Dip of IT Stg2" -> "Dip of IT". Matches the backend's family_title rule. */
const STAGE_SUFFIX = /\s*St(?:a?ge?)?\s*\d+\s*$/i;

export function stripStageSuffix(name: string): string {
  return name.replace(STAGE_SUFFIX, "").trim() || name;
}

export type QualificationFamily = {
  /** The parent id for a split family; the qualification's own id otherwise. */
  key: number;
  /** What the list shows: the family name, or the qualification's own name. */
  label: string;
  /** One entry when never split; every stage in name order when split. */
  stages: Qualification[];
  isSplit: boolean;
};

/**
 * Collapse a flat qualification list into families, keeping the incoming order
 * of first appearance so the list does not reshuffle when a split happens.
 */
export function groupIntoFamilies(quals: Qualification[]): QualificationFamily[] {
  const byKey = new Map<number, Qualification[]>();
  const order: number[] = [];
  for (const q of quals) {
    const key = q.parent_qualification_id || q.id;
    if (!byKey.has(key)) {
      byKey.set(key, []);
      order.push(key);
    }
    byKey.get(key)!.push(q);
  }
  return order.map((key) => {
    // By id, not by name: the split creates stage one first (it keeps the
    // original record) then the rest in order, so ids are the stage order and
    // stay put when a stage is renamed. Sorting by name would let a rename
    // reshuffle the stage tabs under the user.
    const stages = byKey.get(key)!.slice().sort((a, b) => a.id - b.id);
    // A family of one is just a qualification — it keeps its own name, since
    // stripping a suffix from an unsplit "Cert IV Stage 2" would be wrong.
    const isSplit = stages.length > 1;
    // The root record is the family's name, so renaming a later stage does not
    // rename the whole qualification in the list.
    const root = stages.find((s) => s.id === key) ?? stages[0];
    return {
      key,
      label: isSplit ? stripStageSuffix(root.name) : root.name,
      stages,
      isSplit,
    };
  });
}

/** The family a given qualification id belongs to, if any. */
export function familyOf(
  families: QualificationFamily[],
  qualificationId: number | null,
): QualificationFamily | undefined {
  if (qualificationId == null) return undefined;
  return families.find((f) => f.stages.some((s) => s.id === qualificationId));
}
