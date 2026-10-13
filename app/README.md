# app — Expo app (learner + admin/advisor console)

React Native + Expo (SDK 57, TypeScript, expo-router). Routes live in `src/app/`;
everything else (API client, auth, review logic, UI kit) is outside it.

- **Console (Milestone 3b)**, role-gated under `/admin`, phone and web:
  - shloka list with review progress;
  - edit text, translation and review notes; advisors verify;
  - word analyses: pick the rule-based reading (grouped by lemma, searchable,
    diacritic-insensitive) or enter one; meaning and explanation; advisors verify;
  - recordings: upload (direct to R2 via signed URL), listen, verify, make the active
    reference, per-word ground-truth labels;
  - change history (`content_audit`).
- **Learner app (Milestone 3)**: not started; signed-in learners see a placeholder.

Roles come from the server (`GET /me`, i.e. the verified Clerk token). The API enforces
every rule; the console only hides what would be refused and explains why.

## Run

```
npm install
cp .env.example .env        # then fill in (see below)
npm run web                 # console in the browser at http://localhost:8081
npm start                   # Expo dev server (phone: development build, see below)
```

`.env` (only public values; it is gitignored anyway):

| Variable | Value |
|---|---|
| `EXPO_PUBLIC_API_URL` | backend URL, e.g. `http://localhost:8000` |
| `EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY` | from `backend/config/clerk.dev.public.env` |
| `EXPO_PUBLIC_DEV_AUTH` | `1` = sign in by pasting a simulated token (dev builds only, and only without a Clerk key) |

### Local console without Clerk (simulated tokens)

```
# backend (see backend/README.md): local Postgres, migrated + seeded, then
cd backend && uv run python -m vv_backend.devtools init
VV_ENV=dev VV_DEV_JWKS_PATH=.dev-keys/jwks.json CLERK_ISSUER=https://dev.clerk.local \
  CLERK_AUTHORIZED_PARTIES=http://localhost:8081 CORS_ORIGINS=http://localhost:8081 \
  DATABASE_URL=postgresql://... uv run --with uvicorn uvicorn --factory vv_backend.api.app:create_app
uv run python -m vv_backend.devtools token --role advisor     # paste into the sign-in screen

# app
cd app && EXPO_PUBLIC_API_URL=http://localhost:8000 EXPO_PUBLIC_DEV_AUTH=1 npm run web
```

Simulated tokens are kept in memory only (a page reload signs out) and are refused by
the backend when `VV_ENV=prod`.

### With Clerk

Web uses Clerk's sign-in form; iOS/Android use Clerk's hosted sign-in in an in-app
browser (`useHostedAuth`). Native needs a development build (Clerk and expo-secure-store
have native code): `npx expo run:ios|android` or `eas build --profile development`.
In the Clerk dashboard:

- **Sessions → Customize session token**: add `"role": "{{user.public_metadata.role}}"`.
- **Users → (user) → Public metadata**: `{"role": "advisor"}` or `{"role": "admin"}`.
- The backend's `CLERK_AUTHORIZED_PARTIES` must list every web origin of the console.

### Recordings

Uploads and playback need R2 configured on the backend (otherwise the console says
so). Browser uploads PUT straight to R2, so the bucket needs a CORS rule allowing `PUT`
(header `Content-Type`) and `GET` from the console's web origin.

## Check

```
npm run typecheck && npx eslint . && npm run format && npm test
npx expo export -p web       # production web build (CI does this)
```

Tests: review logic and API client (unit), and console screens end to end through
expo-router with a fake API (`src/test/`), e.g. learners are kept out, admins cannot
verify, verification needs an explicit reading, labels send the right payload.

Dependency notes: `@testing-library/react-native` is pinned to 13.x because
`expo-router/testing-library` targets it; `npm audit` reports advisories in Expo SDK 57's
build tooling (metro, jest, @expo/cli), fixed by upgrading the SDK, not by `audit fix`.
