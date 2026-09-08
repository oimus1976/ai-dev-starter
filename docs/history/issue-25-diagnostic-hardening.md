# Issue #25 diagnostic hardening

This follow-up keeps the Issue #16 cleanup safety boundary unchanged while improving operator-facing diagnostics.

Scope:

- report concrete retained/unknown ignored paths that block cleanup;
- keep explicit disposable-path policy unchanged;
- keep mixed-content no-partial-delete semantics unchanged;
- do not add migration/preservation automation;
- do not use `git clean` or forced worktree removal.

Windows real-machine qualification for the underlying safety behavior was completed under Issue #16. Issue #25 requires only diagnostic regression/CI unless implementation changes the cleanup authority boundary.
