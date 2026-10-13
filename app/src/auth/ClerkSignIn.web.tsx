/** Web sign-in (admin console in a browser): Clerk's prebuilt sign-in form. */
import { SignIn } from '@clerk/expo/web';

export function ClerkSignIn() {
  return <SignIn routing="hash" />;
}
