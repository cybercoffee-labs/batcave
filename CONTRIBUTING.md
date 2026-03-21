# Contributing to Batman Lab

## Development Workflow

### Branch Strategy

```
main         — stable, tested, production-ready
  └── develop    — integration branch, CI must pass
       ├── feature/scanner-j-dex     — new feature
       ├── feature/dashboard-pnl     — new feature
       ├── fix/bybit-p2p-price       — bug fix
       └── hotfix/gordon-killswitch  — urgent production fix
```

### Rules

1. **Never push directly to `main`** — always go through `develop`
2. **Every feature gets a branch** — `feature/<name>` from `develop`
3. **All tests must pass** before merging to `develop`
4. **Hotfixes** go directly from `main`, merge back to both `main` and `develop`

### Workflow

```bash
# Start new feature
git checkout develop
git pull
git checkout -b feature/my-feature

# Work on it...
# Commit often with descriptive messages
git add -A
git commit -m "feat(scanner-j): add DexScreener API integration"

# Push and create PR
git push origin feature/my-feature
# Create Pull Request on GitHub: feature/my-feature → develop

# After PR approved + CI passes, merge
git checkout develop
git merge feature/my-feature
git push origin develop

# When develop is stable, merge to main
git checkout main
git merge develop
git push origin main
git tag -a v1.1.0 -m "Added DEX scanner + dashboard"
git push --tags
```

### Commit Messages

Format: `type(scope): description`

Types:
- `feat` — new feature
- `fix` — bug fix
- `refactor` — code change that doesn't fix or add
- `test` — adding/updating tests
- `docs` — documentation
- `chore` — maintenance (deps, configs)
- `security` — security-related changes

Examples:
```
feat(scanner-j): add Uniswap V3 price fetching via DexScreener
fix(scanner-i): reject Bybit prices >3% from Bitso reference
test(gordon): add circuit breaker edge case tests
docs(claude): update CLAUDE.md with 11 scanner architecture
chore(deps): pin numpy to 1.26.4 for reproducibility
security(gordon): add daily exposure hard limit
```

### Before Committing

```bash
make lint       # Fix any linting issues
make test       # All 383+ tests must pass
```

### Release Tags

```
v1.0.0 — Initial release (9 scanners, 383 tests)
v1.1.0 — Dashboard + Scanner J + K (11 scanners)
v1.2.0 — Telegram alerts + more coins
v2.0.0 — SaaS version / public product
```
