// R-10 UI 文案
//
// 本文件属于 ReqGuard 评估测试集。本文件是**合规实现**，作为对照样本存在：
// 用于观察检查器会不会把合规项误判为不符合（误报）。
// 展示文案统一走 t(key) 取词条，组件里不出现硬编码文案。

import { Order, OrderStatus } from "./order";

const messages: Record<string, Record<string, string>> = {
  "zh-CN": {
    "order.title": "订单详情",
    "order.amount": "金额",
    "order.status.pending": "待审批",
    "order.status.approved": "已通过",
    "order.status.rejected": "已驳回",
    "order.status.unknown": "未知状态",
    "common.empty": "暂无数据",
  },
  "en-US": {
    "order.title": "Order detail",
    "order.amount": "Amount",
    "order.status.pending": "Pending review",
    "order.status.approved": "Approved",
    "order.status.rejected": "Rejected",
    "order.status.unknown": "Unknown status",
    "common.empty": "No data",
  },
};

let locale = "zh-CN";

export function setLocale(next: string): void {
  if (messages[next]) {
    locale = next;
  }
}

export function getLocale(): string {
  return locale;
}

/** 按当前语言取文案；缺失时回退到调用方给的兜底值，再不济返回 key。 */
export function t(key: string, fallback?: string): string {
  const table = messages[locale] ?? messages["zh-CN"];
  return table[key] ?? fallback ?? key;
}

/** 状态展示：通过文案 key 取用，组件内不含硬编码文本。 */
export function renderOrderStatus(order: Order): string {
  switch (order.status) {
    case OrderStatus.PENDING:
      return t("order.status.pending");
    case OrderStatus.APPROVED:
      return t("order.status.approved");
    case OrderStatus.REJECTED:
      return t("order.status.rejected");
    default:
      return t("order.status.unknown");
  }
}

/** 订单摘要行：标题、编号、金额、状态，全部走词条与本地化数字格式。 */
export function renderOrderSummary(order: Order): string {
  const amount = new Intl.NumberFormat(locale, {
    style: "currency",
    currency: locale === "zh-CN" ? "CNY" : "USD",
  }).format(order.amount);
  const parts = [
    t("order.title"),
    `#${order.id}`,
    `${t("order.amount")}: ${amount}`,
    renderOrderStatus(order),
  ];
  return parts.join(" · ");
}

/** 空态渲染。 */
export function renderEmptyState(): string {
  return t("common.empty");
}
