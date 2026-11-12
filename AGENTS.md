# Agent instructions

What to build is in [SPEC.md](SPEC.md). This file is about *how* to work here. Keep both short and stable; do not add dated status logs here or in the README.

## Working agreement

- **Don't overfix.** Do what was asked, nothing more. Do not refactor, rename, "improve" or fix unrelated code on the way.
- **Ask before choosing a solution** whenever there is more than one reasonable approach, the fix touches code outside the task, or the cause is unclear. Explain the problem and give 2–3 options with a recommendation, then wait.
- **Stop on unexpected failures.** If something fails for a reason outside the task (environment, dependency, data, access), make one focused diagnostic check, report what you found, and ask. No workarounds, retries in loops or speculative fixes.
- **No silent scope changes.** If the task turns out bigger or different than described, say so before continuing.
- Ask before adding a dependency, changing global or system settings, or spending money (paid APIs, subscriptions).
- Commit or push only when asked.

## Architecture rules

- Layers: `interfaces → usecases → domain`, with `ports` defining every external dependency and `adapters` implementing them. See SPEC.md.
- The domain is pure: no I/O, no HTTP, no database, no environment variables, and no `datetime.now()`. Time always comes from the `Clock` port.
- Market data, LLMs and storage are reached only through ports. Never call a provider SDK outside its adapter.
- The web API and MCP server call the same use cases; no business logic in interfaces.
- No speculative abstractions: add a port, layer or option only when a real use case needs it.

## Code conventions

- Python package in `src/` layout; tests in `tests/`, outside `src/`.
- Absolute imports.
- Money and quantities are `Decimal`, never `float`; serialize them as strings.
- Timestamps are timezone-aware and stored in UTC.
- No magic strings or numbers: give repeated or meaningful literals (env var names, defaults, hosts, ports, identifiers) a named constant or enum.
- Match the surrounding code's style and comment density.

## Frontend

- The UI looks the same everywhere. Every element comes from Mantine or from shared wrappers in `web/src/ui/`; pages compose components and do not style elements themselves.
- Colours, spacing, typography and radii come from the theme in `web/src/ui/theme.ts`; no hard-coded values in components.
- A new kind of element is added to the shared set first, then used.
- UI changes follow established UX practice: check how common products and design systems solve the same problem before proposing a design, and say which pattern you chose and why. In particular:
  - every view handles loading, empty and error states, and a slow or failing part never blocks the rest of the page;
  - destructive actions ask for confirmation and say what will be lost;
  - navigation uses real links, so URLs can be opened, bookmarked and shared;
  - actions that do not apply stay visible but disabled, with the reason;
  - controls are usable by keyboard and screen readers (labels, focus, Enter and Esc).
- API calls go through the generated client in `web/src/api/generated`; run `npm run generate` after backend API changes and never edit it by hand.

## Tests

- Every behaviour change gets a focused test. Prefer tests through a use case or the HTTP/MCP boundary using fake adapters and an in-memory or temporary SQLite repository.
- Real adapters get contract tests shared with their fakes. They never run in the default suite against live services.
- Tests never touch real accounts, paid APIs or the network.
- Keep the suite small and meaningful: no coverage targets, no tests that mirror the implementation.
- Run the relevant tests before handing work back, and report the result in one line. Show output only on failure.

## Safety

- Never put credentials in code, logs, docs, chat or version control. Secrets live in `.env`, which is gitignored.
- The service simulates; it never connects to real brokerage accounts or places real orders.
- Respect market-data licenses: data from personal or development plans must never be shown to public users.
