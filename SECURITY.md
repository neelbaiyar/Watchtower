# Security Policy

## Supported Versions

Watchtower is pre-release software (version `0.1.0`) and has no tagged
releases yet. Security fixes are applied only to the latest commit on the
`main` branch.

| Version | Supported |
| --- | --- |
| Latest commit on `main` | Yes |
| Any older commit or fork | No |

## Reporting a Vulnerability

Please report vulnerabilities privately. Do not open a public issue, pull
request, or discussion for a suspected vulnerability.

Email: **`<SECURITY-CONTACT-EMAIL — placeholder, to be filled in by the maintainer>`**

If you find a credential, token, or personal contact value committed anywhere
in this repository or its history, report it the same way and do not reproduce
the value in your message.

## What to Include

A useful report contains:

- A description of the issue and the impact you believe it has.
- The affected component: the FastAPI service, the browser dashboard, the Go
  poller, the SQL migrations, or the Docker Compose configuration.
- The commit hash you tested.
- Step-by-step reproduction instructions, including the request, input, or
  configuration needed.
- Any proof-of-concept code, logs, or screenshots, with secrets removed.
- Whether the issue is already public or known to anyone else.

## Response Timeline

Watchtower is maintained by one person, so these are good-faith targets rather
than guarantees:

- Acknowledgement of your report within 7 days.
- An initial assessment, including whether the report is accepted, within
  14 days.
- A fix or a documented mitigation for accepted reports as soon as practical,
  with progress updates at least every 14 days until it is resolved.

Please allow a fix to be published before disclosing the issue publicly.

## Scope

Watchtower is designed to run on a single developer machine. The documented
commands bind the API to `127.0.0.1`, and the Compose files publish ports on
`127.0.0.1` only.

In scope:

- Code in this repository: the API, dashboard, poller, migrations, and
  Compose configuration.
- Leaks of secrets or personal configuration through API responses, error
  messages, or files tracked in Git.
- Injection, cross-site scripting, or unsafe handling of data received from
  upstream providers.

Out of scope:

- Vulnerabilities in SEC EDGAR, Yahoo Finance, Marketaux, or other third-party
  services and libraries. Report those to their maintainers.
- The absence of authentication, TLS, and request rate limiting. The API has
  none of these, which is a known limitation of a local-only tool. Do not
  expose it to an untrusted network.
- The accuracy of the research-priority signal. It is not investment advice.

## Security Practices in This Repository

These describe what the code does today:

- Secrets and personal contact values are read from environment variables. The
  local `.env` files are ignored by Git, and the committed `.env.example` files
  contain placeholders only.
- Required configuration is validated at startup. Settings values are excluded
  from object representations, and configuration errors name the missing
  variable without printing its value.
- Provider failures are translated into fixed Watchtower error messages, so raw
  provider responses and tokens are not returned to API callers.
- API responses are validated against strict schemas that reject unknown
  fields, and the ticker path parameter is format-checked before any provider
  is called.
- All SQL uses bound parameters in both the Python and Go code.
- The dashboard inserts provider-supplied text as text content, never as HTML,
  and links are limited to URLs the API has validated as HTTP or HTTPS.
- The API container image runs as a non-root user, and `.dockerignore` keeps
  `.env` files out of the image build context.
- Marketaux accepts its API token only as a URL query parameter. The client
  adds the token below the HTTP library's logging layer, so the token is absent
  from request log lines and from request URLs attached to errors, including
  when `httpx` request logging is enabled.
