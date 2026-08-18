#!/usr/bin/env node
const fs = require('fs');
const { execFileSync } = require('child_process');
const path = require('path');

const isCopilot = Boolean(process.env.COPILOT_PLUGIN_DATA);
const isCodex = !isCopilot && Boolean(process.env.PLUGIN_DATA);

function writeOutput(output) {
  if (isCopilot) {
    process.stdout.write(JSON.stringify(output ? { additionalContext: output } : {}));
    return;
  }
  if (isCodex) {
    process.stdout.write(JSON.stringify({
      systemMessage: 'ARTERIES:RETRIEVAL',
      hookSpecificOutput: { hookEventName: 'UserPromptSubmit', additionalContext: output },
    }));
    return;
  }
  process.stdout.write(output || '');
}

function loadConfig() {
  try {
    const configPath = path.join(__dirname, '..', 'config.json');
    return JSON.parse(fs.readFileSync(configPath, 'utf8'));
  } catch (e) { return {}; }
}

let input = '';
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', () => {
  try {
    const data = JSON.parse(input.replace(/^\xef\xbb\xbf/, ''));
    const prompt = (data.prompt || '').trim();
    if (!prompt) { writeOutput(''); return; }

    const config = loadConfig();
    const arteriesRoot = config.arteries_root || process.env.ARTERIES_ROOT || process.cwd();
    const capRoot = config.capillaries_root || process.env.CAPILLARIES_ROOT;

    const env = { ...process.env };
    env.ARTERIES_CLI = env.ARTERIES_CLI || 'codex';
    env.ARTERIES_EVENT = env.ARTERIES_EVENT || 'UserPromptSubmit';
    // identity, not just PYTHONPATH: without these the child falls back to cwd,
    // and a hook invoked from anywhere but the repo root writes its run state to
    // <cwd>/.arteries — which is a crash at /, so the turn is lost silently
    if (config.project) env.ARTERIES_PROJECT = env.ARTERIES_PROJECT || config.project;
    if (config.agent_id) env.ARTERIES_AGENT_ID = env.ARTERIES_AGENT_ID || config.agent_id;
    if (config.project_root) env.ARTERIES_REPO = env.ARTERIES_REPO || config.project_root;
    // same per-repo .arteries/env the shell hooks read, so codex and claude in
    // one repo cannot end up on different memory policies
    try {{
      for (const line of fs.readFileSync(path.join(__dirname, '..', 'env'), 'utf8').split('\n')) {{
        const m = line.match(/^([A-Z][A-Z0-9_]*)=(.*)$/);
        if (m && !env[m[1]]) env[m[1]] = m[2];
      }}
    }} catch (e) {{}}
    const srcPath = path.join(arteriesRoot, 'src');
    let pypath = srcPath;
    if (capRoot) {
      const capSrc = path.join(capRoot, 'src');
      if (fs.existsSync(capSrc)) pypath = `${srcPath}:${capSrc}`;
    }
    env.PYTHONPATH = env.PYTHONPATH ? `${pypath}:${env.PYTHONPATH}` : pypath;

    const transcriptPath = data.transcript_path || data.transcriptPath || data.transcript_file || data.transcriptFile || data.session_file || data.sessionFile;
    if (transcriptPath) env.ARTERIES_TRANSCRIPT = transcriptPath;

    const result = execFileSync('python3', ['-m', 'arteries.eval', prompt], {
      timeout: 5000, encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'], env,
    }).trim();

    if (result) {
      writeOutput('ARTERIES RETRIEVED PROMPT — use this to guide your response:\n\n' + result);
    } else {
      writeOutput('');
    }
  } catch (e) { writeOutput(''); }
});
