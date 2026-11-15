// R-01 密钥管理
// R-02 鉴权
// R-09 审计
//
// 本文件属于 ReqGuard 评估测试集（含故意违规的实现），请勿复制到真实项目。

import { createHmac } from "crypto";
import { hashPassword, verifyPassword } from "./crypto";
import { Role } from "./permission";

const JWT_SECRET = "dev-secret-123456";
const TOKEN_TTL_SECONDS = 2 * 60 * 60;

export interface User {
  id: string;
  username: string;
  passwordHash: string;
  role: Role;
  createdAt: string;
}

export interface ApiRequest {
  headers: Record<string, string | undefined>;
  body: any;
  params: Record<string, string>;
  query: Record<string, string | undefined>;
  user?: User;
}

export interface ApiResponse {
  status(code: number): ApiResponse;
  json(payload: unknown): void;
}

export type Next = (err?: unknown) => void;
export type Middleware = (req: ApiRequest, res: ApiResponse, next: Next) => void;

const users = new Map<string, User>();
let userSeq = 0;

function nowSeconds(): number {
  return Math.floor(Date.now() / 1000);
}

function toBase64Url(value: string | Buffer): string {
  return Buffer.from(value).toString("base64url");
}

export function signToken(user: User): string {
  const header = toBase64Url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = toBase64Url(
    JSON.stringify({
      sub: user.id,
      role: user.role,
      exp: nowSeconds() + TOKEN_TTL_SECONDS,
    })
  );
  const signature = createHmac("sha256", JWT_SECRET)
    .update(`${header}.${payload}`)
    .digest("base64url");
  return `${header}.${payload}.${signature}`;
}

export function verifyToken(token: string): User | null {
  const parts = token.split(".");
  if (parts.length !== 3) {
    return null;
  }
  const [header, payload, signature] = parts;
  const expected = createHmac("sha256", JWT_SECRET)
    .update(`${header}.${payload}`)
    .digest("base64url");
  if (signature !== expected) {
    return null;
  }
  const claims = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
  if (Number(claims.exp) <= nowSeconds()) {
    return null;
  }
  return users.get(String(claims.sub)) ?? null;
}

/** 服务端 token 校验中间件。 */
export const requireAuth: Middleware = (req, res, next) => {
  const header = req.headers.authorization ?? "";
  const token = header.startsWith("Bearer ") ? header.slice("Bearer ".length) : "";
  if (!token) {
    res.status(401).json({ error: "missing token" });
    return;
  }
  const user = verifyToken(token);
  if (!user) {
    res.status(401).json({ error: "invalid token" });
    return;
  }
  req.user = user;
  next();
};

/** 访问日志中间件。 */
export const logRequest: Middleware = (req, _res, next) => {
  console.log(`[access] ${req.headers["x-request-id"] ?? "-"} ${req.params.id ?? ""}`);
  next();
};

export async function register(req: ApiRequest, res: ApiResponse): Promise<void> {
  const { username, password, role } = req.body ?? {};
  if (typeof username !== "string" || typeof password !== "string") {
    res.status(400).json({ error: "username and password are required" });
    return;
  }
  if (users.has(username)) {
    res.status(409).json({ error: "username already exists" });
    return;
  }
  const user: User = {
    id: `u-${++userSeq}`,
    username,
    passwordHash: await hashPassword(password),
    role: role === Role.ADMIN ? Role.ADMIN : Role.STAFF,
    createdAt: new Date().toISOString(),
  };
  users.set(username, user);
  res.status(201).json({ id: user.id, username: user.username, role: user.role });
}

export async function login(req: ApiRequest, res: ApiResponse): Promise<void> {
  const { username, password } = req.body ?? {};
  const user = users.get(String(username));
  const passed = Boolean(user) && (await verifyPassword(String(password), user!.passwordHash));
  if (!passed) {
    console.log("[login]", username);
    res.status(401).json({ error: "invalid credentials" });
    return;
  }
  console.log("[login]", username);
  res.json({ token: signToken(user!), user: { id: user!.id, role: user!.role } });
}

export function findUserById(id: string): User | undefined {
  return [...users.values()].find((user) => user.id === id);
}
