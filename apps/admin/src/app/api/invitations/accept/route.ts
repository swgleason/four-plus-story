import { createClient as createSupabaseClient } from "@supabase/supabase-js";
import { NextResponse, type NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  let input: { token?: string; email?: string; password?: string; fullName?: string };
  try {
    input = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }

  const token = input.token?.trim();
  const email = input.email?.trim().toLowerCase();
  const password = input.password;
  const fullName = input.fullName?.trim();
  if (!token || !email || !password || !fullName || password.length < 10) {
    return NextResponse.json(
      { error: "Provide all fields and a password of at least 10 characters." },
      { status: 422 },
    );
  }

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !serviceKey) {
    return NextResponse.json({ error: "Invitation acceptance is not configured." }, { status: 503 });
  }

  const supabase = createSupabaseClient(url, serviceKey, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
  const { data: invite, error: inviteError } = await supabase
    .from("admin_invitations")
    .select("id,email,role,expires_at,accepted_at")
    .eq("invite_token", token)
    .maybeSingle();
  if (inviteError) {
    return NextResponse.json({ error: "Could not verify invitation." }, { status: 500 });
  }
  if (
    !invite ||
    invite.email.toLowerCase() !== email ||
    invite.accepted_at ||
    new Date(invite.expires_at).getTime() <= Date.now() ||
    !["curator", "super_admin"].includes(invite.role)
  ) {
    return NextResponse.json({ error: "Invitation is invalid, expired, or already used." }, { status: 400 });
  }

  const { data: created, error: createError } = await supabase.auth.admin.createUser({
    email,
    password,
    email_confirm: true,
    user_metadata: { full_name: fullName },
  });
  if (createError || !created.user) {
    return NextResponse.json(
      { error: createError?.message || "Could not create invited account." },
      { status: 400 },
    );
  }

  const { error: profileError } = await supabase.from("user_profiles").insert({
    id: created.user.id,
    email,
    full_name: fullName,
    role: invite.role,
  });
  if (profileError) {
    await supabase.auth.admin.deleteUser(created.user.id);
    return NextResponse.json({ error: "Could not create the invited curator profile." }, { status: 500 });
  }

  const { data: accepted, error: acceptError } = await supabase
    .from("admin_invitations")
    .update({ accepted_at: new Date().toISOString() })
    .eq("id", invite.id)
    .is("accepted_at", null)
    .select("id")
    .maybeSingle();
  if (acceptError || !accepted) {
    await supabase.from("user_profiles").delete().eq("id", created.user.id);
    await supabase.auth.admin.deleteUser(created.user.id);
    return NextResponse.json({ error: "Invitation was already accepted or could not be finalized." }, { status: 409 });
  }

  return NextResponse.json({ accepted: true }, { status: 201 });
}
