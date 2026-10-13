/** Console home: every shloka (drafts included) with its review progress. */
import { router } from 'expo-router';
import { Pressable, Text, View } from 'react-native';

import { isAdvisor, useApi, useMe } from '@/api/ApiProvider';
import { describeError } from '@/api/client';
import type { ShlokaSummary } from '@/api/types';
import { useReloadOnFocus } from '@/api/useReloadOnFocus';
import { useResource } from '@/api/useResource';
import { Badge, Button, ErrorBox, Loading, Screen, VerifiedBadge } from '@/ui/components';
import { space, styles } from '@/ui/theme';

function ShlokaRow({ s }: { s: ShlokaSummary }) {
  const done = s.analyses > 0 && s.analyses_verified === s.analyses;
  return (
    <Pressable
      accessibilityRole="link"
      onPress={() => router.push({ pathname: '/admin/shlokas/[slug]', params: { slug: s.slug } })}
      style={({ pressed }) => [styles.card, { opacity: pressed ? 0.8 : 1 }]}
    >
      <View style={[styles.row, { justifyContent: 'space-between' }]}>
        <Text style={styles.h2}>{s.title}</Text>
        <VerifiedBadge verified={s.verified} />
      </View>
      <View style={styles.row}>
        <Badge
          text={`Words reviewed ${s.analyses_verified}/${s.analyses}`}
          tone={done ? 'ok' : 'info'}
        />
        <Text style={styles.muted}>{s.slug}</Text>
      </View>
    </Pressable>
  );
}

export default function ShlokaList() {
  const api = useApi();
  const me = useMe();
  const shlokas = useResource(() => api.listShlokas(), [api]);
  useReloadOnFocus(shlokas.reload);

  const pending = shlokas.data?.filter((s) => !s.verified).length ?? 0;
  return (
    <Screen>
      <View style={[styles.row, { justifyContent: 'space-between' }]}>
        <Text style={styles.muted}>
          Signed in as {me.data?.role}
          {isAdvisor(me.data?.role) ? ' (can verify)' : ' (can edit; an advisor verifies)'}
        </Text>
        <View style={[styles.row, { gap: space.sm }]}>
          <Button
            title="Recordings"
            kind="secondary"
            onPress={() => router.push('/admin/recordings')}
          />
          <Button title="History" kind="secondary" onPress={() => router.push('/admin/audit')} />
        </View>
      </View>
      {shlokas.data ? (
        <Text style={styles.text}>
          {pending === 0
            ? 'All shlokas are verified.'
            : `${pending} of ${shlokas.data.length} shlokas need review. Learners only see verified shlokas.`}
        </Text>
      ) : null}
      {shlokas.error ? (
        <ErrorBox message={describeError(shlokas.error)} onRetry={shlokas.reload} />
      ) : null}
      {shlokas.loading && !shlokas.data ? <Loading /> : null}
      {shlokas.data?.map((s) => (
        <ShlokaRow key={s.slug} s={s} />
      ))}
    </Screen>
  );
}
