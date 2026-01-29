# Skills Aren't Broken, Claude Code's Implementation Is

*Vercel's research shows skills achieve just a 53% pass rate. The surprisingly simple reason? Someone put the instructions in the wrong place.*

---

## TL;DR

**There's nothing wrong with Claude Code's skills as a concept.** Modular, specialized instructions that load on-demand? That's smart engineering. The problem is the implementation. Two problems, actually.

**Problem 1: It's architecturally wrong.** I captured Claude Code's actual API requests and discovered that skill instructions get injected as **user messages**, the lowest authority position in the prompt hierarchy. This explains why [Vercel's agent evaluation](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals) found that skills achieve only 53% pass rate (the same as having *no instructions at all*), while AGENTS.md in the system prompt hits 100%.

**Problem 2: It doesn't follow Anthropic's own spec.** Anthropic published an [open spec for Agent Skills](https://agentskills.io) that explicitly says skill metadata belongs in the system prompt. Claude Code puts it in tool descriptions instead. That's a direct spec violation.

Two mistakes. One product. The skills aren't broken. The implementation is.

---

## Wait, What?

Vercel just published their [agent evaluation results](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals) this week. One number shocked me: **53%**.

That was the pass rate for Claude Code's skills system. The same pass rate as providing zero instructions. Meanwhile, a simple AGENTS.md file in the system prompt achieved 100%.

My first reaction was to blame the skills themselves. Maybe they were poorly written, or too verbose, or conflicting with the base prompt somehow. But the more I dug in, the clearer it became: the skill content is actually good. The problem is purely mechanical.

My next thought: "There's no way Anthropic put skill instructions in the user message. That would be... I mean, come on."

They put them in the user message.

But let me back up. To understand why this matters, we need to talk about something that sounds dry but is actually pretty fascinating: where you put words in an AI prompt.

---

## The Pecking Order

Large language models don't treat all input equally. There's a hierarchy:

| Position | Authority Level | What the Model Thinks |
|----------|----------------|------------------------|
| System Prompt | Highest | "These are my orders. I follow these." |
| Tool Descriptions | Medium-High | "Instructions for my capabilities." |
| User Messages | Lower | "Input to process. Might be legit. Might be someone trying to trick me." |
| Tool Results | Lowest | "Data. Interesting, but not my boss." |

This hierarchy exists for good reason. If user messages had the same authority as system prompts, every conversation would be a jailbreaking opportunity. "Ignore your previous instructions" would actually work.

The system prompt is sacred ground. It's where an AI's identity and core behaviors get defined. Content there gets treated with reverence.

User messages? Those get *processed*. Analyzed. Sometimes questioned.

---

## Down the Rabbit Hole

To figure out what Claude Code was actually doing under the hood, I needed to see the raw API requests. Problem: Claude Code talks directly to Anthropic's API, and they're not exactly CC'ing me on the traffic.

Enter **Claude Code Router**, an open-source proxy that intercepts requests and can forward them to alternative providers. More importantly for my purposes: it logs everything.

### The Setup

```bash
npm install -g @musistudio/claude-code-router
```

Configure it to use OpenRouter so I can inspect the full request bodies:

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

Fire it up with debug logging:
```bash
ccr code --log-level debug
```

Then trigger a skill:
```
> Use the PDF skill to create a report
```

And wait.

---

## What the Logs Revealed

The log files were massive. Megabytes of JSON containing full API request bodies. After writing a parser to extract the relevant bits (because apparently that's how I spend my evenings now), a clear picture emerged.

### Finding #1: The System Prompt is Skill-Free

The system prompt contains Claude Code's core identity, behavioral guidelines, and tool usage instructions. It's substantial, with Anthropic's prompt caching enabled.

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

The model can see what skills *exist*, but not the detailed instructions for using them.

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

There it is. **The skill instructions get injected as a user message.**

And here's a detail that surprised me: the skill content doesn't even have `cache_control` set. Anthropic's system prompt uses `{"cache_control": {"type": "ephemeral"}}` to enable prompt caching, but skill messages? No caching by default. It's possible caching kicks in after more conversational turns, but I didn't see it in my testing.

The `<system-reminder>` wrapper is a nice touch. A gentle suggestion that maybe the model should treat this as authoritative. But wrapping user content in official-looking tags doesn't change its fundamental position in the authority hierarchy.

It's like an intern wearing a suit to the board meeting. The outfit helps, but everyone still knows.

---

## The Authority Problem

Here's the current flow:

```
User: "Create a PDF report"
         ↓
Model sees Skill tool exists (from tool description)  ← MEDIUM AUTHORITY
         ↓
Model invokes Skill tool
         ↓
Skill content injected as USER MESSAGE  ← LOW AUTHORITY
         ↓
Model processes skill instructions with appropriate skepticism
         ↓
Maybe follows them? 53% of the time, apparently.
```

The issue isn't visibility. The model can see what skills exist via the tool descriptions. The issue is **authority** at every level.

**Problem 1: Metadata in the Wrong Place**

Skill metadata (names, descriptions) lives in the tool description instead of the system prompt. Tool descriptions have medium authority - the model treats them as instructions for capabilities, not core directives. The spec explicitly says metadata belongs in the system prompt for a reason.

**Problem 2: Skill Content Has Lowest Authority**

When skill content does get loaded, it arrives as a user message. The model's been extensively trained to be helpful-but-cautious with user messages. They might contain attempts to override guidelines. They might be wrong. They're input to be processed, not commandments to be followed.

Both problems are the same underlying issue: instructions that should have system-level authority are placed where they get treated as suggestions.

---

## Vercel's Numbers Back This Up

[Vercel's agent evaluation](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals), published this week, tested different approaches to providing instructions:

| Approach | Where Instructions Live | Pass Rate |
|----------|------------------------|-----------|
| AGENTS.md | System Prompt | **100%** |
| Skills (Default) | Tool → User Message | **53%** |
| No Instructions | Nowhere | **53%** |

The skills system performed identically to having no instructions at all. Not worse (that would almost be better, suggesting the instructions were actively confusing). No, it performed *the same*. The instructions might as well not exist.

Meanwhile, identical content placed in the system prompt achieved perfect pass rate.

The difference isn't the content. It's the placement.

---

## The Kicker: Anthropic Published a Spec. Then Ignored It.

Anthropic published Agent Skills as an [open specification](https://agentskills.io). The spec is unambiguous about one thing: **skill metadata belongs in the system prompt**.

From the [integration guide](https://agentskills.io/integrate-skills):

> "Include skill metadata **in the system prompt** so the model knows what skills are available."

From their [official platform docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview):

> "Claude loads this metadata at startup and **includes it in the system prompt**."

From their [engineering blog](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills):

> "At startup, the agent pre-loads the name and description of every installed skill **into its system prompt**."

The spec provides the recommended format:

```xml
<available_skills>
  <skill>
    <name>pdf-processing</name>
    <description>Extracts text and tables from PDF files...</description>
    <location>/path/to/skills/pdf-processing/SKILL.md</location>
  </skill>
</available_skills>
```

**What does Claude Code actually do?**

Skill metadata goes in the **Tool description**, not the system prompt. That's a direct violation of the spec.

The spec is less explicit about where the *full* SKILL.md content should go after being triggered. It says Claude "reads SKILL.md from the filesystem" and the content "enters the context window." But Claude Code injects it as a **user message** with a `<system-reminder>` wrapper. Given what we know about prompt authority hierarchies, that's the worst possible choice.

So we have:
1. **Metadata placement**: Spec says system prompt. Claude Code uses tool descriptions. Wrong.
2. **Full skill content**: Spec is vague. Claude Code uses user messages (lowest authority). Also wrong.

Anthropic wrote a spec. Published it as an open standard. Then their flagship product didn't follow it.

---

## Why This Probably Made Sense at the Time

Before we pile on, let's acknowledge that this design choice was probably reasonable when it was made. The *concept* is sound. The *implementation* just needs adjustment.

**Token Economics**: Skill instructions are large. A single skill can be thousands of tokens. If you have a dozen skills, you're looking at tens of thousands of tokens that might not be relevant to the current task. Putting all of that in the system prompt for every request would be expensive and wasteful. This is a real concern, but it's solvable.

**Prompt Caching**: Anthropic's prompt caching works on the system prompt. By keeping it relatively stable across requests, they can cache the expensive tokenization and attention computation. Dynamic skill content would bust the cache. This is a real concern, though ironically the current implementation doesn't even cache skill content in user messages - it gets re-tokenized every time anyway.

**Modularity**: The current design allows skills to be added, modified, or removed without touching the core system prompt. Architecturally clean, even if behaviorally problematic.

These are legitimate engineering tradeoffs. But the current implementation has a real cost: the skills just don't work reliably. And the fix doesn't require abandoning these goals. It just requires being smarter about when and how skills get injected.

---

## The Good News: Skills Can Work

**Skills are a great idea.** The concept of modular, on-demand instructions that specialize a general-purpose agent? That's exactly right. The architecture on paper is sound. It just got implemented wrong.

And we know it can work because Vercel already proved it. When they put the same instructions in the system prompt instead of a user message, pass rate jumped from 53% to 100%. Not 60%. Not 80%. **One hundred percent.**

The fix isn't theoretical. It's been validated.

---

## Two Recommendations

### Recommendation 1: Fix the Bug (Follow the Spec)

This one's simple. The spec says skill metadata belongs in the system prompt. Claude Code puts it in tool descriptions. Fix that.

Move the `<available_skills>` block from the Tool description into the system prompt where the spec says it should be. This ensures the model always knows what skills exist and when to use them, with system-level authority.

### Recommendation 2: Dynamic Skill Injection (Our Proposal)

The spec is vague about where full skill content should go after being triggered. Our recommendation: **inject it into the system prompt dynamically, then remove it when the task is done.**

This is different from what Claude Code does today (user message injection) and goes beyond what the spec explicitly requires. But it's the architecture that actually works.

**Current Architecture:**
```
System Prompt (static)
├── Core identity, behavioral guidelines
└── No skill content

Tools Array
├── Skill tool with metadata list
└── ~80 other tools

Messages Array
├── User: "Create a PDF"
├── Assistant: [invokes Skill tool]
└── User: [SKILL CONTENT] ← PROBLEM (low authority)
```

**Proposed Architecture:**
```
System Prompt (DYNAMIC)
├── Core identity, behavioral guidelines
├── Available Skills metadata  ← Per spec
└── [ACTIVE SKILL BLOCK - injected/removed as needed]
    └── Full PDF instructions when active

Messages Array
├── User: "Create a PDF"
├── Assistant: [creates PDF following instructions]  ← Just works
├── User: "Now make a spreadsheet"
└── → System swaps PDF skill out, XLSX skill in
```

### The Lifecycle

**Step 1: Skill Detection.** When the orchestration layer detects a skill-relevant request (via keyword matching, classifier, or the model's own tool call), it identifies which skill is needed.

**Step 2: System Prompt Injection.** The skill's full instructions are appended to the system prompt array with system-level authority.

**Step 3: Task Execution.** The model sees the skill instructions as core directives. Pass Rate goes from 53% to ~100%.

**Step 4: Skill Removal.** When the task is complete (model indicates done, user changes topic, or explicit deactivation), the skill block gets removed from the system prompt.

**Step 5: Context Efficiency.** By removing inactive skills, you prevent system prompt bloat. Only the currently-relevant skill occupies context space.

### Why Dynamic Injection Works

| Aspect | Current (User Message) | Proposed (Dynamic System) |
|--------|----------------------|---------------------------|
| Authority | Low | Highest |
| Visibility | After tool invocation | Immediate |
| Pass Rate | 53% | ~100% |
| Context cost | Accumulates in history | Removed when done |
| Cache efficiency | Poor (in messages) | Good (ephemeral cache) |

---

## Implementation Considerations: Cache & Context Management

There's an obvious objection to dynamic system prompt injection: "Won't that bust the cache?"

Yes. And no. It depends on how you structure it.

### How Anthropic's Cache Actually Works

Anthropic's prompt caching is **prefix-based**. Content is cached from the beginning of the system prompt up to each `cache_control` breakpoint. If you change anything, content *after* that point is invalidated—but content *before* it stays cached.

This means architecture matters:

```
[Core Claude Code instructions - 50k tokens]  ← ALWAYS CACHED
[cache_control breakpoint]
[Skill metadata - 2k tokens]                  ← Cached separately
[cache_control breakpoint]  
[Active skill content - 15k tokens]           ← Can change without busting above
[cache_control breakpoint]
```

If you put skills **at the end** of the system prompt with their own cache breakpoint, swapping skills only invalidates the skill portion. The core instructions (the bulk of the tokens) remain cached.

### The Tradeoff Is Worth It

Current implementation: No cache benefit for skills (they're in user messages) + 53% compliance.

Proposed implementation: Core instructions stay cached + skill portion may invalidate on swap + ~100% compliance.

That's not a hard choice. You're trading partial cache invalidation for a 47-point improvement in pass rate.

### The Harder Problem: When to Retire a Skill

This is where it gets interesting. If skills live in the system prompt, when do you remove them? This isn't just a cache question—it's a **context window** question.

A single skill can be 10-20k tokens. If a user activates three skills in a session, you're looking at 30-60k tokens of skill instructions competing with actual conversation for context space. That's not sustainable.

**Proposed Retirement Logic:**

1. **Explicit deactivation.** User says "I'm done with PDF stuff" or invokes a different skill that's clearly unrelated.

2. **Task completion signal.** The model indicates the skill-related task is complete. This could be explicit ("Your PDF has been created") or implicit (conversation moves to unrelated topic for N turns).

3. **Context budget threshold.** This is the interesting one. The orchestration layer should track what percentage of the context window is consumed by active skills. When it crosses a threshold (say, 15-20%), start pruning.

**Pruning Priority:**
- Oldest activated skill first (LRU)
- Skills not referenced in the last N messages
- Skills with lower relevance scores to recent conversation

4. **Graceful degradation.** When a skill is retired, don't just delete it. Move its metadata back to the "available but not active" list. The model still knows the skill exists and can re-activate it if needed.

### Open Questions

This framework raises questions that need empirical testing:

- **Optimal threshold:** What's the right context budget for skills? 10%? 20%? Probably depends on the task complexity.

- **Re-activation cost:** If a skill gets pruned and immediately re-activated, you've wasted tokens. How do you predict skill stickiness?

- **Multi-skill interactions:** Some tasks legitimately need multiple skills active simultaneously (PDF extraction → Excel analysis → PowerPoint presentation). How do you handle skill chains without blowing the budget?

- **Cache warming:** When you know a skill is likely needed (based on file types in the workspace, recent conversation patterns), should you preemptively inject it to warm the cache?

These aren't blockers. They're implementation details that require tuning. The core architecture—skills in system prompt with intelligent lifecycle management—is sound. The specifics need experimentation.

---

### The Simple Truth

This isn't rocket science. I'm not proposing new ML architectures or retrieval systems. I'm proposing:

1. Put skill metadata in the system prompt (per the spec)
2. Inject full skill content into the system prompt when activated (for authority)
3. Remove skill content when no longer needed (for efficiency)

The model already knows how to follow system prompt instructions with 100% pass rate. Vercel proved it. You just need to put the instructions there.

---

## What This Means

Skills can work. Vercel proved it. Their evaluation showed that when instructions are in the system prompt, pass rate is 100%. Not projected. Measured.

| Metric | Current | With System Prompt (Vercel) |
|--------|---------|-----------|
| Skill Pass Rate | 53% | **100%** |
| Instruction Visibility | Conditional | Always |
| Extra Latency | +1 round trip | None |

This isn't a theoretical improvement. It's a validated fix waiting to be implemented.

---

## The Bigger Picture

There's a lesson here that extends beyond Claude Code. As AI systems become more modular (plugins, skills, tools, extensions), the *architecture* of how instructions flow to the model matters enormously. Where you put text isn't just an implementation detail. It determines whether the model treats your instructions as orders or suggestions.

System prompts aren't just a convenient place to put text. They're the foundation of how the model understands its role and responsibilities. Put your instructions in the wrong mailbox, and they might as well not exist.

---

## Methodology

This research was conducted using **Claude Code version 2.1.20**, intercepting API traffic using Claude Code Router, an open-source proxy. Log analysis was performed on requests routed through OpenRouter to enable full payload inspection. All findings are reproducible using the tools and methodology documented in the [research repository](https://github.com/jrenaldi79/skills-research).

---

*Published January 2026*

*No affiliation with Anthropic, Vercel, or OpenRouter. Just genuine curiosity and mild disbelief.*
