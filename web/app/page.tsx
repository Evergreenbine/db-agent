"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth-store";
import { loginById } from "@/lib/api";
import { Assistant } from "./assistant";

export default function Home() {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const login = useAuthStore((s) => s.login);
  const logout = useAuthStore((s) => s.logout);
  const [mounted, setMounted] = useState(false);
  const [autoLogging, setAutoLogging] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!mounted) return;

    const params = new URLSearchParams(window.location.search);
    const empId = params.get("employee_id");

    // URL 带了 employee_id 且和当前存储的不一致 → 清旧 token 重新登录
    if (empId && user?.employeeId && empId !== user.employeeId) {
      logout();
    }

    // 已有 token 且和 URL 工号一致 → 直接进
    if (token && (!empId || empId === user?.employeeId)) return;

    // 有 URL 工号 → 自动登录
    if (empId && !autoLogging) {
      setAutoLogging(true);
      loginById(empId)
        .then((res) => {
          login(
            { employeeId: res.user.employee_id, name: res.user.name },
            res.token,
          );
        })
        .catch(() => {
          router.replace("/login");
        });
      return;
    }

    // 没有 token、没有工号参数、且不在自动登录中 → 跳登录页
    if (!token && !autoLogging) {
      router.replace("/login");
    }
  }, [mounted, token, user, autoLogging, login, logout, router]);

  if (!mounted || !token) return null;
  return <Assistant />;
}
