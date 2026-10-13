/**
 * Review one word analysis: pick the right grammatical reading from the
 * rule-based candidates (grouped by lemma, searchable) or enter one, write the
 * plain-language meaning, and (advisor) verify.
 */
import { useLocalSearchParams } from 'expo-router';
import { useMemo, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { isAdvisor, useApi, useMe } from '@/api/ApiProvider';
import { describeError } from '@/api/client';
import type { Analysis, Reading, Word } from '@/api/types';
import { useResource } from '@/api/useResource';
import {
  analysisChanges,
  currentReading,
  groupCandidates,
  manualReading,
  sameReading,
} from '@/console/morphology';
import {
  Badge,
  Button,
  Card,
  confirm,
  ErrorBox,
  Field,
  Loading,
  Notice,
  Screen,
  VerifiedBadge,
} from '@/ui/components';
import { colors, space, styles } from '@/ui/theme';

function ReadingOption({
  reading,
  selected,
  proposed,
  onPress,
}: {
  reading: Reading;
  selected: boolean;
  proposed: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ checked: selected }}
      onPress={onPress}
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: space.sm,
        padding: space.sm,
        borderRadius: 8,
        backgroundColor: selected ? colors.infoBg : 'transparent',
      }}
    >
      <Text style={{ fontSize: 16, color: selected ? colors.info : colors.muted }}>
        {selected ? '●' : '○'}
      </Text>
      <Text style={[styles.text, { flexShrink: 1 }]}>{reading.label}</Text>
      {proposed ? <Badge text="proposed" tone="info" /> : null}
    </Pressable>
  );
}

function CandidatePicker({
  analysis,
  chosen,
  onChoose,
}: {
  analysis: Analysis;
  chosen: Reading | null;
  onChoose: (r: Reading) => void;
}) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const groups = useMemo(
    () => groupCandidates(analysis.morphology, query),
    [analysis.morphology, query],
  );
  const total = analysis.morphology.candidates?.length ?? 0;
  const proposed = analysis.morphology.proposed ?? null;

  return (
    <Card>
      <Text style={styles.h2}>Grammatical reading</Text>
      <Text style={styles.muted}>
        {total} candidate readings from the rule-based analyser (
        {analysis.analysis_tool ?? 'unknown tool'}
        {analysis.morphology.status ? `, ${analysis.morphology.status}` : ''}). Pick the right one,
        or enter it below if it is missing.
      </Text>
      {total > 6 ? (
        <Field
          label="Search readings"
          placeholder="e.g. genitive singular, or a lemma"
          value={query}
          onChangeText={setQuery}
          autoCapitalize="none"
        />
      ) : null}
      {groups.length === 0 ? <Text style={styles.muted}>No candidate matches.</Text> : null}
      {groups.map((g, i) => {
        const expanded = open[g.lemma] ?? (i === 0 || query.length > 0 || g.readings.length <= 3);
        return (
          <View key={g.lemma} style={{ gap: 2 }}>
            <Pressable
              accessibilityRole="button"
              onPress={() => setOpen({ ...open, [g.lemma]: !expanded })}
              style={[styles.row, { paddingVertical: space.xs }]}
            >
              <Text style={[styles.text, { fontWeight: '600' }]}>
                {expanded ? '▾' : '▸'} {g.lemma}
              </Text>
              <Text style={styles.muted}>{g.readings.length} readings</Text>
            </Pressable>
            {expanded
              ? g.readings.map((r, j) => (
                  <ReadingOption
                    key={`${r.label}-${j}`}
                    reading={r}
                    selected={sameReading(r, chosen)}
                    proposed={sameReading(r, proposed)}
                    onPress={() => onChoose(r)}
                  />
                ))
              : null}
          </View>
        );
      })}
    </Card>
  );
}

function ManualEntry({ onUse }: { onUse: (r: Reading) => void }) {
  const [lemma, setLemma] = useState('');
  const [label, setLabel] = useState('');
  return (
    <Card>
      <Text style={styles.h2}>Enter a reading</Text>
      <Text style={styles.muted}>
        For forms the lexicon does not know (e.g. Vedic dhīmahi, pracodayāt). Write the lemma and
        the grammatical description.
      </Text>
      <Field label="Lemma" value={lemma} onChangeText={setLemma} autoCapitalize="none" />
      <Field
        label="Description"
        placeholder="e.g. dhī (root) 1st person plural, optative, middle"
        value={label}
        onChangeText={setLabel}
      />
      <Button
        title="Use this reading"
        kind="secondary"
        onPress={() => onUse(manualReading(lemma, label))}
        disabled={!label.trim()}
      />
    </Card>
  );
}

