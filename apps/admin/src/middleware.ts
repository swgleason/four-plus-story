import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request });
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll(
          cookiesToSet: Array<{
            name: string;
            value: string;
            options: Parameters<typeof response.cookies.set>[2];
          }>,
        ) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user && request.nextUrl.pathname.startsWith("/dashboard")) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = "/login";
    loginUrl.searchParams.set("next", request.nextUrl.pathname);
    return redirectWithCookies(response, loginUrl);
  }
  if (user && request.nextUrl.pathname === "/login") {
    const { data: profile } = await supabase
      .from("user_profiles")
      .select("role")
      .eq("id", user.id)
      .maybeSingle();
    if (profile && ["curator", "super_admin"].includes(profile.role)) {
      const dashboardUrl = request.nextUrl.clone();
      dashboardUrl.pathname = "/dashboard";
      dashboardUrl.search = "";
      return redirectWithCookies(response, dashboardUrl);
    }
  }
  return response;
}

function redirectWithCookies(response: NextResponse, destination: URL) {
  const redirectResponse = NextResponse.redirect(destination);
  response.cookies.getAll().forEach(({ name, value, ...options }) => {
    redirectResponse.cookies.set(name, value, options);
  });
  return redirectResponse;
}

export const config = {
  matcher: ["/dashboard/:path*", "/login"],
};
