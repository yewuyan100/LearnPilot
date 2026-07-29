export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(message: string, status = 0, code = "network_error") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: options.body instanceof FormData
        ? options.headers
        : { "Content-Type": "application/json", ...options.headers },
    });
  } catch {
    throw new ApiError("无法连接后端，请确认 FastAPI 已在 8000 端口启动");
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message = body?.error?.message ?? `请求失败（HTTP ${response.status}）`;
    throw new ApiError(message, response.status, body?.error?.code ?? "http_error");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function jsonBody(value: unknown): RequestInit {
  return { body: JSON.stringify(value) };
}

export async function streamPost(
  path: string,
  body: unknown,
  signal: AbortSignal,
  onEvent: (event: string, data: unknown) => void,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new ApiError("无法连接资料问答服务，请确认后端已启动");
  }
  if (!response.ok) {
    const value = await response.json().catch(() => null);
    throw new ApiError(
      value?.error?.message ?? `请求失败（HTTP ${response.status}）`,
      response.status,
      value?.error?.code,
    );
  }
  if (!response.body) throw new ApiError("浏览器未收到流式响应");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      let event = "message";
      const dataLines: string[] = [];
      for (const line of frame.split(/\r?\n/)) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (dataLines.length) {
        onEvent(event, JSON.parse(dataLines.join("\n")));
      }
    }
    if (done) break;
  }
}
