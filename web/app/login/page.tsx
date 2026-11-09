"use client";

import { type FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth-store";
import { DEV_LOGIN, loginWithCredentials } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function LoginPage() {
  const router = useRouter();
  const login = useAuthStore((s) => s.login);
  const [employeeId, setEmployeeId] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!employeeId.trim() || !password) {
      setError("请输入工号和密码");
      return;
    }
    setLoading(true);
    try {
      if (DEV_LOGIN) {
        login(
          { employeeId: employeeId.trim(), name: employeeId.trim() },
          "dev-token",
        );
      } else {
        const res = await loginWithCredentials(employeeId.trim(), password);
        login(
          { employeeId: res.user.employee_id, name: res.user.name },
          res.token,
        );
      }
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-background flex min-h-dvh items-center justify-center p-6">
      <div className="bg-card w-full max-w-sm rounded-xl border p-8 shadow-sm">
        <div className="mb-6 text-center">
          <h1 className="text-foreground text-xl font-semibold">OA 智能助手</h1>
          <p className="text-muted-foreground mt-1 text-sm">输入工号与密码登录</p>
        </div>
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <label htmlFor="employeeId" className="text-muted-foreground text-sm">
              工号
            </label>
            <Input
              id="employeeId"
              value={employeeId}
              onChange={(e) => setEmployeeId(e.target.value)}
              placeholder="请输入工号"
              autoComplete="username"
              autoFocus
            />
          </div>
          <div className="flex flex-col gap-2">
            <label htmlFor="password" className="text-muted-foreground text-sm">
              密码
            </label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="请输入密码"
              autoComplete="current-password"
            />
          </div>
          {error ? <p className="text-red-500 text-sm">{error}</p> : null}
          <Button type="submit" disabled={loading}>
            {loading ? "登录中..." : "登录"}
          </Button>
        </form>
        {DEV_LOGIN ? (
          <p className="text-muted-foreground mt-4 text-center text-xs">
            开发模式：任意工号 + 密码即可登录（未连后端）
          </p>
        ) : null}
      </div>
    </div>
  );
}
