# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| 1.0.x | ✅ Active |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Email: **security@agentdyne9.com**

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Your suggested fix (optional)

We will acknowledge receipt within 48 hours and aim to release a fix within 14 days for critical issues.

## Scope

In scope:
- Remote code execution via the API
- Authentication bypass (RBAC/API key validation)
- Injection vulnerabilities in matrix execution
- Sensitive data exposure in API responses

Out of scope:
- Vulnerabilities in optional dependencies (report to those projects directly)
- Denial of service via concurrency cap exhaustion (this is a configuration matter)

## Disclosure Policy

We follow coordinated disclosure. Please give us reasonable time to fix before public disclosure. We will credit reporters in the release notes unless you prefer to remain anonymous.
