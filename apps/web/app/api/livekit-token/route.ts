import { AccessToken, RoomAgentDispatch, RoomConfiguration } from "livekit-server-sdk";
import { NextResponse } from "next/server";

export const runtime = "nodejs";

function unauthorized() {
  return NextResponse.json({ error: "Invalid demo token" }, { status: 401 });
}

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing ${name}`);
  }
  return value;
}

function safeIdentity(raw: string | undefined): string {
  const cleaned = (raw ?? "").replace(/[^a-zA-Z0-9._-]/g, "").replace(/^\.+/, "").slice(0, 48);
  return /^[A-Za-z0-9]/.test(cleaned) ? cleaned : `driver-${crypto.randomUUID().slice(0, 8)}`;
}

function safeName(raw: string | undefined): string {
  const cleaned = (raw ?? "").replace(/[^\w\s.-]/g, "").trim().slice(0, 40);
  return cleaned || "Driver";
}

export async function POST(request: Request) {
  const expected = process.env.DEMO_ACCESS_TOKEN?.trim();
  if (expected) {
    const header =
      request.headers.get("x-demo-token") ??
      request.headers.get("authorization")?.replace(/^Bearer\s+/i, "");
    if (!header || header !== expected) {
      return unauthorized();
    }
  }

  let body: {
    room_name?: string;
    participant_identity?: string;
    participant_name?: string;
  } = {};
  try {
    body = (await request.json()) as typeof body;
  } catch {
    body = {};
  }

  try {
    const apiKey = requiredEnv("LIVEKIT_API_KEY");
    const apiSecret = requiredEnv("LIVEKIT_API_SECRET");
    const agentName = process.env.NEXT_PUBLIC_AGENT_NAME ?? "mid-drive";
    // Always mint a new room. Client-supplied names reuse existing rooms and
    // skip RoomConfiguration.agents dispatch-on-create.
    const roomName = `drive-${crypto.randomUUID()}`;
    const identity = safeIdentity(body.participant_identity);

    const token = new AccessToken(apiKey, apiSecret, {
      identity,
      name: safeName(body.participant_name),
      ttl: "15m",
    });
    token.addGrant({
      room: roomName,
      roomJoin: true,
      canPublish: true,
      canSubscribe: true,
      canPublishData: true,
    });
    token.roomConfig = new RoomConfiguration({
      agents: [new RoomAgentDispatch({ agentName })],
    });

    const participantToken = await token.toJwt();
    const serverUrl = process.env.NEXT_PUBLIC_LIVEKIT_URL ?? "ws://127.0.0.1:7880";

    return NextResponse.json(
      {
        server_url: serverUrl,
        participant_token: participantToken,
        room_name: roomName,
      },
      { status: 201 },
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "Token mint failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
