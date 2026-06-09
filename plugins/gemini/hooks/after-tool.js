#!/usr/bin/env node
/**
 * archolith-audit AfterTool hook for Gemini CLI.
 * Gemini CLI passes hook context as JSON on stdin.
 * Returns JSON on stdout.
 */

const fs = require("fs");
const path = require("path");
const os = require("os");

async function main() {
  let payload;
  try {
    const chunks = [];
    for await (const chunk of process.stdin) chunks.push(chunk);
    payload = JSON.parse(Buffer.concat(chunks).toString());
  } catch {
    process.stdout.write(JSON.stringify({ continue: true }));
    return;
  }

  const toolName = payload.tool_name || payload.tool || "unknown";
  const result = payload.tool_result || payload.result || payload.output || "";
  const chars = JSON.stringify(result).length;
  // Gemini CLI session ID — check payload shape, fallback to hour-based key
  const sessionId =
    payload.session_id ||
    payload.sessionId ||
    `gemini-${Math.floor(Date.now() / 3600000)}`;

  const dir = path.join(os.homedir(), ".archolith", "sessions");
  fs.mkdirSync(dir, { recursive: true });
  const entry = JSON.stringify({
    tool: toolName,
    chars,
    ts: new Date().toISOString(),
  });

  try {
    fs.appendFileSync(path.join(dir, `${sessionId}.jsonl`), entry + "\n");
  } catch {
    // never block
  }

  process.stdout.write(JSON.stringify({ continue: true }));
}

main().catch(() => {
  process.stdout.write(JSON.stringify({ continue: true }));
});
