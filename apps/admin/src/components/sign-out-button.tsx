"use client";

import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

export function SignOutButton() {
  const router = useRouter();

  async function signOut() {
    const { error } = await createClient().auth.signOut();
    if (error) {
      window.alert(error.message);
      return;
    }
    router.replace("/login");
    router.refresh();
  }

  return (
    <button
      className="rounded-lg border border-white/20 px-3 py-2 text-xs text-sage hover:bg-white/10"
      onClick={signOut}
      type="button"
    >
      Sign out
    </button>
  );
}
