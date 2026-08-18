#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

const isCopilot = Boolean(process.env.COPILOT_PLUGIN_DATA);
const isCodex = !isCopilot && Boolean(process.env.PLUGIN_DATA);

const context = `ARTERIES MEMORY SYSTEM ACTIVE.

This repo is connected to arteries project \`capillaries\`.
Arteries observes turns, builds ephemeral/persistent/evergreen memory, and may surface retrieved prompts as visible context.`;

function writeOutput(output) {
  if (isCopilot) {
    process.stdout.write(JSON.stringify(output ? { additionalContext: output } : {}));
    return;
  }
  if (isCodex) {
    process.stdout.write(JSON.stringify({
      systemMessage: 'ARTERIES:ACTIVE',
      hookSpecificOutput: { hookEventName: 'SessionStart', additionalContext: output },
    }));
    return;
  }
  process.stdout.write(output);
}

try { writeOutput(context); } catch (e) {}
