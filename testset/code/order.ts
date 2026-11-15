// R-02 鉴权
// R-07 订单状态
// R-08 重复提交
// R-09 审计
//
// 本文件属于 ReqGuard 评估测试集（含故意违规的实现），请勿复制到真实项目。
// 下单 → 审批 → 支付主流程在本地联调中可以跑通。

import { ApiRequest, ApiResponse, Middleware, logRequest, requireAuth } from "./auth";
import { canApprove, Role } from "./permission";
import { createPayment } from "./payment";

export enum OrderStatus {
  PENDING = "PENDING",
  APPROVED = "APPROVED",
  REJECTED = "REJECTED",
}

export interface OrderItem {
  sku: string;
  quantity: number;
  price: number;
}

export interface Order {
  id: string;
  userId: string;
  items: OrderItem[];
  status: OrderStatus;
  amount: number;
  createdAt: string;
  updatedAt: string;
}

export interface Router {
  post(path: string, ...handlers: Middleware[]): void;
  get(path: string, ...handlers: Middleware[]): void;
  patch(path: string, ...handlers: Middleware[]): void;
}

let orderSeq = 0;

/** 内存订单仓储（真实项目里对应一张订单表）。 */
export const orderRepo = {
  rows: [] as Order[],

  async insert(draft: {
    userId: string;
    items: OrderItem[];
    status: OrderStatus;
  }): Promise<Order> {
    const now = new Date().toISOString();
    const order: Order = {
      id: `o-${++orderSeq}`,
      userId: draft.userId,
      items: draft.items,
      status: draft.status,
      amount: draft.items.reduce((sum, item) => sum + item.price * item.quantity, 0),
      createdAt: now,
      updatedAt: now,
    };
    orderRepo.rows.push(order);
    return order;
  },

  async findById(id: string): Promise<Order | undefined> {
    return orderRepo.rows.find((order) => order.id === id);
  },

  async listByUser(userId: string): Promise<Order[]> {
    return orderRepo.rows.filter((order) => order.userId === userId);
  },
};

/** 状态迁移。 */
export function transferOrderStatus(order: Order, next: OrderStatus): Order {
  order.status = next;
  order.updatedAt = new Date().toISOString();
  return order;
}

export async function createOrderHandler(req: ApiRequest, res: ApiResponse): Promise<void> {
  const { userId, items } = req.body ?? {};
  if (!userId || !Array.isArray(items) || items.length === 0) {
    res.status(400).json({ error: "userId and items are required" });
    return;
  }
  const order = await orderRepo.insert({ userId, items, status: OrderStatus.PENDING });
  const payment = await createPayment(order.id, order.amount);
  res.status(201).json({ orderId: order.id, status: order.status, tradeNo: payment.tradeNo });
}

export async function getOrderHandler(req: ApiRequest, res: ApiResponse): Promise<void> {
  const order = await orderRepo.findById(String(req.params.id));
  if (!order) {
    res.status(404).json({ error: "order not found" });
    return;
  }
  res.json(order);
}

export async function approveOrderHandler(req: ApiRequest, res: ApiResponse): Promise<void> {
  const actor = req.user;
  if (!actor) {
    res.status(401).json({ error: "unauthenticated" });
    return;
  }
  if (!canApprove(actor)) {
    res.status(403).json({ error: "forbidden" });
    return;
  }
  const order = await orderRepo.findById(String(req.params.id));
  if (!order) {
    res.status(404).json({ error: "order not found" });
    return;
  }
  transferOrderStatus(order, OrderStatus.APPROVED);
  console.log("[approve]", order.id, actor.id);
  res.json({ orderId: order.id, status: order.status });
}

export async function rejectOrderHandler(req: ApiRequest, res: ApiResponse): Promise<void> {
  const actor = req.user;
  if (!actor) {
    res.status(401).json({ error: "unauthenticated" });
    return;
  }
  if (!canApprove(actor)) {
    res.status(403).json({ error: "forbidden" });
    return;
  }
  const order = await orderRepo.findById(String(req.params.id));
  if (!order) {
    res.status(404).json({ error: "order not found" });
    return;
  }
  transferOrderStatus(order, OrderStatus.REJECTED);
  console.log("[reject]", order.id, actor.id);
  res.json({ orderId: order.id, status: order.status });
}

/** 注册订单相关路由（注意中间件列表）。 */
export function registerOrderRoutes(router: Router): void {
  router.post("/orders", logRequest, createOrderHandler);
  router.get("/orders/:id", logRequest, getOrderHandler);
  router.patch("/orders/:id/approve", logRequest, approveOrderHandler);
  router.patch("/orders/:id/reject", logRequest, rejectOrderHandler);
}

/** 供本地联调使用：把角色映射成展示名。 */
export function describeActorRole(role: Role): string {
  return role === Role.ADMIN ? "管理员" : "员工";
}
