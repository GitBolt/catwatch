import { Magic } from "@magic-sdk/admin";
import { SignJWT, jwtVerify } from "jose";
import { cookies } from "next/headers";
import { prisma } from "./db";

const COOKIE_NAME = "cw_session";
const secret = new TextEncoder().encode(
  process.env.MAGIC_SECRET_KEY || "dev-fallback-secret",
);

let _magic: InstanceType<typeof Magic> | null = null;

async function getMagic() {
  if (!_magic) {
    _magic = await Magic.init(process.env.MAGIC_SECRET_KEY!);
  }
  return _magic;
}

/** Validate a Magic DID token, upsert the user, and return the user record. */
export async function loginWithDIDToken(didToken: string) {
  const magic = await getMagic();

  // Validate token signature + expiry
  magic.token.validate(didToken);

  // Get user metadata from Magic
  const metadata = await magic.users.getMetadataByToken(didToken);
  const email = metadata.email!;
  const issuer = metadata.issuer!;

  // Upsert user in our DB
  const user = await prisma.user.upsert({
    where: { magicIss: issuer },
    update: { email },
    create: { email, magicIss: issuer },
  });

  // Create a session JWT (7-day expiry)
  const token = await new SignJWT({ userId: user.id, email: user.email })
    .setProtectedHeader({ alg: "HS256" })
    .setExpirationTime("7d")
    .sign(secret);

  // Set cookie
  const cookieStore = await cookies();
  cookieStore.set(COOKIE_NAME, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 60 * 60 * 24 * 7,
    path: "/",
  });

  return user;
}

/** Read the session cookie and return {userId, email} or null. */
export async function getSession() {
  const cookieStore = await cookies();
  const token = cookieStore.get(COOKIE_NAME)?.value;
  if (!token) return null;

  try {
    const { payload } = await jwtVerify(token, secret);
    return { userId: payload.userId as string, email: payload.email as string };
  } catch {
    return null;
  }
}

/** Clear the session cookie. */
export async function logout() {
  const cookieStore = await cookies();
  cookieStore.delete(COOKIE_NAME);
}
