"""极简 i18n：维护 zh / en 两套翻译字典，提供 detect_language / translate / build_t。

- 通过 Cookie `lang` 强制语言；否则按 Accept-Language 头检测
- 中间件把 lang 与 t() 注入到 request.state，并设置到 Jinja 全局
- /lang/{code} 用于手动切换并写 Cookie
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


SUPPORTED = ("zh", "en")
DEFAULT_LANG = "zh"
COOKIE_NAME = "lang"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 年


# ============================================================================
# 翻译字典
# ============================================================================

TRANSLATIONS: dict[str, dict[str, str]] = {
    # ---------- 通用 ----------
    "common.save": {"zh": "保存", "en": "Save"},
    "common.cancel": {"zh": "取消", "en": "Cancel"},
    "common.delete": {"zh": "删除", "en": "Delete"},
    "common.edit": {"zh": "编辑", "en": "Edit"},
    "common.submit": {"zh": "提交", "en": "Submit"},
    "common.back": {"zh": "返回", "en": "Back"},
    "common.required": {"zh": "必填", "en": "Required"},
    "common.optional": {"zh": "可选", "en": "Optional"},
    "common.confirm": {"zh": "确认", "en": "Confirm"},
    "common.close": {"zh": "关闭", "en": "Close"},
    "common.copy": {"zh": "复制", "en": "Copy"},
    "common.copied": {"zh": "已复制", "en": "Copied"},
    "common.refresh": {"zh": "点击刷新", "en": "Click to refresh"},
    "common.loading": {"zh": "加载中…", "en": "Loading…"},
    "common.lang_label": {"zh": "语言", "en": "Lang"},
    "common.lang_zh": {"zh": "中文", "en": "中文"},
    "common.lang_en": {"zh": "English", "en": "English"},

    # ---------- 站点默认 ----------
    "site.default_name": {"zh": "卡密提取", "en": "Card Key Redemption"},
    "site.default_subtitle": {"zh": "输入卡密查看内容", "en": "Enter your card key to view content"},

    # ---------- 前台提取页 ----------
    "front.card_key": {"zh": "卡密", "en": "Card Key"},
    "front.card_key_placeholder": {"zh": "请输入您的卡密", "en": "Enter your card key"},
    "front.card_key_placeholder_cute": {"zh": "请输入您的卡密 ✿", "en": "Enter your card key ✿"},
    "front.card_key_placeholder_pixel": {"zh": "输入卡密", "en": "ENTER YOUR KEY"},
    "front.captcha": {"zh": "验证码", "en": "Captcha"},
    "front.captcha_placeholder": {"zh": "请输入验证码", "en": "Enter the captcha"},
    "front.captcha_placeholder_short": {"zh": "四位数字", "en": "4 digits"},
    "front.captcha_placeholder_pixel": {"zh": "四位数字", "en": "4 DIGITS"},
    "front.extract": {"zh": "提取", "en": "Redeem"},
    "front.extract_arrow": {"zh": "提取 →", "en": "Redeem →"},
    "front.extract_pixel": {"zh": "开始 »", "en": "START »"},
    "front.confirm_extract": {"zh": "确认提取", "en": "Confirm"},
    "front.go": {"zh": "出发！", "en": "GO!"},
    "front.amount": {"zh": "提取数量", "en": "Amount"},
    "front.amount_pixel": {"zh": "数量", "en": "AMOUNT"},
    "front.remaining": {"zh": "剩余", "en": "Remaining"},
    "front.remaining_max": {"zh": "每次最多提取 {n} 条", "en": "Up to {n} items at a time"},
    "front.remaining_max_cute": {
        "zh": "每次最多提取 {n} 条 ฅ^•ﻌ•^ฅ",
        "en": "Up to {n} items at a time ฅ^•ﻌ•^ฅ",
    },
    "front.remaining_each": {"zh": "每次提取最多 {n} 条", "en": "Up to {n} items per request"},
    "front.extract_success": {"zh": "提取成功", "en": "Redeem successful"},
    "front.extract_success_cute": {"zh": "提取成功啦", "en": "All done!"},
    "front.extract_success_pixel": {"zh": "通关！", "en": "LEVEL CLEAR!"},
    "front.again": {"zh": "再次提取", "en": "Redeem again"},
    "front.again_pixel": {"zh": "1-2 下一关", "en": "1-2 NEXT"},
    "front.copy_content": {"zh": "复制内容", "en": "Copy content"},
    "front.copy": {"zh": "复制", "en": "COPY"},
    "front.copied_pixel": {"zh": "OK！", "en": "OK!"},
    "front.section_desc": {"zh": "说明", "en": "Notes"},
    "front.section_content": {"zh": "卡密内容", "en": "Content"},
    "front.section_desc_pixel": {"zh": "- 说明 -", "en": "- INFO -"},
    "front.section_content_pixel": {"zh": "- 内容 -", "en": "- ITEMS -"},

    # ---------- 前台错误 ----------
    "err.captcha_invalid": {"zh": "验证码错误", "en": "Invalid captcha"},
    "err.empty_key": {"zh": "请输入卡密", "en": "Please enter the card key"},
    "err.key_not_found": {"zh": "卡密不存在，请检查输入", "en": "Card key not found"},
    "err.key_used_up": {"zh": "该卡密额度已用完", "en": "Card key has been fully used"},
    "err.amount_invalid": {"zh": "请输入有效的提取数量", "en": "Please enter a valid amount"},
    "err.amount_exceed": {
        "zh": "提取数量超出剩余额度（剩余 {n}）",
        "en": "Amount exceeds remaining quota (remaining {n})",
    },
    "err.key_invalid": {"zh": "卡密无效", "en": "Invalid card key"},
    "err.product_missing": {"zh": "关联商品不存在", "en": "Linked product not found"},
    "err.stock_insufficient": {
        "zh": "商品库存不足（当前库存 {n}）",
        "en": "Insufficient stock (current stock {n})",
    },
    "err.quota_race": {"zh": "额度不足，请刷新后重试", "en": "Quota race, please retry"},
    "err.invalid_request": {"zh": "无效请求", "en": "Invalid request"},
    "info.extracted_with_quota": {
        "zh": "已提取 {n} 条，剩余额度 {r}",
        "en": "Redeemed {n} items, {r} remaining",
    },
    "info.extracted_with_count": {
        "zh": "已提取 {n} 条，剩余 {r} 条",
        "en": "Redeemed {n} items, {r} left",
    },

    # ---------- 登录 / 注册 ----------
    "auth.login_title": {"zh": "登录", "en": "Sign in"},
    "auth.register_title": {"zh": "注册", "en": "Sign up"},
    "auth.admin_panel": {"zh": "管理后台", "en": "Admin Panel"},
    "auth.login_subtitle": {"zh": "请使用管理员账号登录", "en": "Sign in with your admin account"},
    "auth.register_subtitle": {"zh": "创建管理员账号", "en": "Create an admin account"},
    "auth.username": {"zh": "用户名", "en": "Username"},
    "auth.username_placeholder": {"zh": "管理员用户名", "en": "Admin username"},
    "auth.username_register_placeholder": {"zh": "登录使用的用户名", "en": "Username for login"},
    "auth.username_min": {"zh": "至少 3 位", "en": "Min 3 chars"},
    "auth.password": {"zh": "密码", "en": "Password"},
    "auth.password_placeholder": {"zh": "登录密码", "en": "Password"},
    "auth.password_min": {"zh": "至少 6 位", "en": "Min 6 chars"},
    "auth.password_register_placeholder": {"zh": "设置一个强密码", "en": "Set a strong password"},
    "auth.confirm_password": {"zh": "确认密码", "en": "Confirm password"},
    "auth.confirm_password_placeholder": {"zh": "再次输入密码", "en": "Re-enter password"},
    "auth.signin": {"zh": "登录", "en": "Sign in"},
    "auth.signup": {"zh": "注册", "en": "Sign up"},
    "auth.no_account": {"zh": "没有账号？", "en": "No account?"},
    "auth.signup_link": {"zh": "立即注册", "en": "Sign up"},
    "auth.have_account": {"zh": "已有账号？", "en": "Already registered?"},
    "auth.signin_link": {"zh": "返回登录", "en": "Back to sign in"},
    "auth.first_user_admin": {
        "zh": "第一个注册的用户将自动成为管理员",
        "en": "The first user becomes admin automatically",
    },
    "err.user_or_pwd": {"zh": "用户名或密码错误", "en": "Invalid username or password"},
    "err.password_mismatch": {"zh": "两次密码输入不一致", "en": "Passwords do not match"},
    "err.short_credentials": {
        "zh": "用户名至少3位，密码至少6位",
        "en": "Username ≥ 3 chars, password ≥ 6 chars",
    },

    # ---------- 后台通用 ----------
    "admin.logout": {"zh": "退出", "en": "Sign out"},
    "admin.welcome_back": {"zh": "欢迎回来", "en": "Welcome back"},
    "admin.system_normal": {"zh": "系统运行正常", "en": "System running normally"},
    "admin.menu_dashboard": {"zh": "仪表盘", "en": "Dashboard"},
    "admin.menu_cards": {"zh": "卡密列表", "en": "Cards"},
    "admin.menu_card_add": {"zh": "添加卡密", "en": "Add Card"},
    "admin.menu_batch": {"zh": "批量导入", "en": "Batch Import"},
    "admin.menu_products": {"zh": "商品管理", "en": "Products"},
    "admin.menu_settings": {"zh": "系统设置", "en": "Settings"},
    "admin.menu_api_docs": {"zh": "API 文档", "en": "API Docs"},
    "admin.menu_front": {"zh": "访问前台", "en": "View Front"},
    "admin.wheel_hint": {"zh": "将光标移至扇区，点击展开", "en": "Hover a slice and click to open"},
    "admin.panel_title": {"zh": "管理面板", "en": "Admin Panel"},
    "admin.confirm_delete": {"zh": "确定删除？", "en": "Delete?"},
    "admin.confirm_delete_named": {"zh": "确定删除{label}？", "en": "Delete {label}?"},

    # ---------- 仪表盘 ----------
    "dashboard.title": {"zh": "仪表盘", "en": "Dashboard"},
    "dashboard.subtitle": {
        "zh": "欢迎回来，{user}。系统运行正常。",
        "en": "Welcome back, {user}. System is running normally.",
    },
    "dashboard.add_card": {"zh": "添加卡密", "en": "Add card"},
    "dashboard.batch_import": {"zh": "批量导入", "en": "Batch import"},
    "dashboard.total_cards": {"zh": "总卡密数", "en": "Total cards"},
    "dashboard.avail_cards": {"zh": "可用卡密", "en": "Available"},
    "dashboard.used_cards": {"zh": "已使用 / 已用完", "en": "Used / Exhausted"},
    "dashboard.total_products": {"zh": "商品总数", "en": "Total products"},
    "dashboard.shortcuts": {"zh": "快捷操作", "en": "Shortcuts"},
    "dashboard.usage": {"zh": "使用率", "en": "Usage"},
    "dashboard.usage_label": {"zh": "卡密使用率", "en": "Card usage"},
    "dashboard.used_n": {"zh": "已用 {n}", "en": "Used {n}"},
    "dashboard.left_n": {"zh": "剩余 {n}", "en": "Left {n}"},
    "dashboard.no_cards_yet": {
        "zh": "尚未创建任何卡密，",
        "en": "No cards yet, ",
    },
    "dashboard.add_now": {"zh": "立即添加", "en": "add one now"},
    "dashboard.start_using": {"zh": " 开始使用系统。", "en": " to get started."},
    "dashboard.all_used": {
        "zh": "所有卡密都已使用，",
        "en": "All cards have been used, ",
    },
    "dashboard.batch_refill": {"zh": "批量补充", "en": "batch refill"},
    "dashboard.system_good": {
        "zh": "系统运行良好，还有 ",
        "en": "All good, ",
    },
    "dashboard.cards_left_avail": {
        "zh": " 张可用卡密。",
        "en": " cards still available.",
    },
    "dashboard.about": {"zh": "关于", "en": "About"},
    "dashboard.site_name": {"zh": "站点名称", "en": "Site name"},
    "dashboard.login_user": {"zh": "登录账号", "en": "Logged in as"},
    "dashboard.admin_path": {"zh": "后台路径", "en": "Admin path"},
    "dashboard.front_url": {"zh": "前台地址", "en": "Front URL"},
    "dashboard.visit_front": {"zh": "访问首页 →", "en": "Visit front →"},

    # ---------- 卡密列表 ----------
    "cards.title": {"zh": "卡密列表", "en": "Cards"},
    "cards.subtitle": {
        "zh": "共 {total} 张卡密。点击卡密旁边的按钮即可复制。",
        "en": "{total} cards in total. Click the icon next to a key to copy.",
    },
    "cards.add": {"zh": "添加卡密", "en": "Add card"},
    "cards.batch_add": {"zh": "批量添加", "en": "Batch add"},
    "cards.search_placeholder": {"zh": "搜索卡密或内容…", "en": "Search keys or content…"},
    "cards.filter_all": {"zh": "全部", "en": "All"},
    "cards.filter_normal": {"zh": "通用", "en": "Normal"},
    "cards.filter_points": {"zh": "点数", "en": "Points"},
    "cards.filter_shared": {"zh": "共享库存", "en": "Shared stock"},
    "cards.col_id": {"zh": "ID", "en": "ID"},
    "cards.col_key": {"zh": "卡密", "en": "Key"},
    "cards.col_type": {"zh": "类型", "en": "Type"},
    "cards.col_content": {"zh": "内容 / 额度", "en": "Content / Quota"},
    "cards.col_created": {"zh": "创建时间", "en": "Created"},
    "cards.col_actions": {"zh": "操作", "en": "Actions"},
    "cards.copy_key": {"zh": "复制卡密", "en": "Copy key"},
    "cards.label_key": {"zh": "卡密", "en": "Key"},
    "cards.label_type": {"zh": "类型", "en": "Type"},
    "cards.label_quota": {"zh": "额度", "en": "Quota"},
    "cards.label_product_quota": {"zh": "商品/额度", "en": "Product / Quota"},
    "cards.label_content": {"zh": "内容", "en": "Content"},
    "cards.used_suffix": {"zh": "已用", "en": "used"},
    "cards.empty": {"zh": "暂无卡密", "en": "No cards yet"},
    "cards.add_now": {"zh": "立即添加 →", "en": "Add one →"},
    "cards.confirm_delete": {"zh": "卡密 {key}", "en": "card {key}"},
    "cards.prev_page": {"zh": "← 上一页", "en": "← Prev"},
    "cards.next_page": {"zh": "下一页 →", "en": "Next →"},
    "cards.page_of": {
        "zh": "第 {page} / {total_pages} 页 · 共 {total} 条",
        "en": "Page {page} of {total_pages} · {total} total",
    },

    # ---------- 添加卡密 ----------
    "card_form.title_add": {"zh": "添加卡密", "en": "Add Card"},
    "card_form.subtitle_add": {
        "zh": "为单张卡密设置内容、类型和说明信息",
        "en": "Configure a single card's content, type and description",
    },
    "card_form.return_list": {"zh": "返回列表", "en": "Back to list"},
    "card_form.card_type": {"zh": "卡密类型", "en": "Card type"},
    "card_form.type_normal": {"zh": "通用 — 直接显示内容", "en": "Normal — show content directly"},
    "card_form.type_points": {"zh": "点数 — 按行扣除额度", "en": "Points — deduct line by line"},
    "card_form.type_shared": {"zh": "共享库存 — 从商品库存发货", "en": "Shared — deliver from product stock"},
    "card_form.key_placeholder": {
        "zh": "买家用来提取的卡密字符串",
        "en": "The card key the buyer enters to redeem",
    },
    "card_form.key_hint": {
        "zh": "卡密区分大小写，建议使用足够复杂的字符串",
        "en": "Case-sensitive. Use a sufficiently random string.",
    },
    "card_form.content": {"zh": "内容", "en": "Content"},
    "card_form.content_placeholder": {
        "zh": "通用类型：填写完整内容\n点数类型：每行一条（如每行一个账号）",
        "en": "Normal: full content\nPoints: one item per line (e.g. one account per line)",
    },
    "card_form.content_hint_normal": {
        "zh": "通用类型：内容会一次性显示给用户",
        "en": "Normal: content is shown all at once",
    },
    "card_form.content_hint_points": {
        "zh": "点数类型：当前 {n} 行 = {n} 点额度",
        "en": "Points: currently {n} lines = {n} points",
    },
    "card_form.content_hint_points_default": {
        "zh": "点数类型：每行 1 点额度，总行数即总额度",
        "en": "Points: 1 line = 1 point. Total lines = total quota.",
    },
    "card_form.linked_product": {"zh": "关联商品", "en": "Linked product"},
    "card_form.choose_product": {"zh": "— 请选择商品 —", "en": "— Choose product —"},
    "card_form.product_remaining": {"zh": "（剩余 {n} 条）", "en": "(remaining {n})"},
    "card_form.no_products_yet": {"zh": "尚无商品，请先 ", "en": "No products yet, "},
    "card_form.create_product": {"zh": "创建商品", "en": "create one"},
    "card_form.quota": {"zh": "额度", "en": "Quota"},
    "card_form.quota_placeholder": {"zh": "该卡密可提取的总次数", "en": "Total redeemable count"},
    "card_form.description": {"zh": "描述说明", "en": "Description"},
    "card_form.description_placeholder": {
        "zh": "教程链接、使用说明等，提取时会展示给用户",
        "en": "Tutorial links, usage notes; shown to the user upon redeem",
    },
    "card_form.save": {"zh": "保存卡密", "en": "Save card"},
    "card_form.type_hint_normal": {
        "zh": "通用类型：用户输入卡密后将一次性显示全部内容",
        "en": "Normal: full content is shown after the user enters the key",
    },
    "card_form.type_hint_points": {
        "zh": "点数类型：每行算 1 点额度，用户每次提取消耗 N 行内容",
        "en": "Points: 1 line = 1 point; each redeem consumes N lines",
    },
    "card_form.type_hint_shared": {
        "zh": "共享库存：多张卡密共享同一商品的库存池",
        "en": "Shared: multiple cards share one product's stock pool",
    },
    "err.card_form.empty_key": {"zh": "卡密不能为空", "en": "Card key is required"},
    "err.card_form.empty_content": {"zh": "内容不能为空", "en": "Content is required"},
    "err.card_form.choose_product": {"zh": "请选择关联商品", "en": "Please choose a linked product"},
    "err.card_form.quota_positive": {"zh": "额度必须大于0", "en": "Quota must be greater than 0"},
    "err.card_form.duplicate": {"zh": "该卡密已存在", "en": "Card key already exists"},

    # ---------- 批量导入 ----------
    "batch.title": {"zh": "批量添加卡密", "en": "Batch Add Cards"},
    "batch.subtitle": {
        "zh": "每行一条，按格式批量导入卡密",
        "en": "One card per line, batch import in the given format",
    },
    "batch.data_section": {"zh": "批量数据", "en": "Batch Data"},
    "batch.input_data": {"zh": "输入数据", "en": "Input"},
    "batch.lines_unit": {"zh": "{n} 行", "en": "{n} lines"},
    "batch.placeholder": {
        "zh": "每行一条，格式见右侧说明",
        "en": "One card per line, see format on the right",
    },
    "batch.start_import": {"zh": "开始导入", "en": "Start import"},
    "batch.clear": {"zh": "清空", "en": "Clear"},
    "batch.load_example": {"zh": "填入示例", "en": "Load example"},
    "batch.format_section": {"zh": "格式说明", "en": "Format"},
    "batch.format_intro": {
        "zh": "每行一条，字段使用 | 分隔",
        "en": "One card per line, fields separated by |",
    },
    "batch.format_normal": {"zh": "通用类型", "en": "Normal"},
    "batch.format_points": {"zh": "点数类型", "en": "Points"},
    "batch.format_shared": {"zh": "共享库存", "en": "Shared stock"},
    "batch.format_note": {
        "zh": "重复的卡密会自动跳过，导入完成后会显示成功与跳过的数量",
        "en": "Duplicates are skipped automatically; the result shows added vs. skipped counts",
    },
    "batch.confirm_replace": {
        "zh": "当前已有内容，是否替换为示例？",
        "en": "There is existing content. Replace with the example?",
    },
    "batch.example_normal_content": {
        "zh": "这是一段通用卡密的内容",
        "en": "This is the content of a normal card",
    },
    "batch.example_shared_product": {"zh": "商品名", "en": "ProductName"},
    "err.batch.empty": {"zh": "内容为空", "en": "Empty input"},
    "info.batch.success": {
        "zh": "成功添加 {added} 条，跳过 {skipped} 条",
        "en": "Added {added}, skipped {skipped}",
    },

    # ---------- 商品管理 ----------
    "products.title": {"zh": "商品管理", "en": "Products"},
    "products.subtitle": {
        "zh": "商品作为共享库存类型卡密的库存池，可被多张卡密绑定",
        "en": "Products serve as stock pools for shared-stock cards",
    },
    "products.add": {"zh": "添加商品", "en": "Add product"},
    "products.search_placeholder": {"zh": "搜索商品…", "en": "Search products…"},
    "products.total_count": {"zh": "共 {n} 个商品", "en": "{n} products"},
    "products.col_id": {"zh": "ID", "en": "ID"},
    "products.col_name": {"zh": "商品名称", "en": "Name"},
    "products.col_stock": {"zh": "库存使用情况", "en": "Stock usage"},
    "products.col_created": {"zh": "创建时间", "en": "Created"},
    "products.col_actions": {"zh": "操作", "en": "Actions"},
    "products.label_name": {"zh": "名称", "en": "Name"},
    "products.label_stock": {"zh": "库存", "en": "Stock"},
    "products.empty": {"zh": "暂无商品", "en": "No products yet"},
    "products.add_now": {"zh": "立即添加 →", "en": "Add one →"},
    "products.confirm_delete": {
        "zh": "「{name}」？关联的卡密将无法提取",
        "en": "\"{name}\"? Bound cards will no longer redeem",
    },

    # ---------- 商品表单 ----------
    "product_form.title_add": {"zh": "添加商品", "en": "Add Product"},
    "product_form.title_edit": {"zh": "编辑商品", "en": "Edit Product"},
    "product_form.subtitle_add": {
        "zh": "创建商品，作为共享库存类型卡密的库存池",
        "en": "Create a product as the stock pool for shared-stock cards",
    },
    "product_form.subtitle_edit": {"zh": "修改商品信息或追加库存", "en": "Edit product info or top up stock"},
    "product_form.total_stock": {"zh": "总库存", "en": "Total"},
    "product_form.used_stock": {"zh": "已使用", "en": "Used"},
    "product_form.remaining": {"zh": "剩余", "en": "Remaining"},
    "product_form.name": {"zh": "商品名称", "en": "Product name"},
    "product_form.name_placeholder": {
        "zh": "用于标识商品，如：Netflix账号",
        "en": "e.g. Netflix Accounts",
    },
    "product_form.name_hint": {
        "zh": "名称需唯一，将在创建卡密时用于关联",
        "en": "Must be unique; used when binding cards",
    },
    "product_form.stock_content": {"zh": "库存内容", "en": "Stock content"},
    "product_form.stock_count_unit": {"zh": "{n} 条", "en": "{n} items"},
    "product_form.stock_placeholder": {
        "zh": "每行一条库存（如每行一个账号）",
        "en": "One item per line (e.g. one account per line)",
    },
    "product_form.stock_hint_edit": {
        "zh": "<strong>提示：</strong>当前显示的是剩余可用库存，保存时会自动加上已使用的部分（{n} 条）作为新的总库存",
        "en": "<strong>Note:</strong> shown is the remaining stock; on save, used items ({n}) are added back as the new total",
    },
    "product_form.stock_hint_add": {
        "zh": "每行一条，总行数即库存数量；可留空稍后再添加",
        "en": "One per line; total lines = stock count. May be empty for now.",
    },
    "product_form.save_edit": {"zh": "保存修改", "en": "Save changes"},
    "product_form.save_add": {"zh": "添加商品", "en": "Add product"},
    "err.product_form.empty_name": {"zh": "商品名称不能为空", "en": "Product name is required"},
    "err.product_form.duplicate": {"zh": "该商品名称已存在", "en": "Product name already exists"},

    # ---------- 系统设置 ----------
    "settings.title": {"zh": "系统设置", "en": "Settings"},
    "settings.subtitle": {"zh": "站点信息、后台路径、安全设置", "en": "Site info, admin path, security"},
    "settings.tab_site": {"zh": "站点信息", "en": "Site"},
    "settings.tab_template": {"zh": "前台模板", "en": "Template"},
    "settings.tab_prefix": {"zh": "后台路径", "en": "Admin path"},
    "settings.tab_api": {"zh": "API 接口", "en": "API"},
    "settings.tab_password": {"zh": "修改密码", "en": "Password"},
    "settings.section_site": {"zh": "站点信息", "en": "Site info"},
    "settings.site_saved": {"zh": "站点信息已保存", "en": "Site info saved"},
    "settings.site_name_label": {"zh": "站点名称", "en": "Site name"},
    "settings.site_name_hint": {
        "zh": "显示在浏览器标题、侧栏、登录页和前台首页",
        "en": "Shown in browser title, sidebar, sign-in and front home",
    },
    "settings.site_subtitle_label": {"zh": "副标题", "en": "Subtitle"},
    "settings.site_subtitle_hint": {
        "zh": "显示在前台首页的标题下方",
        "en": "Shown under the title on the front page",
    },
    "settings.section_template": {"zh": "前台模板", "en": "Front template"},
    "settings.template_saved": {"zh": "模板已切换", "en": "Template switched"},
    "settings.template_intro": {
        "zh": "选择前台用户访问时使用的模板风格，保存后立即生效",
        "en": "Choose the front-page template; takes effect immediately after saving",
    },
    "settings.tpl_default": {"zh": "默认模板", "en": "Default"},
    "settings.tpl_default_desc": {"zh": "简洁现代，适合大多数场景", "en": "Clean and modern, fits most cases"},
    "settings.tpl_cartoon": {"zh": "卡通模板", "en": "Cartoon"},
    "settings.tpl_cartoon_desc": {
        "zh": "可爱手绘风，圆润配色与小吉祥物",
        "en": "Cute hand-drawn style with a mascot",
    },
    "settings.tpl_mario": {"zh": "像素模板", "en": "Pixel"},
    "settings.tpl_mario_desc": {
        "zh": "超级马里奥风，8-bit 像素与砖块地面",
        "en": "Super-Mario inspired, 8-bit pixels and brick ground",
    },
    "settings.save_template": {"zh": "保存模板", "en": "Save template"},
    "settings.section_prefix": {"zh": "后台路径", "en": "Admin path"},
    "settings.prefix_saved": {"zh": "已保存到 .env 文件，重启服务后生效", "en": "Saved to .env, restart to take effect"},
    "settings.prefix_label": {"zh": "后台入口路径", "en": "Admin entry path"},
    "settings.prefix_hint": {
        "zh": "修改后将写入 .env 文件，需要重启服务才能生效。路径必须以 <code>/</code> 开头，仅允许字母、数字、下划线和短横线",
        "en": "Saved to .env, restart required. Must start with <code>/</code>; only letters, digits, underscore, dash allowed.",
    },
    "settings.prefix_current": {"zh": "<strong>当前路径：</strong>", "en": "<strong>Current path:</strong> "},
    "settings.prefix_example": {
        "zh": "<br>访问地址示例：",
        "en": "<br>Example URL: ",
    },
    "settings.confirm_prefix": {
        "zh": "修改后台路径会重写 .env 文件，需要重启服务后生效，确定继续？",
        "en": "Changing the admin path rewrites .env and requires a restart. Continue?",
    },
    "err.prefix_write": {"zh": "无法写入 .env：{exc}", "en": "Failed to write .env: {exc}"},
    "settings.section_api": {"zh": "API 接口", "en": "API"},
    "settings.api_created_alert": {
        "zh": "已创建「{name}」，请立即复制并妥善保存，此密钥只显示一次。",
        "en": "Created \"{name}\". Copy and save it now — this key is shown only once.",
    },
    "settings.api_intro_html": {
        "zh": "创建 API Key 用于对接外部系统，可通过 <code>X-API-Key</code> 请求头调用接口。",
        "en": "Create an API key to integrate with external systems via the <code>X-API-Key</code> header.",
    },
    "settings.api_docs_link": {"zh": "查看 API 文档 →", "en": "View API docs →"},
    "settings.api_name": {"zh": "名称", "en": "Name"},
    "settings.api_name_placeholder": {"zh": "例如：对接系统 A", "en": "e.g. System A"},
    "settings.api_create": {"zh": "创建 API Key", "en": "Create API key"},
    "settings.api_col_name": {"zh": "名称", "en": "Name"},
    "settings.api_col_prefix": {"zh": "密钥前缀", "en": "Key prefix"},
    "settings.api_col_status": {"zh": "状态", "en": "Status"},
    "settings.api_col_calls": {"zh": "调用次数", "en": "Calls"},
    "settings.api_col_last": {"zh": "最后使用", "en": "Last used"},
    "settings.api_col_created": {"zh": "创建时间", "en": "Created"},
    "settings.api_col_actions": {"zh": "操作", "en": "Actions"},
    "settings.api_active": {"zh": "启用", "en": "Active"},
    "settings.api_inactive": {"zh": "停用", "en": "Inactive"},
    "settings.api_enable": {"zh": "启用", "en": "Enable"},
    "settings.api_disable": {"zh": "停用", "en": "Disable"},
    "settings.api_confirm_delete": {
        "zh": "确定删除该 API Key？删除后无法恢复",
        "en": "Delete this API key? This cannot be undone.",
    },
    "settings.api_empty": {
        "zh": "还没有 API Key，创建一个开始对接吧",
        "en": "No API keys yet, create one to get started",
    },
    "settings.section_password": {"zh": "修改密码", "en": "Change password"},
    "settings.password_saved": {"zh": "密码修改成功", "en": "Password updated"},
    "settings.old_password": {"zh": "原密码", "en": "Current password"},
    "settings.new_password": {"zh": "新密码", "en": "New password"},
    "settings.confirm_new_password": {"zh": "确认新密码", "en": "Confirm new password"},
    "settings.save_password": {"zh": "修改密码", "en": "Update password"},
    "settings.confirm_password_form_alert": {
        "zh": "两次输入的新密码不一致",
        "en": "New passwords do not match",
    },
    "err.pwd_old": {"zh": "原密码错误", "en": "Current password is incorrect"},
    "err.pwd_mismatch": {"zh": "两次密码不一致", "en": "New passwords do not match"},
    "err.pwd_short": {"zh": "密码至少6位", "en": "Password must be at least 6 chars"},

    # ---------- API 文档 ----------
    "api_docs.title": {"zh": "API 文档", "en": "API Documentation"},
    "api_docs.subtitle": {
        "zh": "通过 API Key 对接卡密、商品库存等功能",
        "en": "Integrate cards / products / stock via API key",
    },
    "api_docs.toc": {"zh": "目录", "en": "Contents"},
    "api_docs.toc_auth": {"zh": "认证方式", "en": "Authentication"},
    "api_docs.toc_errors": {"zh": "错误响应", "en": "Errors"},
    "api_docs.toc_ping": {"zh": "健康检查 · /api/v1/ping", "en": "Health · /api/v1/ping"},
    "api_docs.toc_cards": {"zh": "卡密接口", "en": "Cards"},
    "api_docs.toc_cards_list": {"zh": "查询卡密列表", "en": "List cards"},
    "api_docs.toc_cards_get": {"zh": "查询单个卡密", "en": "Get one card"},
    "api_docs.toc_cards_create": {"zh": "添加卡密", "en": "Create card"},
    "api_docs.toc_cards_delete": {"zh": "删除卡密", "en": "Delete card"},
    "api_docs.toc_products": {"zh": "商品 / 库存接口", "en": "Products / Stock"},
    "api_docs.toc_products_list": {"zh": "查询商品列表", "en": "List products"},
    "api_docs.toc_products_get": {"zh": "查询单个商品", "en": "Get one product"},
    "api_docs.toc_products_stock": {"zh": "追加库存", "en": "Append stock"},
    "api_docs.toc_stats": {"zh": "统计 · /api/v1/stats", "en": "Stats · /api/v1/stats"},
    "api_docs.h_auth": {"zh": "认证方式", "en": "Authentication"},
    "api_docs.auth_intro_html": {
        "zh": "所有 <code>/api/v1/*</code> 接口都需要 API Key。在「系统设置 → API 接口」创建 Key 后，通过下面任一方式传入：",
        "en": "All <code>/api/v1/*</code> endpoints require an API key. Create one under Settings → API and pass it via either:",
    },
    "api_docs.auth_header_recommended": {
        "zh": "请求头 <code>X-API-Key: zfk_xxxxx</code>（推荐）",
        "en": "Header <code>X-API-Key: zfk_xxxxx</code> (recommended)",
    },
    "api_docs.auth_header_bearer": {
        "zh": "请求头 <code>Authorization: Bearer zfk_xxxxx</code>",
        "en": "Header <code>Authorization: Bearer zfk_xxxxx</code>",
    },
    "api_docs.callout_html": {
        "zh": "Base URL：<code>{base_url}</code><br>Key 仅在创建时显示一次，请妥善保管。被禁用或删除的 Key 立即失效。",
        "en": "Base URL: <code>{base_url}</code><br>Keys are shown only once on creation. Disabled or deleted keys are revoked immediately.",
    },
    "api_docs.h_errors": {"zh": "错误响应", "en": "Errors"},
    "api_docs.errors_intro_html": {
        "zh": "失败请求统一返回 <code>{ \"detail\": \"错误描述\" }</code>，HTTP 状态码：",
        "en": "Failures return <code>{ \"detail\": \"...\" }</code>. Status codes:",
    },
    "api_docs.err_400": {"zh": "<code>400</code> 参数错误", "en": "<code>400</code> Bad parameters"},
    "api_docs.err_401": {"zh": "<code>401</code> 缺少或无效的 API Key", "en": "<code>401</code> Missing or invalid API key"},
    "api_docs.err_404": {"zh": "<code>404</code> 资源不存在", "en": "<code>404</code> Not found"},
    "api_docs.err_409": {
        "zh": "<code>409</code> 资源冲突（如卡密已存在）",
        "en": "<code>409</code> Conflict (e.g. duplicate key)",
    },
    "api_docs.h_ping": {"zh": "健康检查", "en": "Health check"},
    "api_docs.ping_desc": {"zh": "验证 API Key 是否有效。", "en": "Validate the API key."},
    "api_docs.h_cards": {"zh": "卡密接口", "en": "Cards"},
    "api_docs.h_cards_list": {"zh": "查询卡密列表", "en": "List cards"},
    "api_docs.cards_list_intro": {"zh": "支持分页与筛选。Query 参数：", "en": "Pagination + filters. Query params:"},
    "api_docs.cards_list_page": {"zh": "<code>page</code> 页码，默认 1", "en": "<code>page</code> default 1"},
    "api_docs.cards_list_per_page": {
        "zh": "<code>per_page</code> 每页数量，默认 50，最大 200",
        "en": "<code>per_page</code> default 50, max 200",
    },
    "api_docs.cards_list_key": {
        "zh": "<code>key</code> 按卡密内容模糊搜索（可选）",
        "en": "<code>key</code> fuzzy search (optional)",
    },
    "api_docs.cards_list_type": {
        "zh": "<code>card_type</code> 类型过滤：<code>normal</code> | <code>points</code> | <code>shared_stock</code>（可选）",
        "en": "<code>card_type</code> filter: <code>normal</code> | <code>points</code> | <code>shared_stock</code> (optional)",
    },
    "api_docs.h_cards_get": {"zh": "查询单个卡密", "en": "Get one card"},
    "api_docs.cards_get_desc": {"zh": "按 ID 或卡密字符串查询单条。", "en": "Look up by ID or card key string."},
    "api_docs.h_cards_create": {"zh": "添加卡密", "en": "Create card"},
    "api_docs.cards_create_intro": {"zh": "请求体（JSON）：", "en": "Request body (JSON):"},
    "api_docs.cards_create_key": {
        "zh": "<code>key</code> 字符串，必填，唯一",
        "en": "<code>key</code> required, unique string",
    },
    "api_docs.cards_create_type": {
        "zh": "<code>card_type</code> 字符串，<code>normal</code>（默认） | <code>points</code> | <code>shared_stock</code>",
        "en": "<code>card_type</code> <code>normal</code> (default) | <code>points</code> | <code>shared_stock</code>",
    },
    "api_docs.cards_create_content": {
        "zh": "<code>content</code> <code>normal</code> 时为单条内容；<code>points</code> 时为多行内容（每行一条额度）",
        "en": "<code>content</code> for <code>normal</code>: single body; for <code>points</code>: multi-line (one per quota point)",
    },
    "api_docs.cards_create_description": {
        "zh": "<code>description</code> 可选说明",
        "en": "<code>description</code> optional notes",
    },
    "api_docs.cards_create_product_id": {
        "zh": "<code>product_id</code> <code>shared_stock</code> 必填，关联商品 ID",
        "en": "<code>product_id</code> required for <code>shared_stock</code>",
    },
    "api_docs.cards_create_total": {
        "zh": "<code>total_points</code> <code>shared_stock</code> 必填，可提取额度",
        "en": "<code>total_points</code> required for <code>shared_stock</code>",
    },
    "api_docs.cards_normal_card": {"zh": "<strong>普通卡密：</strong>", "en": "<strong>Normal card:</strong>"},
    "api_docs.cards_points_card": {"zh": "<strong>额度卡密（点数型）：</strong>", "en": "<strong>Points card:</strong>"},
    "api_docs.cards_shared_card": {"zh": "<strong>共享库存卡密：</strong>", "en": "<strong>Shared-stock card:</strong>"},
    "api_docs.h_cards_delete": {"zh": "删除卡密", "en": "Delete card"},
    "api_docs.h_products": {"zh": "商品 / 库存接口", "en": "Products / Stock"},
    "api_docs.h_products_list": {"zh": "查询商品列表", "en": "List products"},
    "api_docs.h_products_get": {"zh": "查询单个商品", "en": "Get one product"},
    "api_docs.h_products_stock": {"zh": "追加库存", "en": "Append stock"},
    "api_docs.products_stock_intro": {
        "zh": "向已有商品追加库存（不会重置已用数）。请求体：",
        "en": "Append stock to a product (used count is preserved). Body:",
    },
    "api_docs.products_stock_field": {
        "zh": "<code>stock</code> 字符串，多行；每行一条库存",
        "en": "<code>stock</code> multi-line string, one item per line",
    },
    "api_docs.h_stats": {"zh": "统计", "en": "Stats"},

    # ---------- 卡密类型徽章 ----------
    "badge.normal": {"zh": "通用", "en": "Normal"},
    "badge.points": {"zh": "点数", "en": "Points"},
    "badge.shared_stock": {"zh": "共享库存", "en": "Shared"},
}


# ============================================================================
# 检测与渲染
# ============================================================================


def _normalize(code: str) -> str:
    code = (code or "").strip().lower().replace("_", "-")
    if not code:
        return ""
    if code.startswith("zh"):
        return "zh"
    if code.startswith("en"):
        return "en"
    return ""


def parse_accept_language(header: str) -> str:
    """从 Accept-Language 头里挑出最优语言。无匹配返回空串。"""
    if not header:
        return ""
    candidates: list[tuple[float, str]] = []
    for piece in header.split(","):
        piece = piece.strip()
        if not piece:
            continue
        if ";" in piece:
            tag, _, qpart = piece.partition(";")
            q = 1.0
            qpart = qpart.strip()
            if qpart.startswith("q="):
                try:
                    q = float(qpart[2:])
                except ValueError:
                    q = 0.0
        else:
            tag, q = piece, 1.0
        norm = _normalize(tag)
        if norm:
            candidates.append((q, norm))
    if not candidates:
        return ""
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def detect_language(request: Request) -> str:
    """优先级：?lang= 查询参数 > Cookie > Accept-Language 头 > 默认 zh。"""
    qlang = request.query_params.get("lang")
    norm = _normalize(qlang or "")
    if norm in SUPPORTED:
        return norm

    cookie_lang = request.cookies.get(COOKIE_NAME)
    norm = _normalize(cookie_lang or "")
    if norm in SUPPORTED:
        return norm

    header = request.headers.get("accept-language", "")
    norm = parse_accept_language(header)
    if norm in SUPPORTED:
        return norm

    return DEFAULT_LANG


def translate(key: str, lang: str = DEFAULT_LANG, **kwargs) -> str:
    entry = TRANSLATIONS.get(key)
    if entry is None:
        return key
    raw = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    if kwargs:
        try:
            return raw.format(**kwargs)
        except (KeyError, IndexError):
            return raw
    return raw


def build_t(lang: str) -> Callable[..., str]:
    def _t(key: str, **kwargs) -> str:
        return translate(key, lang, **kwargs)
    return _t


# ============================================================================
# Starlette 中间件
# ============================================================================


class I18nMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 静态资源不需要语言上下文
        if request.url.path.startswith("/static"):
            request.state.lang = DEFAULT_LANG
            request.state.t = build_t(DEFAULT_LANG)
        else:
            lang = detect_language(request)
            request.state.lang = lang
            request.state.t = build_t(lang)
        return await call_next(request)
