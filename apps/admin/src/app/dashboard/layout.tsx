import Link from "next/link";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { SignOutButton } from "@/components/sign-out-button";

export default async function DashboardLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile, error } = await supabase
    .from("user_profiles")
    .select("role,full_name")
    .eq("id", user.id)
    .maybeSingle();
  if (error || !profile || !["curator", "super_admin"].includes(profile.role)) {
    redirect("/login?error=access");
  }

  return (
    <div className="min-h-screen md:flex">
      <aside className="bg-ink px-5 py-6 text-white md:sticky md:top-0 md:h-screen md:w-64 md:shrink-0">
        <Link href="/dashboard" className="block text-lg font-semibold leading-tight">
          Four Plus
          <span className="block text-sm font-normal text-sage">Curator Workbench</span>
        </Link>
        <nav className="mt-10 flex gap-2 overflow-x-auto md:flex-col">
          <NavLink href="/dashboard">Overview</NavLink>
          <NavLink href="/dashboard/jobs">Ingestion & jobs</NavLink>
          <NavLink href="/dashboard/review">Story review</NavLink>
        </nav>
        <div className="mt-10 flex items-center justify-between border-t border-white/15 pt-5 text-sm md:mt-auto">
          <div>
            <p className="font-medium">{profile.full_name}</p>
            <p className="text-xs capitalize text-sage">{profile.role.replace("_", " ")}</p>
          </div>
          <SignOutButton />
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-5 md:p-10">{children}</main>
    </div>
  );
}

function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="whitespace-nowrap rounded-xl px-4 py-3 text-sm text-sage transition hover:bg-white/10 hover:text-white"
    >
      {children}
    </Link>
  );
}
