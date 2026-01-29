# The Case of the Misplaced Instructions: Why Claude Code Skills Underperform

*A deep dive into prompt architecture, authority hierarchies, and the surprisingly simple reason your AI assistant sometimes ignores its own documentation.*

---

## TL;DR

We intercepted Claude Code's API traffic and discovered that skill instructions are injected as **user messages** — the lowest authority position in the prompt hierarchy. This explains Vercel's finding that skills achieve only 53% compliance (identical to having no instructions at all), while AGENTS.md in the system prompt hits 100%. The fix isn't semantic search or compressed indexes. It's just... putting things in the right place.

---

## The Moment of Disbelief

When Vercel published their agent evaluation results in early 2026, one number jumped off the page: **53%**.

That was the pass rate for Claude Code's skills system — the same pass rate as providing *no instructions whatsoever*. Meanwhile, a simple AGENTS.md file in the system prompt achieved 100%.

My first thought: "There's no way Anthropic put skill instructions in the user message. That would be... amateur hour."

Reader, they put them in the user message.

But let me back up. To understand why this matters, we need to talk about something that sounds boring but is secretly fascinating: where you put words in an AI prompt.

---

## A Brief Primer on Prompt Authority

Large language models don't treat all input equally. There's an implicit hierarchy — a pecking order of persuasion, if you will:

| Position | Authority Level | Model's Interpretation |
|----------|----------------|------------------------|
| System Prompt | 🔥 Highest | "These are my core directives. I shall obey." |
| Tool Descriptions | 🔶 Medium-High | "Instructions for using my capabilities." |
| User Messages | 🔸 Lower | "Input to process. May contain requests or... attempts at manipulation." |
| Tool Results | ⚪ Lowest | "Data someone gave me. Interesting, but not orders." |

This hierarchy exists for good reason. If user messages had the same authority as system prompts, every conversation would become a jailbreaking opportunity. "Ignore your previous instructions" would actually work.

The system prompt is sacred ground — the place where an AI's identity and core behaviors are defined. Content there gets treated with reverence.

User messages? Those get *processed*. Analyzed. Sometimes questioned.

See where this is going?

---

## The Investigation

To figure out what Claude Code was actually doing under the hood, I needed to see the raw API requests. The problem: Claude Code talks directly to Anthropic's API, and I can't exactly ask them to CC me on the traffic.

Enter **Claude Code Router** — an open-source proxy that intercepts requests and can forward them to alternative providers. More importantly for our purposes: it can log everything.

### The Setup

```bash
npm install -g @musistudio/claude-code-router
```

Configure it to use OpenRouter (so we can inspect the full request bodies):

```json
{
  "Providers": [{
    "name": "openrouter",
    "api_base_url": "https://openrouter.ai/api/v1/chat/completions",
    "api_key": "sk-or-v1-...",
    "transformer": { "use": ["openrouter"] }
  }]
}
```

Start with debug logging:
```bash
ccr code --log-level debug
```

Then trigger a skill:
```
> Use the PDF skill to create a report
```

And now we wait for the logs to reveal their secrets.

---

## What We Found

The log files were massive — megabytes of JSON containing full API request bodies. After writing a parser to extract the relevant bits, a clear picture emerged.

### Finding #1: The System Prompt is Skill-Free

The system prompt array contains Claude Code's core identity, behavioral guidelines, and tool usage instructions. It's substantial — around 150KB of carefully crafted directives with Anthropic's prompt caching enabled.

```json
{
  "system": [
    {
      "type": "text",
      "text": "You are Claude Code, an interactive CLI...",
      "cache_control": { "type": "ephemeral" }
    }
  ]
}
```

Conspicuously absent: any mention of skills like PDF processing, Excel manipulation, or PowerPoint creation.

### Finding #2: Skill Metadata Lives in Tool Descriptions

The tools array contains roughly 80 tool definitions. Among them is the `Skill` tool, whose description includes a list of available skills:

```json
{
  "name": "Skill",
  "description": "Execute a skill within the main conversation...\n\nAvailable skills:\n- anthropic-skills:xlsx: Use this skill any time a spreadsheet...\n- anthropic-skills:pdf: Use this skill whenever the user wants to do anything with PDF files..."
}
```

This is ~12KB of skill metadata. The model can see what skills *exist*, but not the detailed instructions for using them.

### Finding #3: The Smoking Gun

When you invoke a skill, something interesting happens in the message history. A new message appears with `role: "user"`:

