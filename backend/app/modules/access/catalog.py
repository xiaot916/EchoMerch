from __future__ import annotations

from typing import TypedDict


class MenuDefinition(TypedDict):
    code: str
    parent_code: str | None
    name: str
    menu_type: str
    path: str
    component: str
    permission: str | None
    order: int
    hidden: bool


def _domain(
    code: str,
    name: str,
    path: str,
    order: int,
    permission: str,
    children: list[tuple[str, str, str, str]],
) -> list[MenuDefinition]:
    rows: list[MenuDefinition] = [{
        "code": f"domain:{code}",
        "parent_code": None,
        "name": name,
        "menu_type": "catalog",
        "path": path,
        "component": "Layout",
        "permission": permission,
        "order": order,
        "hidden": False,
    }]
    rows.extend({
        "code": item_code,
        "parent_code": f"domain:{code}",
        "name": item_name,
        "menu_type": "menu",
        "path": item_path,
        "component": "RouteView",
        "permission": item_permission,
        "order": order * 100 + index,
        "hidden": False,
    } for index, (item_code, item_name, item_path, item_permission) in enumerate(children, start=1))
    return rows


MENU_DEFINITIONS: tuple[MenuDefinition, ...] = tuple(
    row
    for domain in [
        _domain("ai", "AI 赋能", "/ai", 1, "analytics.read", [
            ("route:ai", "AI 决策中心", "/ai", "analytics.read"),
        ]),
        _domain("home", "首页", "/", 2, "analytics.read", [
            ("route:overview", "经营概览", "/", "analytics.read"),
        ]),
        _domain("transaction", "交易", "/analytics", 3, "analytics.read", [
            ("route:analytics", "交易分析", "/analytics", "analytics.read"),
        ]),
        _domain("traffic", "流量", "/traffic", 4, "analytics.read", [
            ("route:traffic", "流量总览", "/traffic", "analytics.read"),
        ]),
        _domain("customers", "客户", "/customers", 5, "analytics.read", [
            ("route:customers", "客户概况", "/customers", "analytics.read"),
            ("route:customer-members", "会员分析", "/customers/members", "analytics.read"),
        ]),
        _domain("products", "商品", "/products", 6, "analytics.read", [
            ("route:products", "商品表现", "/products", "analytics.read"),
            ("route:product-analysis", "单品分析", "/products/analysis", "analytics.read"),
            ("route:reviews", "评价分析", "/reviews", "analytics.read"),
        ]),
        _domain("promotion", "商品推广", "/promotions", 7, "analytics.read", [
            ("route:promotions", "推广分析", "/promotions", "analytics.read"),
            ("route:promotions-cps", "CPS 分析", "/promotions/cps", "analytics.read"),
        ]),
        _domain("marketing-activities", "营销活动", "/marketing/activities", 8, "analytics.read", [
            ("route:marketing-activities", "活动复盘", "/marketing/activities", "analytics.read"),
            ("route:marketing-flash-sale", "淘宝秒杀", "/marketing/flash-sale", "analytics.read"),
            ("route:marketing-new-customer", "新客礼金", "/marketing/new-customer", "analytics.read"),
            ("route:marketing-shopping-gold", "购物金", "/marketing/shopping-gold", "analytics.read"),
            ("route:marketing-bybt", "百亿补贴", "/marketing/bybt", "analytics.read"),
            ("route:marketing-utry", "U先试用", "/marketing/utry", "analytics.read"),
        ]),
        _domain("service", "客服", "/service", 9, "analytics.read", [
            ("route:service", "客服概览", "/service", "analytics.read"),
        ]),
        _domain("content", "内容", "/content", 10, "analytics.read", [
            ("route:content", "内容概览", "/content", "analytics.read"),
            ("route:live", "直播分析", "/live", "analytics.read"),
        ]),
        _domain("market", "市场", "/market", 11, "analytics.read", [
            ("route:market", "市场洞察", "/market", "analytics.read"),
        ]),
        _domain("brand-assets", "品牌资产", "/brand-assets", 12, "brand_assets.read", [
            ("route:brand-assets", "品牌总览", "/brand-assets", "brand_assets.read"),
        ]),
        _domain("data", "数据管理", "/imports/tasks", 13, "data.manage", [
            ("route:store-data", "店铺数据", "/store-data", "data.manage"),
            ("route:inventory", "库存管理", "/inventory", "analytics.read"),
            ("route:imports-tasks", "数据采集", "/imports/tasks", "data.manage"),
            ("route:imports-overview", "采集状态", "/imports/overview", "data.manage"),
            ("route:imports-settings", "采集设置", "/imports/settings", "data.manage"),
        ]),
        _domain("system", "系统", "/system/users", 14, "system.manage", [
            ("route:system-users", "用户管理", "/system/users", "system.manage"),
            ("route:system-roles", "角色管理", "/system/roles", "system.manage"),
            ("route:system-menus", "菜单管理", "/system/menus", "system.manage"),
            ("route:system-apis", "接口权限", "/system/apis", "system.manage"),
            ("route:system-notifications", "消息通知", "/system/notifications", "system.manage"),
            ("route:system-ai", "AI 配置", "/system/ai", "system.manage"),
        ]),
    ]
    for row in domain
)

MENU_CODES = frozenset(row["code"] for row in MENU_DEFINITIONS)
