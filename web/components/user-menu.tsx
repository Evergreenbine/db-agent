"use client";

import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth-store";
import { Button } from "@/components/ui/button";

export function UserMenu() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  if (!user) return null;
  return (
    <div className="ml-auto flex items-center gap-2">
      <span className="text-sm text-muted-foreground">
        {user.name || user.employeeId}
      </span>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => {
          logout();
          router.replace("/login");
        }}
      >
        <LogOut className="size-4" />
        登出
      </Button>
    </div>
  );
}
