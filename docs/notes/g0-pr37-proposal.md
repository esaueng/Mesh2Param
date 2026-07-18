# G0 PR #37 review proposal

## Finding

PR #37 must not add a second copy of the G0 spanner fixtures. While the draft
was open, `main` advanced to `b59de50` and incorporated `bf21948` (`Add general
spanner fixtures`). That commit already provides the required filleted,
unfilleted, and embossed variants through exact CadQuery feature operations,
records their parameters in manifests, and covers generation, byte stability,
ground-truth geometry, and the pre-G1 segmentation gap with dedicated tests.

The three STL payloads proposed by PR #37 are byte-for-byte identical to the
fixtures now on `main`:

| Fixture | SHA-256 |
| --- | --- |
| `spanner-filleted` | `3afb3b3236b43a6f785b29720e00d23f9def5cc8cca9605db3fb054d231183df` |
| `spanner-sharp` | `bc0e8d2c7fed94e24b612a92c0843aec2497e290342f2731a4b2112fc7a34531` |
| `spanner-filleted-embossed` | `22bbf9a5cff903e414f329d6a26ddb9d3465b7bccb28793ee4768aedb0f9dc5c` |

Keeping the original PR implementation would create two fixture APIs, two
benchmark locations, and two schema names for identical geometry. That would
make the G1 source of truth ambiguous and add avoidable generated binaries.

## Proposal

Keep the G0 implementation already present on `main` under
`engine/mesh2param/general_fixtures.py` and
`samples/general-parametric-benchmark`. Remove the redundant implementation
from PR #37 and treat this note as the draft PR deliverable documenting why.

Do not start G1 on this branch or in this session. G1 should begin later on a
new branch from the then-current `origin/main`, using the merged G0 fixtures as
its prerequisite and touching only the stated G1 allow-list.

The automatic Cloudflare Workers deployment failure on PR #37 is outside this
engine-only milestone. No CI, deploy configuration, merge, or deployment action
is proposed.

## Plan compliance

- Milestone reviewed: G0 prerequisite for G1.
- Files retained in this PR vs. the allow-list: this proposal note only, as
  required by the standing proposal rule after the prerequisite landed through
  a different implementation while the draft was open.
- No G1 segmentation or reconstruction work was started.

No geometry outside engine/mesh2param; no merges or deploys performed.
