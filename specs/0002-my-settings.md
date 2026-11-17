# 0002 — My settings: changing my password

- **Status:** Done
- **Depends on:** 0001
- **Django apps:** `accounts`
- **Touches:** frontend / backend / jobs

## Why
The account menu only signs you out. Someone who wants a new password, because they think it
has been seen or set it in a hurry when they accepted their invitation, has no way to change it.
They need a page of their own where they can, by proving they know the current one.

## Scope
- In: a **My settings** page for every signed-in person, opened from the account menu next to
  Sign out. Its first section: changing my password using my current one. Built as sections so
  more personal settings can join it.
- Out (later specs): forgotten passwords (resetting by email); changing my email address;
  two-factor sign-in and SSO; my name, which is per company and set by its admins (0001).

## Design notes
- My settings is about the person, not a company: it lives at `/account`, works whichever
  company the tab is in, or none, and needs no permission.
- `POST /api/auth/password/` with `{"current_password", "new_password"}`. It only ever changes
  the signed-in person's own password: the request names no user. It works across companies, so
  it opts out of `InRealm` and goes on the allowlist in `apps/realms/test_isolation.py`, with that
  reason.
- The change is a service in `apps/accounts/services.py`: check the current password, run
  Django's `AUTH_PASSWORD_VALIDATORS` against the new one (with the user, so it can't resemble
  their email), set it.
- The page asks for the new password twice and won't send it until both match; the API takes it
  once.
- Tries are throttled per person at the `password` rate, 10 a minute like sign-in, so the form
  can't be used to guess.
- Changing the password signs out every other browser: their tokens stop working. This tab gets
  fresh tokens in the response and stays signed in. SimpleJWT's `CHECK_REVOKE_TOKEN` puts a hash
  of the password in every token; refresh checks it too, and so must any future websocket.
- After a change, the person gets an email saying their password was changed, and to tell an
  Admin if it wasn't them. It's sent from a Hatchet task inside `transaction.on_commit`, like
  invitations, and never contains the password.
- No company data is involved. No password, old or new, is ever logged or sent back.

## Scenarios

### AT-0002-01 — I find my settings in the account menu
- Given I'm signed in, with any role, in any company or none
- When I open the account menu
- Then I see "My settings" next to "Sign out", and it opens a page showing my email and a
  "Password" section that works

### AT-0002-02 — I change my password with my current one
- When I give my current password and a new one, and save
- Then I see "Password changed"
- And I can sign in with the new password, and not with the old one

### AT-0002-03 — A wrong current password changes nothing
- When I give a current password that isn't mine
- Then I see "That isn't your current password"
- And my password is unchanged

### AT-0002-04 — The new password must be a good one
- When my new password is too short, too common, all numbers, or too like my email
- Then I see why it was refused
- And my password is unchanged

### AT-0002-05 — The new password must be new
- When my new password is the same as my current one
- Then I see "Choose a password you aren't using now"

### AT-0002-06 — Changing it signs out my other browsers
- Given I'm signed in on two browsers
- When I change my password on one
- Then that one stays signed in
- And the other is signed out the next time it asks for anything, and can't refresh its way back

### AT-0002-07 — I'm told by email
- When I change my password
- Then I get an email saying it was changed, with no password in it

### AT-0002-08 — Guessing is slowed down
- When someone tries more than ten times in a minute
- Then they are told to wait, and no more passwords are checked until then

### AT-0002-09 — Only my own password, and only when signed in
- When I'm signed out, changing a password is refused
- And whatever I send, only my own account's password can change: anyone else's, in my company
  or not, is untouched

## Decisions
- Ruan asked for this directly ("a user settings page that lets us do a password change"); it
  follows eden-tracker's spec 0012, which Ruan approved there.
- This browser stays signed in after a change; the email is in (as in eden-tracker).

## Implementation notes
- **Backend (`apps/accounts/`):** `services.change_password`, `PasswordChangeSerializer`, the
  `POST /api/auth/password/` view with a per-person `password` throttle (10/min),
  `RevocableTokenRefreshSerializer` with `CHECK_REVOKE_TOKEN`, and `mail.py` / `tasks.py` for the
  `send-password-changed-email` Hatchet task. Ported from eden-tracker's 0012.
- **Frontend:** `src/features/account/` (hook and password form), `src/routes/_app/account/`,
  `src/components/settings-section.tsx`, and "My settings" in the account menu. `/account`
  renders outside `RealmGate`, so it works for someone in no company.
- **Tests:** `apps/accounts/test_password.py`, scenarios 01 to 09 as `test_at_0002_<nn>_...`;
  the route is on the isolation allowlist and in the signed-out test.
- **Checked in the running app:** the menu item, a mismatched repeat, a wrong current password,
  a real change (this tab stayed signed in; the API then refused the old password and took the
  new one), and the page for someone in no company, in dark and light mode and at phone width.
  The "password changed" email is covered by the tests; it wasn't watched leaving a live worker.
