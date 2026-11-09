import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";

const API_BASE = process.env.FOUR_PLUS_API_URL;
const WORKBENCH_ROLES = new Set(["curator", "super_admin"]);

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ detail: "Authentication required." }, { status: 401 });

  const { data: profile, error } = await supabase
    .from("user_profiles")
    .select("role")
    .eq("id", user.id)
    .maybeSingle();
  if (error || !profile || !WORKBENCH_ROLES.has(profile.role)) {
    return NextResponse.json({ detail: "Curator access required." }, { status: 403 });
  }
  if (!API_BASE) {
    return NextResponse.json({ detail: "FOUR_PLUS_API_URL is not configured." }, { status: 503 });
  }

  const { path } = await context.params;
  const sessionResult = await supabase.auth.getSession();
  const accessToken = sessionResult.data.session?.access_token;
  if (!accessToken) return NextResponse.json({ detail: "Authentication required." }, { status: 401 });

  const target = new URL(`${API_BASE.replace(/\/$/, "")}/api/v1/${path.map(encodeURIComponent).join("/")}`);
  target.search = request.nextUrl.search;
  const headers = new Headers({ Authorization: `Bearer ${accessToken}` });
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const body = request.method === "GET" || request.method === "HEAD"
    ? undefined
    : await request.arrayBuffer();

  try {
    const response = await fetch(target, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
    });
    const responseHeaders = new Headers();
    const responseType = response.headers.get("content-type");
    if (responseType) responseHeaders.set("content-type", responseType);
    return new Response(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json({ detail: "The story API could not be reached." }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
