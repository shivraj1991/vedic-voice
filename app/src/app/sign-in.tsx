/** Sign-in: Clerk (hosted on native, prebuilt form on web) or a pasted dev token. */
import { Redirect } from 'expo-router';
import { useState } from 'react';
import { Text } from 'react-native';

import { ClerkSignIn } from '@/auth/ClerkSignIn';
import { useSession } from '@/auth/session';
import { Button, Card, Field, Loading, Notice, Screen } from '@/ui/components';
import { styles } from '@/ui/theme';

function DevTokenSignIn({ onToken }: { onToken: (t: string) => void }) {
  const [token, setToken] = useState('');
  return (
    <Card>
      <Notice tone="warn">
        Development sign-in. Paste a simulated token from `uv run python -m vv_backend.devtools
        token --role advisor`. Not available in production builds, and the server refuses simulated
        tokens in production.
      </Notice>
      <Field
        label="Session token"
        value={token}
        onChangeText={setToken}
        autoCapitalize="none"
        autoCorrect={false}
        multiline
        secureTextEntry={false}
      />
      <Button title="Sign in" onPress={() => onToken(token)} disabled={!token.trim()} />
    </Card>
  );
}

export default function SignIn() {
  const session = useSession();
  if (session.status === 'loading') return <Loading />;
  if (session.status === 'signedIn') return <Redirect href="/" />;
  return (
    <Screen>
      <Text style={styles.h1}>Vedic Voice</Text>
      {session.mode === 'dev' && session.signInWithToken ? (
        <DevTokenSignIn onToken={session.signInWithToken} />
      ) : (
        <ClerkSignIn />
      )}
    </Screen>
  );
}
