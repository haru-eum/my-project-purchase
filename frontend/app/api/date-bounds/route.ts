import { NextResponse } from "next/server";
import { getDateBounds } from "../_lib/snapshot";

export async function GET(): Promise<NextResponse> {
  return NextResponse.json(getDateBounds());
}
