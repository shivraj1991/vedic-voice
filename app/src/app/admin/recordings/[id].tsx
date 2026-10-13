/**
 * One recording: listen, verify (advisor), make it the active reference, and
 * label each word (ground truth for evaluating the scorer).
 */
import { useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import { useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Text, View } from 'react-native';

import { isAdvisor, useApi, useMe } from '@/api/ApiProvider';
import { describeError } from '@/api/client';
import type { AudioAssetDetail, WordLabel } from '@/api/types';
import { useResource } from '@/api/useResource';
import { ISSUE_CODES } from '@/console/issues';
import {
  Badge,
  Button,
  Card,
  Chip,
  ErrorBox,
  Field,
  formatDate,
  Loading,
  Notice,
  Screen,
} from '@/ui/components';
import { space, styles } from '@/ui/theme';

function Player({ assetId }: { assetId: string }) {
  const api = useApi();
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const player = useAudioPlayer(url ? { uri: url } : null);
  const status = useAudioPlayerStatus(player);

  async function load() {
    setError(null);
    try {
      setUrl((await api.playUrl(assetId)).url); // signed, expires in minutes
    } catch (e) {
      setError(describeError(e));
    }
  }

  return (
    <View style={styles.row}>
      {!url ? (
        <Button title="Load audio" kind="secondary" onPress={load} />
      ) : (
        <>
          <Button
            title={status.playing ? 'Pause' : 'Play'}
            onPress={() => (status.playing ? player.pause() : player.play())}
            disabled={!status.isLoaded}
          />
          <Button
            title="From start"
            kind="secondary"
            onPress={() => {
              void player.seekTo(0);
              player.play();
            }}
            disabled={!status.isLoaded}
          />
          <Text style={styles.muted}>
            {status.currentTime.toFixed(1)}s / {status.duration ? status.duration.toFixed(1) : '…'}s
          </Text>
        </>
      )}
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}

function LabelRow({
  assetId,
  word,
  label,
  onSaved,
}: {
  assetId: string;
  word: AudioAssetDetail['words'][number];
  label: WordLabel | undefined;
  onSaved: (l: WordLabel) => void;
}) {
  const api = useApi();
  const [ok, setOk] = useState<boolean | null>(label ? label.ok : null);
  const [issue, setIssue] = useState<string | null>(label?.issue_code ?? null);
  const [note, setNote] = useState(label?.note ?? '');
  const [state, setState] = useState<'idle' | 'saving' | 'saved' | string>('idle');

  const dirty =
    ok !== (label ? label.ok : null) ||
    issue !== (label?.issue_code ?? null) ||
    note !== (label?.note ?? '');

  async function save() {
    if (ok === null) return;
    const next: WordLabel = {
      shloka_word_id: word.id,
      ok,
      issue_code: ok ? null : issue,
      note: note.trim() || null,
    };
    setState('saving');
    try {
      await api.putLabel(assetId, next);
      onSaved(next);
      setState('saved');
    } catch (e) {
      setState(describeError(e));
    }
  }

  return (
    <View style={[styles.card, { gap: space.xs }]}>
      <View style={styles.row}>
        <Text style={styles.deva}>{word.surface_devanagari}</Text>
        <Text style={styles.text}>{word.surface_iast}</Text>
        {label ? (
          <Badge
            text={label.ok ? 'Labelled correct' : 'Labelled issue'}
            tone={label.ok ? 'ok' : 'warn'}
          />
        ) : null}
      </View>
      <View style={styles.row}>
        <Chip text="Correct" selected={ok === true} onPress={() => setOk(true)} />
        <Chip text="Needs work" selected={ok === false} onPress={() => setOk(false)} />
      </View>
      {ok === false ? (
        <View style={[styles.row, { gap: space.xs }]}>
          {ISSUE_CODES.map((i) => (
            <Chip
              key={i.code}
              text={i.label}
              selected={issue === i.code}
              onPress={() => setIssue(i.code)}
            />
          ))}
        </View>
      ) : null}
      {ok !== null ? <Field label="Note" value={note} onChangeText={setNote} /> : null}
      <View style={styles.row}>
        <Button
          title="Save label"
          kind="secondary"
          onPress={save}
          disabled={ok === null || !dirty || state === 'saving'}
        />
        {state === 'saved' && !dirty ? <Text style={styles.muted}>Saved</Text> : null}
        {state !== 'idle' && state !== 'saving' && state !== 'saved' ? (
          <Text style={styles.error}>{state}</Text>
        ) : null}
      </View>
    </View>
  );
}

export default function RecordingScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const api = useApi();
  const me = useMe();
  const asset = useResource(() => api.getAudio(id), [api, id]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (asset.loading && !asset.data) return <Loading />;
  if (!asset.data) {
    return (
      <Screen>
        <ErrorBox message={describeError(asset.error)} onRetry={asset.reload} />
      </Screen>
    );
  }
  const a = asset.data;

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      asset.reload();
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <View style={styles.row}>
        <Text style={styles.h1}>{a.shloka_title}</Text>
        <Badge text={a.kind} tone="info" />
        {a.verified ? (
          <Badge text="Verified" tone="ok" />
        ) : (
          <Badge text="Needs review" tone="warn" />
        )}
        {a.is_active_reference ? <Badge text="Active reference" tone="ok" /> : null}
      </View>
      <Text style={styles.muted}>
        {[a.reciter && `Reciter: ${a.reciter}`, a.license && `License: ${a.license}`, a.attribution]
          .filter(Boolean)
          .join(' · ')}{' '}
        · added {formatDate(a.created_at)}
      </Text>
      {error ? <ErrorBox message={error} /> : null}

      <Card>
        <Player assetId={a.id} />
        <View style={styles.row}>
          {isAdvisor(me.data?.role) && !a.verified ? (
            <Button
              title="Verify recording"
              onPress={() => act(() => api.verifyAudio(a.id))}
              disabled={busy}
            />
          ) : null}
          {a.kind === 'reference' && !a.is_active_reference ? (
            <Button
              title="Make active reference"
              kind="secondary"
              onPress={() => act(() => api.activateAudio(a.id))}
              disabled={busy || !a.verified}
            />
          ) : null}
        </View>
        {a.kind === 'reference' && !a.verified ? (
          <Text style={styles.muted}>
            An advisor must verify this recording before it can be made active.
          </Text>
        ) : null}
      </Card>

      <WordLabels key={a.id} asset={a} />
    </Screen>
  );
}

/** Labels start from the server copy; afterwards each saved row updates the local view. */
function WordLabels({ asset }: { asset: AudioAssetDetail }) {
  const [labels, setLabels] = useState<Record<string, WordLabel>>(() =>
    Object.fromEntries(asset.labels.map((l) => [l.shloka_word_id, l])),
  );
  return (
    <>
      <Text style={styles.h2}>
        Word labels ({Object.keys(labels).length}/{asset.words.length})
      </Text>
      <Notice>
        Your labels are ground truth for testing the scorer: mark each word correct or pick the
        issue you hear. Labels are kept per reviewer.
      </Notice>
      {asset.words.map((w) => (
        <LabelRow
          key={w.id}
          assetId={asset.id}
          word={w}
          label={labels[w.id]}
          onSaved={(l) => setLabels((prev) => ({ ...prev, [w.id]: l }))}
        />
      ))}
    </>
  );
}
