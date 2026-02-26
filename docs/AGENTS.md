<!-- braindump: rules extracted from PR review patterns -->

# docs/ Guidelines

## Documentation

- Remove self-evident, outdated, internal, or redundant content from docs — Keeps documentation focused on useful, current information that users actually need to understand the product
- Prioritize common-case features in primary docs, move edge cases to secondary/reference sections — Reduces cognitive load for new users and helps them find the 90% use case quickly without wading through rare scenarios.
- When documenting alternatives, highlight the recommended option and when to use others — Prevents user confusion and guides them to the common-case solution without hiding available alternatives
- Link to centralized reference docs instead of duplicating schemas/APIs inline — prevents doc drift and maintenance burden — Duplication causes docs to fall out of sync when APIs change, creating confusion and extra maintenance work
- Hyperlink concepts, features, and variables to their docs — improves discoverability and reduces context-switching — Users can navigate to definitions without searching, making documentation more self-contained and easier to understand.
- Link to specific doc pages, not repo folders or generic entry points — improves user experience and reduces navigation friction — Users can immediately access relevant content instead of hunting through folder listings or following redirects
- Include screenshots, output samples, or diagrams in docs for user-facing features — Visual aids help users understand expected results and reduce confusion about UI/output behavior
- In docs, define concepts before usage and show simple examples before filtered variants — Builds understanding progressively, preventing cognitive overload when readers encounter complex examples before grasping fundamentals
- Link to GitHub issues for roadmaps/tracking content — avoids stale docs and duplication — Frequently-changing content becomes outdated quickly when duplicated in docs; issue links keep information centralized and current.
- Test all doc code examples against actual dependencies — prevents publishing broken examples that confuse users — Ensures documentation stays accurate as APIs evolve and protects user experience from copy-paste errors
- Verify cross-referenced pages actually cover the linked concepts with clear distinctions — Prevents user frustration from broken knowledge paths and ensures documentation cross-references remain accurate as content evolves
- Use 'instrumentation' or 'integration' (not 'auto-instrumentation') and explain direct vs. dependency-based monitoring — Prevents user confusion about what's actually being monitored and how the instrumentation works
- Split related docs into separate pages with cross-links — improves navigation and lets readers find topic-specific content faster — Separating concerns in documentation (e.g., HTTP client vs server) prevents overwhelming readers and makes each page more focused and discoverable.
- Place cross-links at page start, use inline links not admonitions — improves discoverability and reduces visual clutter — Users scan page tops first, and inline links blend better than attention-grabbing boxes that distract from content flow.

<!-- /braindump -->