import { redirect } from "next/navigation";

export default function KeysRedirect() {
  redirect("/dashboard/settings");
}
