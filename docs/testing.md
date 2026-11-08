# Testing and Acceptance Traceability

The brief refers to sections 10.1–10.3, but those sections are not present in
the repository. This traceability table maps the acceptance bullets supplied
for Phase 7. Automated test names refer to the current backend/frontend suites.

## Traceability

| Requirement | Automated evidence | Status / remaining gap |
|---|---|---|
| Auth: registration, duplicate email, password hashing, login, invalid password, protected routes, expired/tampered tokens, rate limiting | `backend/tests/test_auth.py`: `test_register_returns_generic_response_and_hashes_password`, `test_register_normalizes_email_and_rejects_duplicate`, `test_login_returns_access_token_and_me_returns_public_profile`, `test_wrong_password_and_unknown_email_share_same_error`, `test_me_rejects_expired_and_tampered_tokens`, `test_auth_rate_limit_returns_429_and_retry_after`; `backend/tests/test_rate_limit.py::test_auth_rate_limits_are_shared_between_instances`, `test_auth_rate_limits_are_scoped_by_action`; `backend/tests/test_routes_security.py::test_every_protected_route_rejects_anonymous_requests` | Covered. New/duplicate registrations return the same response; the frontend does not auto-login. `test_login_does_not_log_password_or_access_token` checks credential redaction. |
| Project owner/admin/member/non-member permissions | `backend/tests/test_authorization_matrix.py::test_project_route_permissions_for_each_role`; existing project/task role tests | Automated 25 protected-route × 4-role matrix. |
| Every protected API route rejects anonymous requests | `backend/tests/test_routes_security.py::test_every_protected_route_rejects_anonymous_requests` | Covered by enumerating the OpenAPI paths; new protected API paths fail unless explicitly allow-listed. |
| Every protected API route has an explicit role-matrix entry | `backend/tests/test_authorization_matrix.py::test_role_matrix_covers_every_protected_api_route` | Covered; fails when a protected OpenAPI route is missing from the role matrix. |
| Tasks: CRUD, assignee validation, filters, status transitions, ordering, concurrency, move/update conflict | `backend/tests/test_tasks.py`: `test_task_create_update_conflict_move_filters_and_outbox`, `test_task_assignee_must_be_project_member_and_dashboard_counts`, `test_task_http_version_conflict_contains_current_state`, `test_task_positions_remain_contiguous_after_reorder_move_and_delete`, `test_concurrent_task_mutations_have_one_winner`, `test_review_workflow_attributes_mover_and_credits_submitter` | Covered, including same-version write contention and move/update version conflicts. |
| Comments, activity, notifications | `backend/tests/test_comments_notifications_activity.py`: `test_comment_creation_permissions_notifications_and_activity`, `test_notifications_read_state_and_isolation`, `test_activity_feed_and_dashboard_recent_scoping`; `backend/tests/test_projects.py::test_member_services_record_activity_and_return_outbox_events` | Covered, including notification scoping and outbox behavior. |
| Realtime authentication, room authorization, multiple recipients, outsider exclusion, removal revocation, transactional delivery | `backend/tests/test_realtime.py::test_socket_auth_rejects_bad_tokens_and_checks_expiry_on_join`, `backend/tests/test_realtime.py::test_realtime_rooms_publish_committed_changes_and_revoke_removed_members`; `backend/tests/test_projects.py::test_project_creation_failure_rolls_back_project_membership_and_activity` | Covered for denied connection/join, authorized room delivery to two clients, outsider exclusion, revoked members, and events not emitted before successful transaction completion. |
| HTTP error shapes and exception masking | `backend/tests/test_security_review.py::test_error_responses_shape_and_no_traceback_leakage`; relevant 403/404/409 behavior is asserted by project/task authorization and version-conflict tests | Covered for 422 and generic 500/no traceback; authorization and conflict tests cover endpoint-specific 403/404/409 outcomes. |
| Configuration: required secrets, PostgreSQL URL normalization, CORS, body-size bounds | `backend/tests/test_config.py::test_settings_require_secrets_outside_tests`, `test_settings_parse_origins_and_normalize_database_urls`; `backend/tests/test_security_review.py::test_cors_allowed_and_disallowed_origins`, `test_request_body_limit_rejects_large_fixed_and_chunked_bodies`, `test_socket_payload_limit_matches_http_request_limit` | Covered; CORS tests allowed/disallowed origins and preflight; HTTP and Socket.IO enforce the configured 1 MiB cap. |
| Production security headers and frontend Vercel policy | `backend/tests/test_security_review.py::test_production_security_headers_include_csp_and_hsts`, `test_vercel_config_sets_frontend_security_headers` | Covered by helper and config assertions. Tighten Vercel `connect-src` to the final API hostname before deployment. |
| Frontend auth validation and protected routes | `frontend/src/pages/AuthPages.test.jsx`: `shows inline validation messages on login`, `shows a server error on login failure`, `redirects unauthenticated users to login and remembers destination`, `redirects authenticated users away from login and register`, `shows a generic registration confirmation and asks the user to sign in` | Covered. |
| Frontend board states, create/edit/delete, and role-sensitive controls | `frontend/src/pages/BoardPage.test.jsx`: `renders the four task columns and real task cards`, `shows loading and retryable error states for an empty board`, `creates a task using the real task API`, `edits a task and sends its expected version`, `confirms task deletion before calling the API`, `disables Review drag handles for members who are not the reviewer` | Covered. Direct drag/drop handler behavior is included in manual QA; no Playwright test was added. |
| Frontend realtime hook and reconnect refetch | `frontend/src/hooks/useProjectRealtime.test.jsx`: `joins after connect, rejoins on reconnect, and refetches after each join`, `deduplicates event ids and ignores its own mutation echo`, `reports join errors and cleans up listeners and room membership` | Covered with mocked realtime transport. |
| Frontend notifications | `frontend/src/components/NotificationsMenu.test.jsx`: `marks a notification as read and navigates to its task`, `updates the unread count when a realtime notification arrives`, `marks all loaded notifications as read` | Covered. |
| Frontend accessibility smoke checks | Accessible roles/names and password-visibility behavior are exercised by UI tests; manual keyboard/focus review below | No automated axe scan is configured. |

