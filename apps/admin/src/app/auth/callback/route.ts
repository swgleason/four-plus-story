import { createServerClient } from "@supabase/ssr";
import type { EmailOtpType } from "@supabase/supabase-js";
import { NextResponse, type NextRequest } from "next/server";

const WORKBENCH_ROLES = new Set(["curator", "super_admin"]);
const OTP_TYPES = new Set<EmailOtpType>(["email", "magiclink", "signup"]);

function safeDestination(value: string | null, origin: string) {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/dashboard";
  const resolved = new URL(value, origin);
  return resolved.origin === origin ? `${resolved.pathname}${resolved.search}${resolved.hash}` : "/dashboard";
}

function redirectResponse(
  request: NextRequest,
  path: string,
  previousResponse?: NextResponse,
) {
  const response = NextResponse.redirect(new URL(path, request.url));
  previousResponse?.cookies.getAll().forEach(({ name, value, ...options }) => {
    response.cookies.set(name, value, options);
  });
  return response;
}

export async function GET(request: NextRequest) {
  const requestUrl = request.nextUrl;
  const destination = safeDestination(requestUrl.searchParams.get("next"), requestUrl.origin);
  let redirectPath = destination;
  let response = redirectResponse(request, redirectPath);
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseAnonKey) {
    redirectPath = "/login?error=auth_config";
    return redirectResponse(request, redirectPath);
  }

  const supabase = createServerClient(supabaseUrl, supabaseAnonKey, {
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
        response = redirectResponse(request, redirectPath, response);
        cookiesToSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options),
        );
      },
    },
  });

  const code = requestUrl.searchParams.get("code");
  const tokenHash = requestUrl.searchParams.get("token_hash");
  let authError: Error | null = null;
  let userId: string | undefined;

  if (code) {
    const { data, error } = await supabase.auth.exchangeCodeForSession(code);
    authError = error;
    userId = data.user?.id;
  } else if (tokenHash) {
    const rawType = requestUrl.searchParams.get("type");
    const type = rawType && OTP_TYPES.has(rawType as EmailOtpType)
      ? rawType as EmailOtpType
      : null;
    if (type) {
      const { data, error } = await supabase.auth.verifyOtp({ token_hash: tokenHash, type });
      authError = error;
      userId = data.user?.id;
    } else {
      authError = new Error("The email link has an unsupported verification type.");
    }
  } else {
    authError = new Error("The authentication link is missing its code or token.");
  }

  if (authError || !userId) {
    redirectPath = "/login?error=callback";
    response = redirectResponse(request, redirectPath, response);
    return response;
  }

  const { data: profile, error: profileError } = await supabase
    .from("user_profiles")
    .select("role")
    .eq("id", userId)
    .maybeSingle();
  if (profileError || !profile || !WORKBENCH_ROLES.has(profile.role)) {
    redirectPath = "/login?error=access";
    response = redirectResponse(request, redirectPath, response);
  }
  return response;
}
