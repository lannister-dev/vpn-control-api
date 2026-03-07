## Branching Rules
- Source branch: personal feature branch (`feature/*`, `fix/*`, etc.)
- Target branch: `dev`
- Direct pushes to `dev` are not allowed

## Checklist
- [ ] Base branch is `dev`
- [ ] Tests are green in `Dev PR Checks`
- [ ] Migration impact checked (if schema changed)
- [ ] Backward compatibility checked (if API/agent contracts changed)
