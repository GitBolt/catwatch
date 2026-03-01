import { NextRequest, NextResponse } from "next/server";
import OpenAI from "openai";
import { ZONE_LABELS, type ZoneId } from "@/lib/constants";

export async function POST(req: NextRequest) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      { error: "OPENAI_API_KEY not configured" },
      { status: 500 },
    );
  }

  const body = await req.json();
  const {
    sessionId,
    createdAt,
    endedAt,
    unitSerial,
    unitModel,
    fleetTag,
    location,
    coveragePct,
    findings,
  } = body;

  if (!findings || !Array.isArray(findings) || findings.length === 0) {
    return NextResponse.json(
      { error: "Inspection must have findings to file a claim" },
      { status: 400 },
    );
  }

  const redCount = findings.filter(
    (f: any) => f.rating?.toUpperCase() === "RED",
  ).length;
  const yellowCount = findings.filter(
    (f: any) => f.rating?.toUpperCase() === "YELLOW",
  ).length;
  const greenCount = findings.filter(
    (f: any) => f.rating?.toUpperCase() === "GREEN",
  ).length;

  const findingsSummary = findings
    .map(
      (f: any, i: number) =>
        `${i + 1}. [${f.rating}] ${ZONE_LABELS[f.zone as ZoneId] ?? f.zone}: ${f.description}`,
    )
    .join("\n");

  const inspectionDate = new Date(createdAt).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const systemPrompt = `You are a heavy equipment insurance claims specialist. Generate a professional, ready-to-file insurance claim document for damaged mining equipment based on drone inspection data.

The claim should be thorough, factual, and formatted for submission to an insurance company. Use industry-standard language. Be specific about damages found during the AI-powered drone inspection.`;

  const userPrompt = `Generate an insurance claim document for the following drone inspection of a CAT 797F mining truck.

INSPECTION DATA:
- Inspection ID: ${sessionId}
- Date: ${inspectionDate}
${endedAt ? `- Completed: ${new Date(endedAt).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}` : ""}
- Equipment: CAT 797F Mining Truck
${unitSerial ? `- Unit Serial: ${unitSerial}` : ""}
${unitModel ? `- Model: ${unitModel}` : ""}
${fleetTag ? `- Fleet Tag: ${fleetTag}` : ""}
${location ? `- Location: ${location}` : ""}
- Inspection Coverage: ${coveragePct}%
- Total Findings: ${findings.length} (${redCount} Critical, ${yellowCount} Warning, ${greenCount} Minor)

FINDINGS:
${findingsSummary}

Generate the claim as a JSON object with these exact fields:
{
  "claimTitle": "Brief claim title",
  "claimDate": "Today's date formatted",
  "policySection": "Recommended policy section (e.g. Comprehensive Equipment Coverage, Collision, etc.)",
  "incidentSummary": "2-3 paragraph professional summary of the incident and damages discovered",
  "equipmentDetails": {
    "make": "Caterpillar",
    "model": "797F",
    "type": "Off-Highway Mining Truck",
    "serial": "serial or N/A",
    "estimatedValue": "Estimated current market value"
  },
  "damageAssessment": [
    {
      "zone": "zone name",
      "severity": "Critical/Warning/Minor",
      "description": "Detailed damage description",
      "estimatedRepairCost": "$X,XXX - $XX,XXX",
      "safetyImpact": "Description of safety implications"
    }
  ],
  "totalEstimatedCost": "$XXX,XXX - $XXX,XXX range",
  "urgencyLevel": "Immediate/Urgent/Standard",
  "recommendedActions": ["action 1", "action 2", ...],
  "supportingEvidence": "Description of AI drone inspection methodology and evidence collected",
  "declaration": "Standard declaration text for the claimant to sign"
}

Be realistic with cost estimates for a CAT 797F (a $5M+ mining truck). Use actual repair cost ranges for heavy mining equipment.`;

  try {
    const openai = new OpenAI({ apiKey });
    const completion = await openai.chat.completions.create({
      model: "gpt-4o-mini",
      temperature: 0.4,
      max_tokens: 3000,
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userPrompt },
      ],
    });

    const raw = completion.choices[0]?.message?.content ?? "{}";
    const jsonMatch = raw.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      return NextResponse.json(
        { error: "Failed to parse claim document" },
        { status: 500 },
      );
    }

    const claim = JSON.parse(jsonMatch[0]);
    return NextResponse.json({ claim });
  } catch (e: any) {
    console.error("Claim generation error:", e);
    return NextResponse.json(
      { error: e.message ?? "Failed to generate claim" },
      { status: 500 },
    );
  }
}
