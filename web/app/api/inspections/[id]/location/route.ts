import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { prisma } from "@/lib/db";

/** PATCH /api/inspections/[id]/location — set geo-resolved location on a session */
export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const session = await getSession();
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const { location } = await req.json();
  if (!location || typeof location !== "string") {
    return NextResponse.json({ error: "location required" }, { status: 400 });
  }

  await prisma.session.updateMany({
    where: { id, userId: session.userId, location: null },
    data: { location: location.trim() },
  });

  return NextResponse.json({ ok: true });
}
