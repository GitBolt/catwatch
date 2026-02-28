import { NextRequest, NextResponse } from "next/server";
import {
  addMemory,
  searchMemories,
  getUnitProfile,
} from "@/lib/supermemory";

/**
 * POST /api/memory — Store a finding or report in Supermemory
 *
 * Body: { action: "store", unitSerial, content, metadata?, customId? }
 *       { action: "store_report", unitSerial, reportJson }
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { action, unitSerial } = body;

    if (!unitSerial) {
      return NextResponse.json({ error: "unitSerial required" }, { status: 400 });
    }

    if (action === "store") {
      const doc = await addMemory({
        content: body.content,
        containerTag: unitSerial,
        customId: body.customId,
        metadata: body.metadata,
      });
      return NextResponse.json(doc);
    }

    if (action === "store_report") {
      const reportStr =
        typeof body.reportJson === "string"
          ? body.reportJson
          : JSON.stringify(body.reportJson);
      const doc = await addMemory({
        content: `Inspection report for ${unitSerial}:\n${reportStr}`,
        containerTag: unitSerial,
        customId: body.customId ?? `report-${unitSerial}-${Date.now()}`,
        metadata: { type: "report", unitSerial },
      });
      return NextResponse.json(doc);
    }

    return NextResponse.json({ error: "Unknown action" }, { status: 400 });
  } catch (e) {
    console.error("[memory/POST]", e);
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Unknown error" },
      { status: 500 },
    );
  }
}

/**
 * GET /api/memory — Search or get unit profile from Supermemory
 *
 * ?action=profile&unitSerial=X&query=optional
 * ?action=search&query=X&unitSerial=optional&limit=10
 */
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = req.nextUrl;
    const action = searchParams.get("action") ?? "profile";
    const unitSerial = searchParams.get("unitSerial");
    const query = searchParams.get("query") ?? undefined;
    const limit = parseInt(searchParams.get("limit") ?? "10", 10);

    if (action === "profile") {
      if (!unitSerial) {
        return NextResponse.json({ error: "unitSerial required" }, { status: 400 });
      }
      const profile = await getUnitProfile({
        containerTag: unitSerial,
        query,
      });
      return NextResponse.json(profile);
    }

    if (action === "search") {
      if (!query) {
        return NextResponse.json({ error: "query required" }, { status: 400 });
      }
      const results = await searchMemories({
        query,
        containerTag: unitSerial ?? undefined,
        limit,
      });
      return NextResponse.json(results);
    }

    return NextResponse.json({ error: "Unknown action" }, { status: 400 });
  } catch (e) {
    console.error("[memory/GET]", e);
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Unknown error" },
      { status: 500 },
    );
  }
}