export default function AnalysisScreen() {
  const { slug, id } = useLocalSearchParams<{ slug: string; id: string }>();
  const api = useApi();
  const shloka = useResource(() => api.getShloka(slug), [api, slug]);
  const word = shloka.data?.words.find((w) => w.analyses.some((a) => a.id === id));
  const analysis = word?.analyses.find((a) => a.id === id);

  if (shloka.loading && !shloka.data) return <Loading />;
  if (!analysis || !word || !shloka.data) {
    return (
      <Screen>
        <ErrorBox
          message={shloka.error ? describeError(shloka.error) : 'This word analysis was not found.'}
          onRetry={shloka.reload}
        />
      </Screen>
    );
  }
  // A new server copy (after save or verify) remounts the editor, so the form starts from it.
  const version = [
    analysis.verified,
    analysis.meaning,
    analysis.explanation,
    analysis.morphology.chosen?.label,
  ].join('|');
  return (
    <AnalysisEditor
      key={`${analysis.id}|${version}`}
      analysis={analysis}
      word={word}
      shlokaTitle={shloka.data.title}
      onChanged={shloka.reload}
    />
  );
}

function AnalysisEditor({
  analysis,
  word,
  shlokaTitle,
  onChanged,
}: {
  analysis: Analysis;
  word: Word;
  shlokaTitle: string;
  onChanged: () => void;
}) {
  const api = useApi();
  const me = useMe();
  const [chosen, setChosen] = useState<Reading | null>(analysis.morphology.chosen ?? null);
  const [meaning, setMeaning] = useState(analysis.meaning ?? '');
  const [explanation, setExplanation] = useState(analysis.explanation ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const changes = analysisChanges(analysis, chosen, meaning, explanation);
  const dirty = Object.keys(changes).length > 0;
  const shown = chosen ?? currentReading(analysis.morphology);
  // Verification needs a saved, explicit choice: the analyser's proposal alone is not reviewed content.
  const ready = !!analysis.morphology.chosen && !!analysis.meaning?.trim();

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onChanged();
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (
      analysis.verified &&
      !(await confirm(
        'Send back to review?',
        'This analysis is verified. Saving changes needs an advisor to verify it again.',
      ))
    )
      return;
    await act(() => api.editAnalysis(analysis.id, changes));
  }

  return (
    <Screen>
      <View style={styles.row}>
        <Text style={styles.deva}>{word.surface_devanagari}</Text>
        <Text style={styles.h1}>{analysis.pada_iast}</Text>
        <VerifiedBadge verified={analysis.verified} />
      </View>
      <Text style={styles.muted}>
        Word {word.position + 1} of {shlokaTitle}
        {word.surface_iast !== analysis.pada_iast ? ` · part of “${word.surface_iast}”` : ''}
        {analysis.morphology.split_source
          ? ` · split from ${analysis.morphology.split_source}`
          : ''}
      </Text>
      {error ? <ErrorBox message={error} /> : null}

      <Card>
        <Text style={styles.label}>Learners will see</Text>
        <Text style={styles.text}>{shown?.label ?? 'No reading yet'}</Text>
        {!analysis.morphology.chosen && !chosen && analysis.morphology.proposed ? (
          <Text style={styles.muted}>
            This is the analyser&apos;s proposal (right only about 2 times in 3). Select the correct
            reading below.
          </Text>
        ) : null}
      </Card>

      <CandidatePicker analysis={analysis} chosen={chosen} onChoose={setChosen} />
      <ManualEntry onUse={setChosen} />

      <Card>
        <Text style={styles.h2}>Meaning</Text>
        <Field
          label="Meaning (short)"
          value={meaning}
          onChangeText={setMeaning}
          placeholder="e.g. that"
        />
        <Field
          label="Explanation (plain language)"
          value={explanation}
          onChangeText={setExplanation}
          multiline
        />
      </Card>

      {analysis.verified && dirty ? (
        <Notice tone="warn">Saving will send this analysis back to review.</Notice>
      ) : null}
      <View style={styles.row}>
        <Button title={busy ? 'Saving…' : 'Save'} onPress={save} disabled={!dirty || busy} />
        {isAdvisor(me.data?.role) && !analysis.verified ? (
          <Button
            title="Verify"
            onPress={() => act(() => api.verifyAnalysis(analysis.id))}
            disabled={dirty || busy || !ready}
          />
        ) : null}
      </View>
      {isAdvisor(me.data?.role) && !analysis.verified && (dirty || !ready) ? (
        <Text style={styles.muted}>
          {dirty
            ? 'Save your changes before verifying.'
            : 'Choose a reading (select the proposed one if it is right) and add a meaning, then save, before verifying.'}
        </Text>
      ) : null}
    </Screen>
  );
}
