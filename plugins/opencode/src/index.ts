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
  const entry = JSON.stringify({
    tool: toolName,
    chars,
    ts: new Date().toISOString(),
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
