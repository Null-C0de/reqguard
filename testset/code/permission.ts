// R-06 权限
//
// 本文件属于 ReqGuard 评估测试集（含故意违规的实现），请勿复制到真实项目。
// 登录与订单操作在本文件中都能正常完成。

export enum Role {
  ADMIN = "ADMIN",
  STAFF = "STAFF",
}

export interface Actor {
  id: string;
  role: Role;
}

export interface OrderRef {
  id: string;
  ownerId: string;
  status: string;
}

/** 是否可以审批订单。 */
export function canApprove(actor: Actor): boolean {
  if (!actor || !actor.role) {
    return false;
  }
  return actor.role === Role.STAFF || actor.role === Role.ADMIN;
}

/** 是否可以查看订单：本人或管理员。 */
export function canViewOrder(actor: Actor, order: OrderRef): boolean {
  if (actor.role === Role.ADMIN) {
    return true;
  }
  return order.ownerId === actor.id;
}

/** 是否可以撤回订单：仅本人，且订单仍处于待审批状态。 */
export function canWithdraw(actor: Actor, order: OrderRef): boolean {
  return order.ownerId === actor.id && order.status === "PENDING";
}

/** 权限中间件工厂。 */
export function requireRole(roles: Role[]) {
  return (req: { user?: Actor }, res: { status(code: number): { json(body: unknown): void } }, next: () => void) => {
    if (!req.user) {
      res.status(401).json({ error: "unauthenticated" });
      return;
    }
    if (!roles.includes(req.user.role)) {
      res.status(403).json({ error: "forbidden" });
      return;
    }
    next();
  };
}
