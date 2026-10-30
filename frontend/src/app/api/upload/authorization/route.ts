import { headers } from "next/headers";
import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";
import { buildBackendAuthHeaders, hasSignedBackendAuth } from "@/lib/backend-auth";
import { backendTraceHeaders } from "@/server/backend-api";

export async function POST(request: Request) {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const payload = await request.json().catch(() => null);
  if (payload) {
    const internalUrl = process.env.BACKEND_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const upstream = await fetch(`${internalUrl.replace(/\/$/, "")}/upload/authorize`, {
      method: "POST",
      headers: { ...buildBackendAuthHeaders(session.user.id), ...(await backendTraceHeaders()), "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
    if (!upstream.ok && upstream.status !== 404) {
      return new Response(upstream.body, { status: upstream.status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
    }
    const authorization = upstream.ok ? await upstream.json() : null;
    if (authorization?.storage === "s3") {
      return NextResponse.json(authorization, { headers: { "Cache-Control": "no-store" } });
    }
  }

  // In self-host mode or single-server VPS, ALWAYS use the Next.js streaming proxy (/api/upload).
  // This streams directly to http://backend:8000 over Docker's internal network,
  // completely eliminating CORS issues, port 8000 firewall blocks, and build-time URL mismatches.
  const isSelfHost =
    process.env.NEXT_PUBLIC_SELF_HOST === "true" ||
    process.env.SELF_HOST === "true" ||
    !process.env.NEXT_PUBLIC_API_URL ||
    process.env.NEXT_PUBLIC_API_URL.includes("localhost") ||
    !hasSignedBackendAuth();

  if (isSelfHost) {
    return NextResponse.json(
      {
        directUpload: false,
        reason: "proxy_upload",
      },
      {
        headers: {
          "Cache-Control": "no-store",
        },
      },
    );
  }

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const normalizedApiUrl = apiUrl.replace(/\/$/, "");

  return NextResponse.json(
    {
      directUpload: true,
      uploadUrl: `${normalizedApiUrl}/upload`,
      headers: buildBackendAuthHeaders(session.user.id),
    },
    {
      headers: {
        "Cache-Control": "no-store",
      },
    },
  );
}
