# Skills Aren't Broken, Claude Code's Implementation Is

Independent research into why Claude Code skills achieve only a 53% pass rate in Vercel's agent evaluations.

## The Finding

**Skill instructions are injected as user messages (low authority) rather than system prompt content (high authority).** This architectural choice—not the skills themselves—explains the performance gap.

Vercel's research shows AGENTS.md (system prompt placement) achieves 100% pass rate vs 53% for skills. The difference isn't what's in the instructions, it's where they're placed.

## Read the Full Analysis

**[Read the blog post →](https://jrenaldi79.github.io/skills-research/blog-post.html)**

The blog post covers:
- How prompt authority hierarchy works
- Why placement matters more than content
- The evidence from intercepted API requests
- What this means for skill authors

## Research Artifacts

| File | Description |
|------|-------------|
| [blog-post.html](https://jrenaldi79.github.io/skills-research/blog-post.html) | Full analysis and writeup |
| [viewer.html](https://jrenaldi79.github.io/skills-research/viewer.html) | Interactive context inspector |
| [index.html](https://jrenaldi79.github.io/skills-research/index.html) | Landing page |
| `log_parser.py` | Python script to parse Claude Code Router logs |
| `sample_data.json` | Structured JSON of intercepted API data |

## Methodology

This research used [Claude Code Router](https://github.com/musistudio/claude-code-router) to intercept API requests between Claude Code and the LLM provider. By examining the full request payloads, we could see exactly where skill content appears in the prompt hierarchy.

See the blog post for detailed methodology and reproduction steps.

## References

- [Vercel: AGENTS.md Outperforms Skills](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals)
- [Claude Code Router](https://github.com/musistudio/claude-code-router)
- [Anthropic Prompt Caching Docs](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)

## Author

**John Renaldi** — Adjunct Professor at Northwestern & University of Illinois Grainger College of Engineering

[LinkedIn](https://linkedin.com/in/renaldi) · [Email](mailto:jrenaldi@northwestern.edu)

---

*No affiliation with Anthropic, Vercel, or OpenRouter. Independent research.*