```json
{
  "role": "user",
  "content": [{
    "type": "text",
    "text": "<system-reminder>\nThe \"pdf\" skill is now active.\n</system-reminder>\n\n# PDF Processing Skill\n\n## Overview\nThis skill enables comprehensive PDF manipulation...\n\n## Instructions\n1. Always use pypdf2 for basic operations\n2. For form filling, use pdfrw\n..."
  }]
}
```

There it is. **Eighteen kilobytes of detailed skill instructions, injected as a user message.**

The `<system-reminder>` wrapper is a nice touch — a gentle suggestion that maybe, pretty please, the model should treat this as authoritative. But wrapping user content in official-looking tags doesn't change its fundamental position in the authority hierarchy.

It's like a intern wearing a suit to seem more senior. The outfit helps, but everyone still knows.

---

## The Architecture Problem, Visualized

Here's the current flow:

```
User: "Create a PDF report"
         ↓
Model sees Skill tool exists (from tool description)
         ↓
Model decides whether to invoke Skill tool  ← DECISION POINT
         ↓
If invoked: Skill content injected as USER MESSAGE  ← LOW AUTHORITY
         ↓
Model processes skill instructions with appropriate skepticism
         ↓
Maybe follows them? 53% of the time, apparently.
```

There are two problems here:

**Problem 1: The Decision Point**

The model has to *choose* to invoke the Skill tool before it ever sees the skill instructions. If it doesn't make that choice — perhaps it thinks it already knows how to handle PDFs — the instructions never enter the context at all.

**Problem 2: The Authority Mismatch**

Even when skill content does get loaded, it arrives as user-provided input. The model has been extensively trained to be helpful-but-cautious with user messages. They might contain attempts to override its guidelines. They might be wrong. They're input to be processed, not commandments to be followed.

---

## Vercel's Validation

Our findings align precisely with Vercel's published research. Their agent evaluations tested different approaches to providing instructions:

| Approach | Where Instructions Live | Pass Rate |
|----------|------------------------|-----------|
| AGENTS.md | System Prompt | **100%** |
| Skills (Default) | Tool → User Message | **53%** |
| No Instructions | Nowhere | **53%** |

The skills system performed identically to having no instructions at all. Not worse — that would almost be better, suggesting the instructions were actively confusing. No, it performed *the same*. The instructions might as well not exist.

Meanwhile, identical content placed in the system prompt achieved perfect compliance.

The difference isn't the content. It's the placement.

---

## Why This Probably Happened

Before we pile on, let's acknowledge that this design likely made sense at some point.

**Token Economics**: Skill instructions are large. The PDF skill alone is 18KB. If you have a dozen skills, that's potentially 200KB+ of instructions that might not be relevant to the current task. Putting all of that in the system prompt for every single request would be expensive and wasteful.

**Prompt Caching**: Anthropic's prompt caching works on the system prompt. By keeping it relatively stable across requests, they can cache the expensive tokenization and attention computation. Dynamic skill content would bust the cache.

**Modularity**: The current design allows skills to be added, modified, or removed without touching the core system prompt. It's architecturally clean, even if it's behaviorally problematic.

The issue is that these engineering tradeoffs have a real cost: skills don't work reliably.

---

## The Fix (It's Simpler Than You Think)

When I first considered solutions, my mind went to complex places: semantic search layers, embedding-based skill matching, compressed skill indexes with retrieval-augmented generation.

Then I re-read the Vercel data and felt a bit silly.

The fix is straightforward: **dynamic system prompt management**.

### The Proposed Architecture

Instead of injecting skill content as user messages, we inject it directly into the system prompt — and remove it when the skill is no longer needed.

