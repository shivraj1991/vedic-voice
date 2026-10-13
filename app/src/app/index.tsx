/**
 * Home. Staff (admin/advisor) get the console; the learner experience arrives in
 * Milestone 3.
 */
import { Redirect, router } from 'expo-router';
import { Text } from 'react-native';

import { isStaff, useMe } from '@/api/ApiProvider';
import { describeError } from '@/api/client';
import { useSession } from '@/auth/session';
import { Button, Card, ErrorBox, Loading, Screen } from '@/ui/components';
import { styles } from '@/ui/theme';

export default function Home() {
  const session = useSession();
  const me = useMe();

  if (session.status === 'loading') return <Loading />;
  if (session.status === 'signedOut') return <Redirect href="/sign-in" />;
  if (me.loading && !me.data) return <Loading />;

  return (
    <Screen>
      {me.error ? <ErrorBox message={describeError(me.error)} onRetry={me.reload} /> : null}
      {me.data ? (
        <Card>
          <Text style={styles.h2}>Signed in</Text>
          <Text style={styles.text}>Role: {me.data.role}</Text>
          {isStaff(me.data.role) ? (
            <Button title="Open the console" onPress={() => router.push('/admin')} />
          ) : (
            <Text style={styles.muted}>
              The learner app (listen, record, feedback) arrives in the next milestone.
            </Text>
          )}
        </Card>
      ) : null}
      <Button title="Sign out" kind="secondary" onPress={() => void session.signOut()} />
    </Screen>
  );
}
