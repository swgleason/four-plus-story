# Four Plus Story Library — Admin Workbench

The Next.js App Router application provides a curator-only interface for:
- accepting one-time curator invitations and signing in with Supabase Auth;
- uploading source documents and monitoring processing jobs and audit events;
- reviewing original source text, page spans, AI evaluation, emotions, somatics, and STEP;
- saving separate, unapproved curated telling drafts with live 140 wpm metrics;
- approving, rejecting, or requesting revision, with visibility controlled by document rights.

## Local configuration

Copy `.env.example` to `.env.local` and set the Supabase URL, public anon key,
server-only service-role key, and FastAPI base URL. Never expose the service-role
key using a `NEXT_PUBLIC_` variable. The API proxy rechecks the signed-in profile
role, and the FastAPI service independently validates curator authorization.

The invite acceptance route validates the token, invited email, role, and expiry
against `admin_invitations`. Invitations only create curator or super-admin
profiles. The Supabase service-role key must be configured for this endpoint.

## Development

Run the app from this directory with `pnpm dev`. The curator app expects the
FastAPI service at `FOUR_PLUS_API_URL` (defaults in `.env.example` to
`http://localhost:8000`).

## Key stack

- Next.js 15 App Router, React 19, TypeScript, Tailwind CSS
- Supabase SSR/Auth with server-side role guards
- `@four-plus/shared-types`
