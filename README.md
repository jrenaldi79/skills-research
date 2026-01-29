# Claude Code Skills Architecture Research

## Research Objective

Understand how Claude Code transmits skill instructions to the LLM API and identify architectural factors affecting skill compliance rates.

## Key Finding

**Skill content is injected as user messages (low authority) rather than system prompt content (high authority).** This placement issue explains the 53% pass rate observed in Vercel's agent evaluations compared to 100% for AGENTS.md (system prompt placement).

---

## Methodology

### Prerequisites

- Node.js 18+ installed
- An OpenRouter API key (get one at https://openrouter.ai)
- Claude Code CLI installed (`npm install -g @anthropic-ai/claude-code`)

### Step 1: Install Claude Code Router

Claude Code Router is a proxy that intercepts Claude Code API requests and forwards them to alternative LLM providers. This allows us to inspect the full API request/response payloads.

```bash
# Install globally (use prefix if you encounter permission errors)
npm install -g @musistudio/claude-code-router

# Or with custom prefix to avoid sudo
npm install -g @musistudio/claude-code-router --prefix ~/.npm-global
export PATH="$HOME/.npm-global/bin:$PATH"
```

Verify installation:
```bash
ccr --version
```

### Step 2: Configure OpenRouter Provider

Create or edit the configuration file at `~/.claude-code-router/config.json`:

```json
{
  "Providers": [
    {
      "name": "openrouter",
      "api_base_url": "https://openrouter.ai/api/v1/chat/completions",
      "api_key": "sk-or-v1-YOUR_API_KEY_HERE",
      "models": [
        "google/gemini-2.5-pro-preview",
        "google/gemini-2.5-flash",
        "anthropic/claude-sonnet-4"
      ],
      "transformer": {
        "use": ["openrouter"]
      }
    }
  ],
  "Router": {
    "default": "openrouter,google/gemini-2.5-pro-preview"
  }
}
```

**Important:** The `transformer` must be set to `["openrouter"]` — not `"Anthropic"`. Using the wrong transformer causes 401 authentication errors.

### Step 3: Enable Logging

Start the router with logging enabled:

```bash
ccr code --log-level debug
```

This creates timestamped log files at:
```
~/.claude-code-router/logs/ccr-YYYYMMDDHHMMSS.log
```

The logs contain full API request bodies including:
- System prompt array with cache control settings
- Complete tools array (80+ tools)
- Full message history with skill content

### Step 4: Trigger Skill Loading

In the Claude Code session (now proxied through the router), invoke a skill:

```
> Use the PDF skill to help me create a document
```

Or directly:
```
> /pdf
```

This triggers the Skill tool invocation, which injects skill content into the conversation.

### Step 5: Analyze the Logs

Stop the router (`Ctrl+C`) and examine the log files:

```bash
# Find the latest log
ls -la ~/.claude-code-router/logs/

# The logs are JSON-lines format (one JSON object per line)
# Look for lines containing the API request body
```

#### What to Look For

**1. System Prompt (search for `"system":`)**
```json
{
  "system": [
    {
      "type": "text",
      "text": "[Core Claude Code instructions...]",
      "cache_control": { "type": "ephemeral" }
    }
  ]
}
```
Note: System prompt does NOT contain skill content.

**2. Skill Tool Definition (search for `"name":"Skill"`)**
```json
{
  "name": "Skill",
  "description": "Execute a skill within the main conversation...\n\nAvailable skills:\n- anthropic-skills:xlsx: Use this skill any time a spreadsheet...\n- anthropic-skills:pdf: Use this skill whenever...",
  "input_schema": { ... }
}
```
This contains skill metadata (~12KB) but not full instructions.

**3. Skill Content Injection (search for `system-reminder` or skill name)**
```json
{
  "role": "user",
  "content": [{
    "type": "text",
    "text": "<system-reminder>\nThe \"pdf\" skill is now active...\n</system-reminder>\n\n# PDF Processing Skill\n\n[Full skill instructions ~18KB]"
  }]
}
```
**This is the key finding:** Skill content arrives as a USER message, not system prompt.

### Step 6: Use the Log Parser (Optional)

We've included a Python script to automate log analysis:

```bash
python log_parser.py ~/.claude-code-router/logs/ccr-*.log --pretty -o parsed_output.json
```

The parser extracts:
- System prompt blocks with cache control info
- Skill tool definition from tools array
- Skill content in message history
- Statistics on message types

---

## Research Artifacts

| File | Description |
|------|-------------|
| `viewer.html` | Interactive HTML presentation of findings |
| `log_parser.py` | Python script to parse CCR logs |
| `sample_data.json` | Structured JSON summary of findings |

Open `viewer.html` in a browser for the full research presentation.

---

## Findings Summary

### Prompt Authority Hierarchy

| Level | Component | Authority | Skill Content? |
|-------|-----------|-----------|----------------|
| 1 | System Prompt | Highest | ❌ No |
| 2 | Tool Description | Medium-High | ⚠️ Metadata only |
| 3 | User Message | Lower | ✅ Full content here |
| 4 | Tool Result | Lowest | ❌ No |

### Current Architecture Flow

```
User: "Use PDF skill"
         ↓
Model sees Skill tool in tools array (with skill list)
         ↓
Model decides to invoke Skill tool  ← DECISION POINT (may not invoke)
         ↓
Skill content injected as USER MESSAGE  ← LOW AUTHORITY PLACEMENT
         ↓
Model may or may not follow skill instructions
```

### Vercel's Comparative Research

Source: https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals

| Approach | Placement | Pass Rate | Improvement |
|----------|-----------|-----------|-------------|
| AGENTS.md | System Prompt | 100% | +47% |
| Skills (Default) | User Message | 53% | 0% |
| No Instructions | — | 53% | Baseline |

**Conclusion:** Placement in system prompt is the critical factor for instruction compliance.

---

## Recommendations

1. **Move skill metadata to system prompt** — Model should always see available skills without tool invocation

2. **Use Read tool for skill content** — Have models read SKILL.md files via Read tool (tool results have higher authority than user messages)

3. **Remove the decision point** — Don't require the model to invoke a Skill tool to discover skill information

---

## Troubleshooting

### 401 "User not found" Error
- Verify your OpenRouter API key is valid: `curl -H "Authorization: Bearer $API_KEY" https://openrouter.ai/api/v1/auth/key`
- Ensure `transformer` is set to `["openrouter"]` not `"Anthropic"`

### Logs Not Appearing
- Ensure you started with `--log-level debug`
- Check `~/.claude-code-router/logs/` directory exists
- Restart with `ccr restart`

### Permission Errors on npm Install
- Use `--prefix ~/.npm-global` flag
- Add `~/.npm-global/bin` to your PATH

---

## References

- Claude Code Router: https://github.com/musistudio/claude-code-router
- OpenRouter API: https://openrouter.ai/docs
- Vercel AGENTS.md Research: https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals
- Anthropic Prompt Caching: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching

---

## Research Date

January 28, 2026
