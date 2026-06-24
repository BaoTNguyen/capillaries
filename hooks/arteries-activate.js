#!/usr/bin/env node
// prompt-system wrapper for arteries SessionStart.

const isCopilot = Boolean(process.env.COPILOT_PLUGIN_DATA);
const isCodex = !isCopilot && Boolean(process.env.PLUGIN_DATA);

const context = `ARTERIES MEMORY SYSTEM ACTIVE.

This prompt-system workspace is connected to arteries.
Arteries observes turns, builds ephemeral/persistent/evergreen memory, and may surface retrieved prompts as visible context.

When arteries retrieves a prompt, use it as context for the response. You do not need to invoke arteries manually.`;

function writeOutput(output) {
  if (isCopilot) {
    process.stdout.write(JSON.stringify(output ? { additionalContext: output } : {}));
    return;
  }
  if (isCodex) {
    process.stdout.write(JSON.stringify({
      systemMessage: 'ARTERIES:ACTIVE',
      hookSpecificOutput: {
        hookEventName: 'SessionStart',
        additionalContext: output,
      },
    }));
    return;
  }
  process.stdout.write(output);
}

try {
  writeOutput(context);
} catch (_e) {
  writeOutput('');
}
