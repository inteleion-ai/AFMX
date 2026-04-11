# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.3.x   | ✅ Active           |
| 1.2.x   | ✅ Security fixes   |
| 1.1.x   | ⚠️ End of life      |
| < 1.1   | ❌ Unsupported      |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Email: **security@agentdyne9.com**
(or **hello@agentdyne9.com** if the security alias is not yet active)

We acknowledge reports within **48 hours** and target resolution of critical
issues within **14 days**.

Include: AFMX version, Python version, steps to reproduce, and impact assessment.
We will confirm receipt, assess severity, and coordinate disclosure.

## Scope

**In scope:**
- Remote code execution via the API
- Authentication bypass or privilege escalation via RBAC
- Injection vulnerabilities (prompt, shell, expression sandbox escape)
- Sensitive data exposure across tenant boundaries
- Denial-of-service via resource exhaustion
- Handler registry poisoning

**Out of scope:**
- Social engineering or physical security
- Issues in third-party dependencies (report those upstream)
- Vulnerabilities in optional adapter packages (LangChain, CrewAI, etc.)

## Disclosure Policy

We follow coordinated disclosure. Once a fix is released, we publish a security
advisory on GitHub. Credit is given to reporters who request it.
