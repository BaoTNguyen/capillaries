#!/usr/bin/env node
// Capillaries wrapper for arteries UserPromptSubmit.
// Reads Claude/Codex-style JSON on stdin and returns the expected hook JSON.

const { execFileSync } = require('child_process');
const path = require('path');

const ARTERIES_ROOT = process.env.ARTERIES_ROOT;
const CAPILLARIES_ROOT = process.env.CAPILLARIES_ROOT || process.env.CLAUDE_PROJECT_DIR || path.resolve(__dirname, '..');
const isCopilot = Boolean(process.env.COPILOT_PLUGIN_DATA);
const isCodex = !isCopilot && Boolean(process.env.PLUGIN_DATA);

if (!ARTERIES_ROOT) {
  process.stdout.write(isCopilot || isCodex ? '{}' : '');
  process.exit(0);
}

function writeOutput(output) {
  if (isCopilot) {
    process.stdout.write(JSON.stringify(output ? { additionalContext: output } : {}));
    return;
  }
  if (isCodex) {
    process.stdout.write(JSON.stringify({
      systemMessage: 'ARTERIES:RETRIEVAL',
      hookSpecificOutput: {
        hookEventName: 'UserPromptSubmit',
        additionalContext: output,
      },
    }));
    return;
  }
  process.stdout.write(output || '');
}

let input = '';
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', () => {
  try {
    const data = JSON.parse(input.replace(/^﻿/, ''));
    const prompt = (data.prompt || '').trim();
    if (!prompt) {
      writeOutput('');
      return;
    }

    const env = { ...process.env };
    const paths = [`${ARTERIES_ROOT}/src`, `${CAPILLARIES_ROOT}/src`];
    env.PYTHONPATH = env.PYTHONPATH ? `${paths.join(':')}:${env.PYTHONPATH}` : paths.join(':');
    env.ARTERIES_PROJECT = env.ARTERIES_PROJECT || 'capillaries';
    env.ARTERIES_AGENT_ID = env.ARTERIES_AGENT_ID || 'capillaries-hook';

    const result = execFileSync(
      'python3',
      ['-m', 'arteries.eval', prompt],
      { timeout: 10000, encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'], env }
    ).trim();

    if (result) {
      writeOutput('ARTERIES RETRIEVED PROMPT - use this to guide your response:\n\n' + result);
    } else {
      writeOutput('');
    }
  } catch (_e) {
    writeOutput('');
  }
});
