import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { prisma } from "@/lib/db";

/** DELETE /api/inspections — batch delete inspections by IDs */
export async function DELETE(req: NextRequest) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { ids } = await req.json();
  if (!Array.isArray(ids) || ids.length === 0) {
    return NextResponse.json({ error: "ids[] required" }, { status: 400 });
  }

  const { count } = await prisma.session.deleteMany({
    where: { id: { in: ids }, userId: session.userId },
  });

  return NextResponse.json({ deleted: count });
}
