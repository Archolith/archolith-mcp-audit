import * as fs from "fs";
import * as path from "path";
import * as os from "os";

interface PluginContext {
  sessionId: string;
  config: Record<string, unknown>;
}

interface ToolExecuteAfterEvent {
  tool: string;
  result: unknown;
  durationMs: number;
}

function getSessionPath(sessionId: string): string {
  const dir = path.join(os.homedir(), ".archolith", "sessions");
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, `${sessionId}.jsonl`);
}

function writeObservation(sessionId: string, toolName: string, chars: number): void {
  // Match the schema FileTelemetrySource.pull() expects. Token counts are
  // unavailable in the OpenCode plugin context, so raw/filtered tokens are 0
  // and char counts carry the signal. timestamp is epoch seconds to match
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
    fs.appendFileSync(getSessionPath(sessionId), entry + "\n", "utf-8");
  } catch {
    // never block the agent
  }
}

export default function archolith_audit_plugin(context: PluginContext) {
  const { sessionId } = context;

  return {
    "tool.execute.after": (event: ToolExecuteAfterEvent) => {
      const chars = JSON.stringify(event.result ?? "").length;
      writeObservation(sessionId, event.tool, chars);
    },
  };
}