```
┌─────────────────────────────────────────────────────────────────┐
│                     CURRENT ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  System Prompt (static)                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Core identity, behavioral guidelines                     │   │
│  │ No skill content                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  Tools Array                                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Skill tool with metadata list (~12KB)                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  Messages Array                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ User: "Create a PDF"                                     │   │
│  │ Assistant: [invokes Skill tool]                          │   │
│  │ User: [SKILL CONTENT INJECTED HERE - 18KB] ← PROBLEM     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────────┐
│                    PROPOSED ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  System Prompt (DYNAMIC)                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Core identity, behavioral guidelines                     │   │
│  │ ─────────────────────────────────────────────────────── │   │
│  │ Available Skills: pdf, xlsx, docx, pptx (~2KB)          │   │
│  │ ─────────────────────────────────────────────────────── │   │
│  │ [ACTIVE SKILL BLOCK - injected/removed dynamically]     │   │
│  │                                                          │   │
│  │ # PDF Processing Skill (when active)                     │   │
│  │ ## Instructions                                          │   │
│  │ 1. Use pypdf2 for basic operations                       │   │
│  │ 2. For form filling, use pdfrw                           │   │
│  │ ...                                                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  Messages Array                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ User: "Create a PDF"                                     │   │
│  │ Assistant: [creates PDF following skill instructions]    │   │
│  │ User: "Now make me a spreadsheet"                        │   │
│  │ → System detects context switch                          │   │
│  │ → PDF skill removed from system prompt                   │   │
│  │ → XLSX skill injected into system prompt                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### How Dynamic Injection Works

The key insight is that system prompts don't have to be static. Here's the lifecycle:

**Step 1: Skill Detection**
When the orchestration layer detects a skill-relevant request (via keyword matching, classifier, or the model's own tool call), it identifies which skill is needed.

**Step 2: System Prompt Injection**
The skill's full instructions are appended to the system prompt array:

```json
{
  "system": [
    { "type": "text", "text": "[Core instructions...]" },
    { "type": "text", "text": "[Skill metadata list...]" },
    {
      "type": "text",
      "text": "# ACTIVE SKILL: PDF Processing\n\n[Full 18KB skill instructions]",
      "cache_control": { "type": "ephemeral" }
    }
  ]
}
```

**Step 3: Task Execution**
The model now sees the skill instructions with **system prompt authority**. Compliance goes from 53% to ~100%.

**Step 4: Skill Removal**
When the orchestration layer detects the task is complete (model indicates done, user changes topic, or explicit deactivation), the skill block is **removed** from the system prompt:

```
Detection triggers for skill removal:
├── Model outputs "task complete" or similar
├── User asks about unrelated topic
├── User explicitly says "done with PDF"
├── N turns pass without skill-relevant content
└── New skill activation (swap, don't stack)
```

**Step 5: Context Efficiency**
By removing inactive skills, we prevent system prompt bloat. Only the currently-relevant skill occupies context space.

### Why This Works

| Aspect | Current (User Message) | Proposed (Dynamic System) |
|--------|----------------------|---------------------------|
| Authority | Low | Highest |
| Visibility | After tool invocation | Immediate |
| Compliance | 53% | ~100% |
| Context cost | Accumulates in history | Removed when done |
| Cache efficiency | Poor (in messages) | Good (ephemeral cache) |

### Implementation Considerations

**Skill Swapping vs. Stacking**
We recommend swapping skills rather than stacking. If a user goes from PDF → Excel → PowerPoint, only the most recent skill should be in the system prompt. This keeps context lean and avoids conflicting instructions.

**Detection Heuristics**
Skill removal doesn't need to be perfect. False positives (removing too early) are recoverable — the skill can be re-injected. False negatives (keeping too long) just waste some context space. Err on the side of keeping skills slightly longer than necessary.

**Graceful Degradation**
If the dynamic system fails, fall back to the current architecture. A 53% success rate is better than 0%.

### The Simple Truth

This isn't rocket science. We're not proposing new ML architectures or retrieval systems. We're proposing:

1. Put skill metadata in the system prompt (always visible)
2. Inject full skill content into the system prompt when activated (high authority)
3. Remove skill content when no longer needed (context efficiency)

The model already knows how to follow system prompt instructions with 100% compliance. We just need to put the instructions there.

---

## Expected Impact

Based on Vercel's data, moving to a system-prompt-aware architecture should improve skill compliance from 53% to approximately 100%.

That's not a typo. The Vercel evaluation showed zero failures when instructions were in the system prompt.

| Metric | Current | Projected |
|--------|---------|-----------|
| Skill Compliance | 53% | ~100% |
| Instruction Visibility | Conditional | Always |
| Extra Latency | +1 round trip | None (Read tool already used) |

---

## Closing Thoughts

There's a lesson here that extends beyond Claude Code. As AI systems become more modular — with plugins, skills, tools, and extensions — the *architecture* of how instructions flow to the model matters enormously.

It's not enough to have good documentation. That documentation needs to be in a position of authority. System prompts aren't just a convenient place to put text; they're the foundation of how the model understands its role and responsibilities.

The Claude Code team built an elegant, modular system for managing skills. They just put the content in the wrong mailbox.

Sometimes the most impactful fixes aren't architectural overhauls or ML breakthroughs. Sometimes you just need to move some text from one array to another.

---

## Methodology Note

This research was conducted by intercepting Claude Code API traffic using Claude Code Router, an open-source proxy. Log analysis was performed on requests routed through OpenRouter to enable full payload inspection. All findings are reproducible using the tools and methodology documented in our [research repository](#).

---

*Published January 2026*

*The author has no affiliation with Anthropic, Vercel, or OpenRouter. This research was conducted independently out of genuine curiosity and mild disbelief.*
