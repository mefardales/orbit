---
name: security-review
description: Run a comprehensive security review on code
---

# Security Review Skill

Conduct a thorough security audit checking for OWASP Top 10 vulnerabilities, hardcoded secrets, and unsafe patterns.

## When to Use

This skill activates when:
- User requests "security review", "security audit"
- After writing code that handles user input
- After adding new API endpoints
- After modifying authentication/authorization logic
- Before deploying to production
- After adding external dependencies

## What It Does

Delegates to the `security-reviewer` agent (THOROUGH tier) for deep security analysis:

1. **OWASP Top 10 Scan**
   - A01: Broken Access Control
   - A02: Cryptographic Failures
   - A03: Injection (SQL, NoSQL, Command, XSS)
   - A04: Insecure Design
   - A05: Security Misconfiguration
   - A06: Vulnerable and Outdated Components
   - A07: Identification and Authentication Failures
   - A08: Software and Data Integrity Failures
   - A09: Security Logging and Monitoring Failures
   - A10: Server-Side Request Forgery (SSRF)

2. **Secrets Detection**
   - Hardcoded API keys
   - Passwords in source code
   - Private keys in repo
   - Tokens and credentials
   - Connection strings with secrets

3. **Input Validation**
   - All user inputs sanitized
   - SQL/NoSQL injection prevention
   - Command injection prevention
   - XSS prevention (output escaping)
   - Path traversal prevention

4. **Authentication/Authorization**
   - Proper password hashing (bcrypt, argon2)
   - Session management security
   - Access control enforcement
   - JWT implementation security

5. **Dependency Security**
   - Run `npm audit` for known vulnerabilities
   - Check for outdated dependencies
   - Identify high-severity CVEs

## Agent Delegation

```
delegate(
  role="security-reviewer",
  tier="THOROUGH",
  prompt="SECURITY REVIEW TASK

Conduct comprehensive security audit of codebase.

Scope: [specific files or entire codebase]

Security Checklist:
1. OWASP Top 10 scan
2. Hardcoded secrets detection
3. Input validation review
4. Authentication/authorization review
5. Dependency vulnerability scan (npm audit)

Output: Security review report with:
- Summary of findings by severity (CRITICAL, HIGH, MEDIUM, LOW)
- Specific file:line locations
- CVE references where applicable
- Remediation guidance for each issue
- Overall security posture assessment"
)
```

## External Model Consultation (Preferred)

The security-reviewer agent SHOULD consult Codex for cross-validation.

### Protocol
1. **Form your OWN security analysis FIRST** - Complete the review independently
2. **Consult for validation** - Cross-check findings with Codex
3. **Critically evaluate** - Never blindly adopt external findings
4. **Graceful fallback** - Never block if tools unavailable

### Tool Usage
Before first MCP tool use, call `ToolSearch("mcp")` to discover deferred MCP tools.
Use `mcp__x__ask_codex` with `agent_role: "security-reviewer"`.
If ToolSearch finds no MCP tools, fall back to the `security-reviewer` agent.

## Security Checklist

### Authentication & Authorization
- [ ] Passwords hashed with strong algorithm (bcrypt/argon2)
- [ ] Session tokens cryptographically random
- [ ] JWT tokens properly signed and validated
- [ ] Access control enforced on all protected resources
- [ ] No authentication bypass vulnerabilities

### Input Validation
- [ ] All user inputs validated and sanitized
- [ ] SQL queries use parameterization (no string concatenation)
- [ ] NoSQL queries prevent injection
- [ ] File uploads validated (type, size, content)
- [ ] URLs validated to prevent SSRF

### Output Encoding
- [ ] HTML output escaped to prevent XSS
- [ ] JSON responses properly encoded
- [ ] No user data in error messages
- [ ] Content-Security-Policy headers set

### Secrets Management
- [ ] No hardcoded API keys
- [ ] No passwords in source code
- [ ] No private keys in repo
- [ ] Environment variables used for secrets
- [ ] Secrets not logged or exposed in errors

### Dependencies
- [ ] No known vulnerabilities in dependencies
- [ ] Dependencies up to date
- [ ] No CRITICAL or HIGH CVEs
- [ ] Dependency sources verified

## Severity Definitions

**CRITICAL** - Exploitable vulnerability with severe impact (data breach, RCE, credential theft)
**HIGH** - Vulnerability requiring specific conditions but serious impact
**MEDIUM** - Security weakness with limited impact or difficult exploitation
**LOW** - Best practice violation or minor security concern

## Remediation Priority

1. **Rotate exposed secrets** - Immediate (within 1 hour)
2. **Fix CRITICAL** - Urgent (within 24 hours)
3. **Fix HIGH** - Important (within 1 week)
4. **Fix MEDIUM** - Planned (within 1 month)
5. **Fix LOW** - Backlog (when convenient)

## Use with Other Skills

**With Team:**
```
/team "run security review on authentication module"
```

**With Ralph:**
```
/ralph security-review then fix all issues
```

## Best Practices

- **Review early** - Security by design, not afterthought
- **Review often** - Every major feature or API change
- **Automate** - Run security scans in CI/CD pipeline
- **Fix immediately** - Don't accumulate security debt
- **Verify fixes** - Re-run security review after remediation
