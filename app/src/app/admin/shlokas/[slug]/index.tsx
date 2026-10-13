/**
 * One shloka: edit its text, review notes, word-by-word analyses, and (advisor)
 * verify it. Editing verified text sends it back to review (enforced by the API
 * and the database); review notes can change without that.
 */
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { isAdvisor, useApi, useMe } from '@/api/ApiProvider';
import { describeError } from '@/api/client';
import type { ShlokaDetail, Word } from '@/api/types';
import { useReloadOnFocus } from '@/api/useReloadOnFocus';
import { useResource } from '@/api/useResource';
import { currentReading } from '@/console/morphology';
import { changedFields, type Draft, draftOf, resetsReview } from '@/console/shlokaDraft';
import {
  Badge,
  Button,
  Card,
  confirm,
  ErrorBox,
  Field,
  formatDate,
  Loading,
  Notice,
  Screen,
  VerifiedBadge,
} from '@/ui/components';
import { space, styles } from '@/ui/theme';

function WordCard({ slug, word }: { slug: string; word: Word }) {
  return (
    <View style={styles.card}>
      <View style={styles.row}>
        <Text style={styles.deva}>{word.surface_devanagari}</Text>
        <Text style={styles.text}>{word.surface_iast}</Text>
      </View>
      {word.analyses.length === 0 ? <Text style={styles.muted}>No analysis yet.</Text> : null}
      {word.analyses.map((a) => {
        const reading = currentReading(a.morphology);
        return (
          <Pressable
            key={a.id}
            accessibilityRole="link"
            onPress={() =>
              router.push({
                pathname: '/admin/shlokas/[slug]/analyses/[id]',
                params: { slug, id: a.id },
              })
            }
            style={({ pressed }) => ({
              gap: 2,
              opacity: pressed ? 0.7 : 1,
              paddingVertical: space.xs,
            })}
          >
            <View style={styles.row}>
              <Text style={[styles.text, { fontWeight: '600' }]}>{a.pada_iast}</Text>
              <VerifiedBadge verified={a.verified} />
              {a.morphology.chosen ? <Badge text="Reading chosen" tone="info" /> : null}
            </View>
            <Text style={styles.muted}>
              {reading?.label ?? 'No reading proposed'}
              {a.meaning ? ` · “${a.meaning}”` : ' · meaning missing'}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export default function ShlokaScreen() {
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const api = useApi();
  const shloka = useResource(() => api.getShloka(slug), [api, slug]);
  useReloadOnFocus(shloka.reload);

  if (shloka.loading && !shloka.data) return <Loading />;
  if (!shloka.data) {
    return (
      <Screen>
        <ErrorBox message={describeError(shloka.error)} onRetry={shloka.reload} />
      </Screen>
    );
  }
  // A new server copy (after save or verify) remounts the editor, so the form starts from it.
  return (
    <ShlokaEditor
      key={`${shloka.data.updated_at}|${shloka.data.verified}`}
      s={shloka.data}
      onSaved={shloka.setData}
    />
  );
}

function ShlokaEditor({ s, onSaved }: { s: ShlokaDetail; onSaved: (s: ShlokaDetail) => void }) {
  const api = useApi();
  const me = useMe();
  const [draft, setDraft] = useState<Draft>(() => draftOf(s));
  const [verifyNotes, setVerifyNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const changes = changedFields(s, draft);
  const dirty = Object.keys(changes).length > 0;
  const sendsBack = resetsReview(s, changes);
  const analyses = s.words.flatMap((w) => w.analyses);
  const unreviewed = analyses.filter((a) => !a.verified).length;

  async function run(action: () => Promise<ShlokaDetail>) {
    setBusy(true);
    setError(null);
    try {
      onSaved(await action());
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (
      sendsBack &&
      !(await confirm(
        'Send back to review?',
        'This shloka is verified. Changing its text hides it from learners until an advisor verifies it again.',
      ))
    )
      return;
    await run(() => api.editShloka(s.slug, changes));
  }

  async function verify() {
    if (
      unreviewed > 0 &&
      !(await confirm(
        'Some words are not reviewed',
        `${unreviewed} word analyses are not verified yet. Learners will not see their meanings until they are. Verify the shloka text anyway?`,
      ))
    )
      return;
    await run(() => api.verifyShloka(s.slug, verifyNotes.trim() || undefined));
    setVerifyNotes('');
  }

  const set = (k: keyof Draft) => (v: string) => setDraft({ ...draft, [k]: v });

  return (
    <Screen>
      <View style={[styles.row, { justifyContent: 'space-between' }]}>
        <Text style={styles.h1}>{s.title}</Text>
        <VerifiedBadge verified={s.verified} />
      </View>
      <Text style={styles.muted}>
        Source: {s.source.name} ({s.source.license}) · {s.source_ref}
        {s.verified ? ` · verified by ${s.verified_by} on ${formatDate(s.verified_at)}` : ''}
      </Text>
      {error ? <ErrorBox message={error} /> : null}

      <Card>
        <Text style={styles.h2}>Text</Text>
        <Field label="Title" value={draft.title} onChangeText={set('title')} />
        <Field
          label="Devanagari"
          value={draft.devanagari}
          onChangeText={set('devanagari')}
          multiline
        />
        <Field
          label="IAST"
          value={draft.iast}
          onChangeText={set('iast')}
          multiline
          autoCapitalize="none"
        />
        <Field
          label="Translation"
          value={draft.translation}
          onChangeText={set('translation')}
          multiline
        />
        <Field label="Source reference" value={draft.source_ref} onChangeText={set('source_ref')} />
        <Field
          label="Review notes"
          hint="Notes for reviewers (source issues, variants). Editing notes does not reset verification."
          value={draft.review_notes}
          onChangeText={set('review_notes')}
          multiline
        />
        {sendsBack ? (
          <Notice tone="warn">Saving will send this shloka back to review.</Notice>
        ) : null}
        <View style={styles.row}>
          <Button
            title={busy ? 'Saving…' : 'Save changes'}
            onPress={save}
            disabled={!dirty || busy}
          />
          <Button
            title="Discard"
            kind="secondary"
            onPress={() => setDraft(draftOf(s))}
            disabled={!dirty || busy}
          />
        </View>
      </Card>

      {isAdvisor(me.data?.role) && !s.verified ? (
        <Card>
          <Text style={styles.h2}>Verify</Text>
          <Text style={styles.text}>
            Verifying publishes this shloka to learners.{' '}
            {unreviewed === 0
              ? 'All word analyses are verified.'
              : `${unreviewed} of ${analyses.length} word analyses still need review.`}
          </Text>
          <Field
            label="Note (optional)"
            value={verifyNotes}
            onChangeText={setVerifyNotes}
            multiline
          />
          <Button title="Verify shloka" onPress={verify} disabled={dirty || busy} />
          {dirty ? <Text style={styles.muted}>Save or discard your edits first.</Text> : null}
        </Card>
      ) : null}

      <Text style={styles.h2}>
        Words ({analyses.length - unreviewed}/{analyses.length} reviewed)
      </Text>
      {s.words.map((w) => (
        <WordCard key={w.id} slug={s.slug} word={w} />
      ))}
      <Button
        title="Recordings of this shloka"
        kind="secondary"
        onPress={() => router.push({ pathname: '/admin/recordings', params: { shloka: s.slug } })}
      />
    </Screen>
  );
}
