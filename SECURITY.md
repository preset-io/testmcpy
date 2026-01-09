# Security Policy

## Supported Versions

We actively support the following versions of testmcpy with security updates:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

We take the security of testmcpy seriously. If you discover a security vulnerability, please report it responsibly.

### How to Report

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report security vulnerabilities through one of the following methods:

1. **GitHub Security Advisories** (Recommended)
   - Navigate to the [Security Advisories](https://github.com/preset-io/testmcpy/security/advisories/new) page
   - Click "Report a vulnerability"
   - Fill out the form with details about the vulnerability

2. **Email**
   - Send an email to [preset-oss@preset.io](mailto:preset-oss@preset.io)
   - Use the subject line: "SECURITY: [Brief description]"
   - Include detailed information about the vulnerability (see below)

### What to Include in Your Report

To help us understand and address the issue quickly, please include:

- **Description**: A clear description of the vulnerability
- **Impact**: What type of vulnerability is it? (e.g., authentication bypass, code execution, information disclosure)
- **Affected Components**: Which parts of testmcpy are affected?
- **Reproduction Steps**: Detailed steps to reproduce the vulnerability
- **Proof of Concept**: If possible, include code or commands that demonstrate the issue
- **Suggested Fix**: If you have ideas on how to fix the issue, please share them
- **Your Contact Information**: How we can reach you for follow-up questions

### What to Expect

After you submit a vulnerability report:

1. **Acknowledgment**: We will acknowledge receipt of your report within 2 business days
2. **Investigation**: We will investigate and validate the vulnerability
3. **Updates**: We will keep you informed about our progress
4. **Resolution**: We will work on a fix and coordinate a disclosure timeline with you
5. **Credit**: If you wish, we will credit you in the security advisory and release notes

### Disclosure Policy

- **Coordinated Disclosure**: We follow coordinated disclosure practices
- **Timeline**: We aim to resolve critical vulnerabilities within 90 days
- **Public Disclosure**: After a fix is released, we will publish a security advisory
- **CVE Assignment**: For significant vulnerabilities, we will request a CVE identifier

## Security Best Practices for Users

When using testmcpy, follow these security best practices:

### API Keys and Credentials

1. **Never commit credentials**: Do not commit API keys, tokens, or secrets to version control
2. **Use environment variables**: Store sensitive configuration in environment variables or secure config files
3. **File permissions**: Ensure your `~/.testmcpy` config file has restricted permissions (600)
   ```bash
   chmod 600 ~/.testmcpy
   ```
4. **Rotate keys regularly**: Periodically rotate your API keys for Anthropic, OpenAI, and MCP services

### MCP Service Security

1. **Secure MCP URLs**: Only connect to trusted MCP services over HTTPS
2. **Token Management**: Use short-lived JWT tokens when possible (enable dynamic JWT auth)
3. **Network Security**: Be cautious when exposing MCP services on public networks
4. **Validate responses**: Be aware that MCP tools can execute operations with your credentials

### Test File Security

1. **Review test files**: Inspect YAML test files from untrusted sources before running them
2. **Limit prompts**: Be cautious with prompts that might trigger unintended tool calls
3. **Sandbox testing**: Test unknown MCP services in isolated environments first

### Web UI Security

1. **Local access**: By default, the web UI runs on localhost only (127.0.0.1)
2. **Authentication**: If exposing the web UI, implement proper authentication
3. **HTTPS**: Use HTTPS when accessing the web UI over a network

## Known Security Considerations

### LLM-Specific Risks

- **Prompt Injection**: LLMs may be susceptible to prompt injection attacks
- **Tool Misuse**: Malicious prompts could potentially trigger unintended tool calls
- **Data Leakage**: Be careful about sensitive data in prompts or MCP responses

### Dependency Security

We regularly update dependencies to address known vulnerabilities. You can check for outdated dependencies:

```bash
pip list --outdated
```

To update testmcpy to the latest version:

```bash
pip install --upgrade testmcpy
```

## Security Update Policy

- **Critical vulnerabilities**: Patched within 7 days, emergency releases if needed
- **High severity**: Patched within 30 days
- **Medium/Low severity**: Patched in next regular release

## Hall of Fame

We recognize security researchers who responsibly disclose vulnerabilities:

<!-- Future contributors will be listed here -->
- (No vulnerabilities reported yet)

## Questions?

If you have questions about this security policy or general security concerns (not vulnerability reports), please:

- Open a [GitHub Discussion](https://github.com/preset-io/testmcpy/discussions)
- Email us at [preset-oss@preset.io](mailto:preset-oss@preset.io)

## Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Python Security Best Practices](https://python.readthedocs.io/en/latest/library/security_warnings.html)
- [GitHub Security Best Practices](https://docs.github.com/en/code-security)

---

Thank you for helping keep testmcpy and its users safe!
