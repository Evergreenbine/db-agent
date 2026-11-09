import {
  createUIMessageStreamResponse,
  type UIMessage,
  type UIMessageChunk,
} from "ai";
import { decodeMentionsSuffix } from "@/lib/mention-encode";

export async function POST(req: Request) {
  const { messages }: { messages: UIMessage[] } = await req.json();

  // 提取最后一条用户消息的文本
  const lastUser = [...messages].reverse().find((m) => m.role === "user");
  const prompt =
    lastUser?.parts
      ?.filter((p): p is { type: "text"; text: string } => p.type === "text")
      .map((p) => p.text)
      .join("") ?? "你好";
  const { text: cleanPrompt } = decodeMentionsSuffix(prompt);

  // 用第一条消息的 ID 作为会话 ID（同一对话内保持一致）
  const sessionId = messages[0]?.id ?? "default";

  // 转发认证 header 给后端
  const authHeader = req.headers.get("authorization") ?? "";
  const xEmployeeId = req.headers.get("x-employee-id") ?? "";

  const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

  const forwardHeaders: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (authHeader) forwardHeaders["Authorization"] = authHeader;
  if (xEmployeeId) forwardHeaders["X-Employee-Id"] = xEmployeeId;

  // 转发 E-Cology 单据上下文
  const xRequestId = req.headers.get("x-request-id") ?? "";
  const xSqr = req.headers.get("x-sqr") ?? "";
  if (xRequestId) forwardHeaders["X-Request-Id"] = xRequestId;
  if (xSqr) forwardHeaders["X-SQR"] = xSqr;

  const xMentions = req.headers.get("x-mentions") ?? "";
  if (xMentions) forwardHeaders["X-Mentions"] = xMentions;
  // 调用后端 SSE 流式接口（真流式 + 思考过程 + 工具事件 + 用户身份）
  const backendRes = await fetch(`${backendUrl}/api/agent/chat`, {
    method: "POST",
    headers: forwardHeaders,
    body: JSON.stringify({ prompt: prompt, session_id: sessionId }),
  });

  if (!backendRes.ok || !backendRes.body) {
    return new Response("Backend unavailable", { status: 502 });
  }
  const backendBody = backendRes.body;

  const messageId = crypto.randomUUID();
  // 后端 tool_call_id -> 前端 UUID 映射（兜底空 ID）
  const toolCallIdMap = new Map<string, string>();

  const stream = new ReadableStream<UIMessageChunk>({
    async start(controller) {
      controller.enqueue({ type: "start", messageId });

      // 思考(reasoning)与正文(text)按需开关，保证「先思考后正文」的顺序
      let openPart: "reasoning" | "text" | null = null;
      let reasoningId = crypto.randomUUID();
      const textId = crypto.randomUUID();

      const closePart = () => {
        if (openPart === "reasoning") {
          controller.enqueue({ type: "reasoning-end", id: reasoningId });
        } else if (openPart === "text") {
          controller.enqueue({ type: "text-end", id: textId });
        }
        openPart = null;
      };
      const openReasoning = () => {
        if (openPart !== "reasoning") {
          closePart();
          reasoningId = crypto.randomUUID();
          controller.enqueue({ type: "reasoning-start", id: reasoningId });
          openPart = "reasoning";
        }
      };
      const openText = () => {
        if (openPart !== "text") {
          closePart();
          controller.enqueue({ type: "text-start", id: textId });
          openPart = "text";
        }
      };

      const reader = backendBody.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data: ")) continue;
            const payload = trimmed.slice(6);
            if (payload === "[DONE]") continue;

            try {
              const parsed = JSON.parse(payload);
              if (parsed.type === "reasoning" && parsed.content) {
                openReasoning();
                controller.enqueue({
                  type: "reasoning-delta",
                  id: reasoningId,
                  delta: parsed.content,
                });
              } else if (parsed.type === "text" && parsed.content) {
                openText();
                controller.enqueue({
                  type: "text-delta",
                  id: textId,
                  delta: parsed.content,
                });
              } else if (parsed.type === "tool_call") {
                closePart();
                const toolCallId = crypto.randomUUID();
                toolCallIdMap.set(parsed.tool_call_id ?? "", toolCallId);
                let input = parsed.args;
                if (typeof input === "string") {
                  try { input = JSON.parse(input); } catch { /* 保留原始字符串 */ }
                }
                controller.enqueue({
                  type: "tool-input-available",
                  toolCallId,
                  toolName: parsed.name,
                  input,
                });
              } else if (parsed.type === "tool_result") {
                const backendId = parsed.tool_call_id ?? "";
                const toolCallId = toolCallIdMap.get(backendId) ?? crypto.randomUUID();
                let _output = parsed.output;
                if (_output && typeof _output === "object") {
                  _output = { ..._output, _backend_call_id: backendId };
                } else if (typeof _output === "string") {
                  try {
                    const _o = JSON.parse(_output);
                    if (_o && typeof _o === "object") { _o._backend_call_id = backendId; _output = JSON.stringify(_o); }
                  } catch { /* keep original */ }
                }
                controller.enqueue({
                  type: "tool-output-available",
                  toolCallId,
                  output: _output,
                });
              } else if (parsed.type === "error") {
                controller.enqueue({
                  type: "error",
                  errorText: String(parsed.content),
                });
              }
            } catch {
              // 忽略解析失败的行
            }
          }
        }
      } catch {
        // 网络中断等异常，静默处理
      }

      closePart();
      controller.enqueue({ type: "finish", finishReason: "stop" });
      controller.close();
    },
  });

  return createUIMessageStreamResponse({ stream });
}
