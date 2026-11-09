export interface LoginResponse {
  token: string;
  user: { employee_id: string; name: string };
}

// 开发模式：=1 时前端直接放行，不连后端（后端就绪后置空或删掉）
export const DEV_LOGIN = process.env.NEXT_PUBLIC_DEV_LOGIN === "1";

export async function loginWithCredentials(
  employeeId: string,
  password: string,
): Promise<LoginResponse> {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ employee_id: employeeId, password }),
  });
  if (!res.ok) {
    let msg = "登录失败 (" + res.status + ")";
    try {
      const data = await res.json();
      msg = data?.detail || data?.message || msg;
    } catch {
      // 响应不是 JSON，用默认消息
    }
    throw new Error(msg);
  }
  return (await res.json()) as LoginResponse;
}

export async function loginById(employeeId: string): Promise<LoginResponse> {
  const res = await fetch("/api/auth/by-id", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ employee_id: employeeId }),
  });
  if (!res.ok) {
    let msg = "登录失败 (" + res.status + ")";
    try {
      const data = await res.json();
      msg = data?.detail || data?.message || msg;
    } catch {}
    throw new Error(msg);
  }
  return (await res.json()) as LoginResponse;
}
