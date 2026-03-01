import { NextRequest, NextResponse } from "next/server";
import OpenAI from "openai";
import { ALL_ZONES, ZONE_LABELS, type ZoneId } from "@/lib/constants";

const ZONE_LIST = ALL_ZONES.map((z) => `${z} (${ZONE_LABELS[z]})`).join(", ");

const SYSTEM_PROMPT = `You are an expert heavy-equipment damage analyst for the CAT 797F mining truck.
Given a scenario, determine which zones of the truck would be damaged, the severity, and a short description.

Available zones: ${ZONE_LIST}

Severity levels:
- RED: Critical structural/safety damage requiring immediate attention
- YELLOW: Moderate damage that affects performance or longevity
- GREEN: Minor cosmetic or surface-level damage

Respond ONLY with a JSON array. Each element: {"zone": "<zone_id>", "severity": "RED"|"YELLOW"|"GREEN", "description": "<short damage description>"}
Do not include zones that would be unaffected. Be realistic and specific to the CAT 797F mining truck.`;

export async function POST(req: NextRequest) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      { error: "OPENAI_API_KEY not configured" },
      { status: 500 },
    );
  }

  const body = await req.json();
  const scenario = body.scenario as string;
  if (!scenario || scenario.trim().length === 0) {
    return NextResponse.json({ error: "scenario is required" }, { status: 400 });
  }

  try {
    const openai = new OpenAI({ apiKey });
    const completion = await openai.chat.completions.create({
      model: "gpt-4o-mini",
      temperature: 0.7,
      max_tokens: 1024,
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        { role: "user", content: scenario },
      ],
    });

    const raw = completion.choices[0]?.message?.content ?? "[]";
    const jsonMatch = raw.match(/\[[\s\S]*\]/);
    if (!jsonMatch) {
      return NextResponse.json({ damages: [] });
    }

    const parsed = JSON.parse(jsonMatch[0]) as {
      zone: string;
      severity: string;
      description: string;
    }[];

    const validZones = new Set<string>(ALL_ZONES);
    const validSev = new Set(["RED", "YELLOW", "GREEN"]);

    const damages = parsed
      .filter(
        (d) =>
          validZones.has(d.zone) &&
          validSev.has(d.severity?.toUpperCase()) &&
          typeof d.description === "string",
      )
      .map((d) => ({
        zone: d.zone as ZoneId,
        severity: d.severity.toUpperCase(),
        description: d.description,
      }));

    return NextResponse.json({ damages });
  } catch (e: any) {
    console.error("Scenario simulation error:", e);
    return NextResponse.json(
      { error: e.message ?? "Failed to generate scenario" },
      { status: 500 },
    );
  }
}
