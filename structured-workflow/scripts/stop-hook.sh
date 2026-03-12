#!/bin/bash

# Structured Workflow Stop Hook
# 项目级 stop hook，部署时被复制到 .claude/hooks/structured-workflow-stop.sh
# 阻止会话退出并喂 prompt 以实现自动循环执行

set -euo pipefail

# Flag for deferred self-deletion (set by cleanup_hook)
_CLEANUP_SELF=0
_cleanup_on_exit() {
  if [[ $_CLEANUP_SELF -eq 1 ]]; then
    local self_path=".claude/hooks/structured-workflow-stop.sh"
    rm -f "$self_path" 2>/dev/null || true
    # Clean up empty hooks directory
    if [[ -d ".claude/hooks" ]] && [[ -z "$(ls -A .claude/hooks 2>/dev/null)" ]]; then
      rmdir ".claude/hooks" 2>/dev/null || true
    fi
  fi
}
trap _cleanup_on_exit EXIT

# Read hook input from stdin (advanced stop hook API)
HOOK_INPUT=$(cat)

# Check if state file exists
RALPH_STATE_FILE=".claude/structured-workflow-loop.local.md"

if [[ ! -f "$RALPH_STATE_FILE" ]]; then
  # No active loop - allow exit silently (residual hook, harmless)
  exit 0
fi

# Parse markdown frontmatter (YAML between ---) and extract values
FRONTMATTER=$(sed -n '/^---$/,/^---$/{ /^---$/d; p; }' "$RALPH_STATE_FILE")
ITERATION=$(echo "$FRONTMATTER" | grep '^iteration:' | sed 's/iteration: *//')
MAX_ITERATIONS=$(echo "$FRONTMATTER" | grep '^max_iterations:' | sed 's/max_iterations: *//')
COMPLETION_PROMISE=$(echo "$FRONTMATTER" | grep '^completion_promise:' | sed 's/completion_promise: *//' | sed 's/^"\(.*\)"$/\1/')

# Session isolation: only the session that started the loop should be affected.
# If session_id doesn't match, exit silently (don't block, don't clean up).
STATE_SESSION=$(echo "$FRONTMATTER" | grep '^session_id:' | sed 's/session_id: *//' || true)
HOOK_SESSION=$(echo "$HOOK_INPUT" | jq -r '.session_id // ""')
if [[ -n "$STATE_SESSION" ]] && [[ "$STATE_SESSION" != "$HOOK_SESSION" ]]; then
  exit 0
fi

# --- cleanup_hook: remove state file, deregister from settings.local.json, delete self ---
cleanup_hook() {
  # 1. Remove state file
  rm -f "$RALPH_STATE_FILE"

  # 2. Deregister from .claude/settings.local.json using jq
  local SETTINGS_FILE=".claude/settings.local.json"
  if [[ -f "$SETTINGS_FILE" ]] && command -v jq &>/dev/null; then
    local TEMP_FILE="${SETTINGS_FILE}.tmp.$$"
    # Remove hook entries containing "structured-workflow-stop"
    jq '
      if .hooks?.Stop then
        .hooks.Stop |= map(
          if .hooks then
            .hooks |= map(select(.command | tostring | contains("structured-workflow-stop") | not))
            | select(.hooks | length > 0)
          else . end
        )
        | if .hooks.Stop | length == 0 then del(.hooks.Stop) else . end
        | if .hooks | length == 0 then del(.hooks) else . end
      else . end
    ' "$SETTINGS_FILE" > "$TEMP_FILE" 2>/dev/null && mv "$TEMP_FILE" "$SETTINGS_FILE" || rm -f "$TEMP_FILE"
  fi

  # 3. Schedule self-deletion via trap (deferred to script exit)
  #    On Windows (Git Bash), deleting a running script may fail.
  #    By deferring to EXIT trap, we ensure all other work is done first.
  _CLEANUP_SELF=1
}

# Validate numeric fields before arithmetic operations
if [[ ! "$ITERATION" =~ ^[0-9]+$ ]]; then
  echo "⚠️  Structured workflow loop: State file corrupted" >&2
  echo "   File: $RALPH_STATE_FILE" >&2
  echo "   Problem: 'iteration' field is not a valid number (got: '$ITERATION')" >&2
  echo "   Loop is stopping. Run /structured-workflow:task-auto again to start fresh." >&2
  cleanup_hook
  exit 0
fi

if [[ ! "$MAX_ITERATIONS" =~ ^[0-9]+$ ]]; then
  echo "⚠️  Structured workflow loop: State file corrupted" >&2
  echo "   File: $RALPH_STATE_FILE" >&2
  echo "   Problem: 'max_iterations' field is not a valid number (got: '$MAX_ITERATIONS')" >&2
  echo "   Loop is stopping. Run /structured-workflow:task-auto again to start fresh." >&2
  cleanup_hook
  exit 0
