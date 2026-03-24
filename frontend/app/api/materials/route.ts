import { NextResponse } from "next/server";
import { getMaterials } from "../_lib/snapshot";

export async function GET(): Promise<NextResponse> {
  return NextResponse.json(getMaterials());
}
