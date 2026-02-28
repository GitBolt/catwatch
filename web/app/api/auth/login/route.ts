import { NextResponse } from "next/server";
import { loginWithDIDToken } from "@/lib/auth";

export async function POST(req: Request) {
  const { didToken } = await req.json();
  if (!didToken) {
    return NextResponse.json({ error: "didToken required" }, { status: 400 });
  }

  try {
    const user = await loginWithDIDToken(didToken);
    return NextResponse.json({ user: { id: user.id, email: user.email } });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Authentication failed";
    return NextResponse.json({ error: message }, { status: 401 });
  }
}
