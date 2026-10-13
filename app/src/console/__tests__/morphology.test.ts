import {
  analysisChanges,
  currentReading,
  fold,
  groupCandidates,
  manualReading,
  withChoice,
} from '@/console/morphology';
import { analysis, TA_GEN, TAT_ACC, TAT_NOM } from '@/test/fixtures';

describe('currentReading', () => {
  it('prefers the advisor choice over the proposal, like the learner view', () => {
    const m = analysis().morphology;
    expect(currentReading(m)).toEqual(TAT_NOM);
    expect(currentReading({ ...m, chosen: TAT_ACC })).toEqual(TAT_ACC);
    expect(currentReading({})).toBeNull();
  });
});

describe('groupCandidates', () => {
  const m = analysis().morphology;

  it('groups by lemma with the proposed lemma first', () => {
    const groups = groupCandidates(m);
    expect(groups.map((g) => g.lemma)).toEqual(['tad', 'ta']);
    expect(groups[0]?.readings).toEqual([TAT_NOM, TAT_ACC]);
  });

  it('filters with every search term, ignoring case and diacritics', () => {
    expect(groupCandidates(m, 'ACCUSATIVE')).toEqual([{ lemma: 'tad', readings: [TAT_ACC] }]);
    expect(groupCandidates(m, 'ta genitive')).toEqual([{ lemma: 'ta', readings: [TA_GEN] }]);
    expect(groupCandidates(m, 'dative')).toEqual([]);
    expect(fold('dhīmahi Ṛṇa')).toBe('dhimahi rna');
  });
});

describe('choosing a reading', () => {
  it('stores the choice and keeps the pipeline data for provenance', () => {
    const m = withChoice(analysis().morphology, TAT_ACC);
    expect(m.chosen).toEqual(TAT_ACC);
    expect(m.candidates).toHaveLength(3);
    expect(withChoice(m, null).chosen).toBeUndefined();
  });

  it('records a manual reading for forms the lexicon does not know', () => {
    expect(manualReading(' dhī ', ' optative 1pl ')).toEqual({
      kind: 'manual',
      lemma: 'dhī',
      label: 'optative 1pl',
    });
    expect(manualReading('', 'x').lemma).toBeNull();
  });
});

describe('analysisChanges', () => {
  const a = analysis();

  it('sends nothing when nothing changed', () => {
    expect(analysisChanges(a, null, '', '')).toEqual({});
  });

  it('sends the chosen reading, its lemma if different, and edited text', () => {
    const changes = analysisChanges(a, TA_GEN, 'that', '');
    expect(changes.morphology?.chosen).toEqual(TA_GEN);
    expect(changes.lemma).toBe('ta');
    expect(changes.meaning).toBe('that');
    expect(changes).not.toHaveProperty('explanation');
  });

  it('does not resend an unchanged choice', () => {
    const chosen = analysis({ morphology: { ...a.morphology, chosen: TAT_NOM } });
    expect(analysisChanges(chosen, { ...TAT_NOM }, '', '')).toEqual({});
  });
});
