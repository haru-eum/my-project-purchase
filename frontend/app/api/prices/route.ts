import { NextRequest, NextResponse } from "next/server";
import { filterPrices, parseMaterialIds } from "../_lib/snapshot";

export async function GET(req: NextRequest): Promise<NextResponse> {
  const startDate = req.nextUrl.searchParams.get("start_date") ?? "";
  const endDate = req.nextUrl.searchParams.get("end_date") ?? "";
  const materialIds = parseMaterialIds(req.nextUrl.searchParams.get("material_ids"));

  if (!startDate || !endDate) {
    return NextResponse.json({ message: "start_date, end_date가 필요합니다." }, { status: 400 });
  }

  return NextResponse.json(
    filterPrices({
      startDate,
      endDate,
      materialIds,
    })
  );
}
