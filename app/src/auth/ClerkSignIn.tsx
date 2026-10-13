/**
 * Native sign-in: Clerk's hosted Account Portal in an in-app browser. Supports
 * every sign-in method enabled in the Clerk dashboard without custom UI.
 */
import { useHostedAuth } from '@clerk/expo/hosted-auth';
import { useState } from 'react';
import { Text } from 'react-native';

import { Button } from '@/ui/components';
import { styles } from '@/ui/theme';

export function ClerkSignIn() {
  const { startHostedAuth } = useHostedAuth();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const { createdSessionId } = await startHostedAuth({ mode: 'sign-in' });
      if (!createdSessionId) setError('Sign-in was cancelled.');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button title={busy ? 'Opening…' : 'Sign in'} onPress={start} disabled={busy} />
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </>
  );
}
