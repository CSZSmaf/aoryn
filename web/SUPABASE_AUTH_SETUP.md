# Aoryn Supabase Auth Setup

This project uses Supabase only for identity and the smallest possible profile.
Tasks, history, screenshots, cache, and configuration stay on the user's device.

## 1. Run the SQL bootstrap

Use [scripts/supabase_auth_setup.sql](../scripts/supabase_auth_setup.sql) in the Supabase SQL editor.

It does four things:

- keeps `public.profiles` attached to `auth.users`
- hardens `handle_new_user()` so profile creation does not block sign-up
- enables RLS on `public.profiles`
- allows users to read and update only their own profile

## 2. Configure Supabase Auth

In Supabase Auth settings:

- enable Email / Password sign-in
- enable email confirmation
- set `Site URL` to `https://aoryn.org`
- add redirect URLs for at least:
  - `https://aoryn.org`
  - `https://www.aoryn.org`
  - `https://aoryn.pages.dev`

## 3. Configure Cloudflare Pages Functions

Set these environment variables in the Pages project:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SITE_URL=https://aoryn.org`

The website registration modal already defaults to:

- `VITE_REGISTER_ENDPOINT=/api/auth/register`

The Pages Functions endpoints are:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `POST /api/auth/refresh`

## 4. Desktop app behavior

The desktop dashboard uses the same auth API base URL and stores only the session locally.
On Windows the session is protected with DPAPI.

Cloud data:

- auth account
- email
- display name
- account creation time
- auth session / tokens

Local-only data:

- tasks
- chat history
- agent runs
- screenshots
- runtime preferences
- model configuration
- cache
