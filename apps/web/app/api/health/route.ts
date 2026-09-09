export const runtime = "nodejs";

export function GET() {
  return Response.json({
    ok: true,
    service: "mid-drive-web",
    tts: "rime",
    stt: "elevenlabs",
  });
}
