# Security Policy

## Reporting a vulnerability

If you discover a security vulnerability in Chrisnov Media Toolkit, please
report it privately by emailing **contact@chrisnov.com**.

Do **not** open a public GitHub Issue.

You should receive a response within 48 hours. If you don't, follow up to
ensure we received your original message.

## What to include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested mitigation (if known)

## Scope

The following are in scope:

- Code execution or privilege escalation via crafted URLs
- Arbitrary file read/write via output path injection
- Unsafe deserialisation

The following are out of scope:

- Missing code signing / notarisation (the app ships unsigned)
- Phishing via yt-dlp's network requests (yt-dlp controls its own TLS)

## Supported versions

Only the latest release tag is supported. No backports are provided for
older beta versions.