fi

# Check if max iterations reached
if [[ $MAX_ITERATIONS -gt 0 ]] && [[ $ITERATION -ge $MAX_ITERATIONS ]]; then
  echo "🛑 Structured workflow loop: Max iterations ($MAX_ITERATIONS) reached."
  cleanup_hook
  exit 0
fi

# Get transcript path from hook input
TRANSCRIPT_PATH=$(echo "$HOOK_INPUT" | jq -r '.transcript_path')

if [[ ! -f "$TRANSCRIPT_PATH" ]]; then
  echo "⚠️  Structured workflow loop: Transcript file not found" >&2
  echo "   Expected: $TRANSCRIPT_PATH" >&2
  echo "   Loop is stopping." >&2
  cleanup_hook
  exit 0
fi

# Read last assistant message from transcript (JSONL format)
if ! grep -q '"role":"assistant"' "$TRANSCRIPT_PATH"; then
  echo "⚠️  Structured workflow loop: No assistant messages found in transcript" >&2
  echo "   Loop is stopping." >&2
  cleanup_hook
  exit 0
fi

# Extract the most recent assistant text block.
LAST_LINES=$(grep '"role":"assistant"' "$TRANSCRIPT_PATH" | tail -n 100)
if [[ -z "$LAST_LINES" ]]; then
  echo "⚠️  Structured workflow loop: Failed to extract assistant messages" >&2
  echo "   Loop is stopping." >&2
  cleanup_hook
  exit 0
fi

set +e
LAST_OUTPUT=$(echo "$LAST_LINES" | jq -rs '
  map(.message.content[]? | select(.type == "text") | .text) | last // ""
' 2>&1)
JQ_EXIT=$?
set -e

if [[ $JQ_EXIT -ne 0 ]]; then
  echo "⚠️  Structured workflow loop: Failed to parse assistant message JSON" >&2
  echo "   Error: $LAST_OUTPUT" >&2
  echo "   Loop is stopping." >&2
  cleanup_hook
  exit 0
fi

# Check for completion promise
if [[ "$COMPLETION_PROMISE" != "null" ]] && [[ -n "$COMPLETION_PROMISE" ]]; then
  PROMISE_TEXT=$(echo "$LAST_OUTPUT" | perl -0777 -pe 's/.*?<promise>(.*?)<\/promise>.*/$1/s; s/^\s+|\s+$//g; s/\s+/ /g' 2>/dev/null || echo "")

  if [[ -n "$PROMISE_TEXT" ]] && [[ "$PROMISE_TEXT" = "$COMPLETION_PROMISE" ]]; then
    echo "✅ Structured workflow loop: Detected <promise>$COMPLETION_PROMISE</promise>"
    cleanup_hook
    exit 0
  fi
fi

# Not complete - continue loop
NEXT_ITERATION=$((ITERATION + 1))

# Extract prompt (everything after the closing ---)
PROMPT_TEXT=$(awk '/^---$/{i++; next} i>=2' "$RALPH_STATE_FILE")

if [[ -z "$PROMPT_TEXT" ]]; then
  echo "⚠️  Structured workflow loop: State file corrupted or incomplete" >&2
  echo "   No prompt text found." >&2
  echo "   Loop is stopping." >&2
  cleanup_hook
  exit 0
fi

# Update iteration in frontmatter
TEMP_FILE="${RALPH_STATE_FILE}.tmp.$$"
sed "s/^iteration: .*/iteration: $NEXT_ITERATION/" "$RALPH_STATE_FILE" > "$TEMP_FILE"
mv "$TEMP_FILE" "$RALPH_STATE_FILE"

# Build system message
if [[ "$COMPLETION_PROMISE" != "null" ]] && [[ -n "$COMPLETION_PROMISE" ]]; then
  SYSTEM_MSG="🔄 Structured workflow iteration $NEXT_ITERATION | To stop: output <promise>$COMPLETION_PROMISE</promise> (ONLY when statement is TRUE - do not lie to exit!)"
else
  SYSTEM_MSG="🔄 Structured workflow iteration $NEXT_ITERATION | No completion promise set - loop runs infinitely"
fi

# Output JSON to block the stop and feed prompt back
jq -n \
  --arg prompt "$PROMPT_TEXT" \
  --arg msg "$SYSTEM_MSG" \
  '{
    "decision": "block",
    "reason": $prompt,
    "systemMessage": $msg
  }'

exit 0
