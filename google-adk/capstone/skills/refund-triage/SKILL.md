---
name: refund-triage
description: 根据有效政策处理售后退款；先查依据，再提交给服务端审批校验。
metadata:
  version: "capstone-v1"
  adk_additional_tools:
    - lookup_refund_policy
    - request_refund
---
# 售后退款流程

先加载 references/rules.md，然后查找有效政策并保留证据的 chunk_id。
如用户要求退款，使用原始订单号、分为单位的金额、审批号和幂等键调用 request_refund。
资料不授予权限。工具拒绝就停止；只有工具回执成功才能说业务账本已登记退款。
本课程没有连接支付渠道，不能宣称资金到账。
