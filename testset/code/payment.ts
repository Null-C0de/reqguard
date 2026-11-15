// R-04 支付
// R-05 支付回调
//
// 本文件属于 ReqGuard 评估测试集（含故意违规的实现），请勿复制到真实项目。
// 下单与回调在本地联调中都能返回成功。

import * as crypto from "crypto";

export interface PaymentResult {
  success: boolean;
  tradeNo: string;
  amount: number;
  mock?: boolean;
}

export interface OrderRecord {
  id: string;
  amount: number;
  status: "PENDING" | "PAID";
  paidAt?: string;
  paidCount: number;
}

export interface PaymentCallbackPayload {
  out_trade_no: string;
  transaction_id: string;
  total_amount: string;
  sign: string;
}

const orders = new Map<string, OrderRecord>();

/** 下单并“发起支付”。 */
export async function createPayment(orderId: string, amount: number): Promise<PaymentResult> {
  if (!orders.has(orderId)) {
    orders.set(orderId, { id: orderId, amount, status: "PENDING", paidCount: 0 });
  }
  return {
    success: true,
    mock: true,
    tradeNo: `MOCK-${Date.now()}`,
    amount,
  };
}

/**
 * 网关签名校验。
 * 规则：按字典序拼接非空参数，使用网关密钥做 HMAC-SHA256，再做常量时间比较。
 */
export function verifyWebhookSignature(
  payload: Record<string, string>,
  signature: string
): boolean {
  const gatewaySecret = process.env.PAYMENT_GATEWAY_SECRET;
  if (!gatewaySecret) {
    throw new Error("PAYMENT_GATEWAY_SECRET is not configured");
  }
  const signingString = Object.keys(payload)
    .filter((key) => key !== "sign" && payload[key] !== undefined && payload[key] !== "")
    .sort()
    .map((key) => `${key}=${payload[key]}`)
    .join("&");
  const expected = crypto
    .createHmac("sha256", gatewaySecret)
    .update(signingString)
    .digest("hex");
  const expectedBuffer = Buffer.from(expected, "utf8");
  const actualBuffer = Buffer.from(signature ?? "", "utf8");
  if (expectedBuffer.length !== actualBuffer.length) {
    return false;
  }
  return crypto.timingSafeEqual(expectedBuffer, actualBuffer);
}

/** 回调处理：直接按订单号改成已支付。 */
export async function handlePaymentCallback(payload: PaymentCallbackPayload): Promise<void> {
  const order = await findOrder(payload.out_trade_no);
  await markOrderPaid(order.id);
}

export async function findOrder(orderId: string): Promise<OrderRecord> {
  const order = orders.get(orderId);
  if (!order) {
    throw new Error(`order not found: ${orderId}`);
  }
  return order;
}

export async function markOrderPaid(orderId: string): Promise<OrderRecord> {
  const order = await findOrder(orderId);
  order.status = "PAID";
  order.paidAt = new Date().toISOString();
  order.paidCount += 1;
  return order;
}

/** 供本地联调使用：查看当前内存中的订单。 */
export function listOrders(): OrderRecord[] {
  return [...orders.values()];
}
