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
  // Match the schema FileTelemetrySource.pull() expects. Token counts are
  // unavailable in the Gemini hook context, so raw/filtered tokens are 0 and
  // char counts carry the signal. timestamp is epoch seconds to match
  // Python's time.time().
  const entry = JSON.stringify({
    tool_name: toolName,
    raw_tokens: 0,
    raw_chars: chars,
    filtered_tokens: 0,
    filtered_chars: chars,
    timestamp: Date.now() / 1000,
    session_id: sessionId,
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
