import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/api/config";

export default async function RootPage() {
  const store = await cookies();
  const hasSession = store.has(ACCESS_COOKIE) || store.has(REFRESH_COOKIE);
  redirect(hasSession ? "/dashboard" : "/login");
}
