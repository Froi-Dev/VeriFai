# Publishing the current project safely

The original repository's history contains a database connection string matching
local configuration. Do not push that history to a new public repository. Rotate
the database password, especially if any earlier commits were shared. Removing
a file from the latest commit does not remove it from older commits.

A separate `Verifai-publish-ready` folder beside the original workspace contains
the current source files with a fresh Git index and no inherited history. It
includes the existing uncommitted source changes. Use that folder for the first
commit and push to a new GitHub repository. No remote is configured automatically.
Do not merge the original history into the clean repository.

Local `.env` files, runtime logs, security-audit output, dependency directories,
and build output are excluded. Keep secrets in local environment files or hosting
provider secret settings. `.env.example` contains placeholders only. All `VITE_`
variables are public browser configuration and must never contain credentials.

Before committing, install Gitleaks and run from the clean folder:

```powershell
gitleaks dir . --config .gitleaks.toml --redact
```

After committing, verify the history before pushing:

```powershell
gitleaks git . --config .gitleaks.toml --redact --log-opts="--all"
```

The GitHub workflow repeats the history scan on pushes and pull requests, but
cannot prevent the first upload of a secret. Always scan locally first.

Publishing source is separate from deploying the full application. The existing
GitHub Pages workflow publishes only the landing page. The backend requires its
own environment configuration, database, and model files.
