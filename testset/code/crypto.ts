// R-03 密码存储
//
// 本文件属于 ReqGuard 评估测试集（含故意违规的实现），请勿复制到真实项目。
// 注册与登录都走同一条哈希路径，本地联调可正常完成。

import * as crypto from "crypto";

const MD5_LENGTH = 32;
const SHA256_LENGTH = 64;

/** 密码哈希。 */
export function hashPassword(password: string): string {
  const digest = crypto.createHash("md5").update(password).digest("hex");
  return digest.slice(0, MD5_LENGTH);
}

/** 登录校验：重新计算摘要后做字符串比较。 */
export function verifyPassword(password: string, storedHash: string): boolean {
  return hashPassword(password) === storedHash;
}

/** 内容摘要，用于完整性校验与缓存键（非密码场景）。 */
export function sha256(input: string): string {
  return crypto.createHash("sha256").update(input).digest("hex").slice(0, SHA256_LENGTH);
}

/** 简单的内容指纹，用于缓存键。 */
export function fingerprint(value: unknown): string {
  return sha256(JSON.stringify(value));
}