## Executed validation

| Suite | Result |
|---|---|
| Backend Ruff lint and formatter check | Passed |
| Backend pytest | 268 passed; 91% statement coverage (1,719/1,895 statements) |
| Concurrency + realtime repeat run | 10 runs × 22 passing tests; no failures |
| Frontend ESLint | Passed |
| Frontend Vitest | 86 passed; 69.76% statement / 70.64% line coverage |
| Frontend production build | Passed |
| Python dependency audit | No known vulnerabilities |
| Production npm audit | 0 vulnerabilities |
| Full npm audit | 0 vulnerabilities after ESLint 9.39.5 update and JSX-aware lint configuration |

The CI workflow is [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).
Its YAML was locally parsed and its backend/frontend jobs inspected; `actionlint`
was unavailable, and the workflow has not been run on GitHub.

## Manual QA procedure

Use the local development setup documented in the README. Keep three browser
profiles available: **Owner**, **Member**, and **Outsider**. Create separate
accounts for each; add the Member to the Owner's project, and leave the
Outsider out of it.

1. **Authentication and route protection**
   - In a private browser profile, open a protected project URL and verify it
     redirects to sign-in. Sign in, then verify the intended project page opens.
   - Sign out and verify the session is cleared. Try invalid login credentials
     and an invalid registration form; verify actionable inline errors appear.
   - Submit a valid new account and then an existing email. Verify both
     requests show the same generic confirmation and neither signs in
     automatically; use the sign-in link afterward.
2. **Project role checks**
   - As Owner, open project settings and add the Member. Verify owner-only
     settings controls are visible.
   - As Member, open the same project and verify owner-only settings controls
     are absent. Try the corresponding edit/delete operation through the UI;
     verify it is denied.
   - As Outsider, paste the project URL and task URL directly. Verify project
     data is not displayed. If using the API, repeat with the same resource IDs
     and confirm non-member responses do not disclose the resource.
   - As Owner, change a non-owner role and remove the Member. Verify the
     Member's project access is revoked. As Admin, verify permitted member
     management actions and verify role changes reserved for the Owner are
     unavailable.
3. **Task and collaboration workflow**
   - As Owner or Member, create, edit, assign, filter, move, and delete a task.
     Verify invalid assignees are rejected and task ordering remains stable
     after a move/delete.
   - Add a comment, open project activity, and mark a notification read. Verify
     the activity and notification correspond to the task/project and that
     another user's notifications remain private.
4. **Realtime isolation and revocation**
   - Open the same project board in Owner and Member profiles and open an
     unrelated project (or no project) in Outsider.
   - Change a task in the Owner profile. Verify the Member board updates
     without refresh, while the Outsider receives no task/project event.
   - Remove the Member from the project, reconnect or refresh the Member
     profile, and verify it cannot rejoin or receive later project events.
5. **Keyboard/accessibility smoke check**
   - Navigate sign-in, project navigation, task dialog, and notifications using
     only Tab, Shift+Tab, Enter, and Escape. Confirm visible focus, meaningful
     control names, associated form labels/errors, and that dialogs can be
     closed without a pointer.

Record browser, account role, action, and observed result for failures. The
two-browser realtime scenario remains manual; no Playwright E2E was added
because a reliable browser-context setup was not established.
