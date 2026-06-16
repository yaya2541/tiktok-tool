from flask import Flask, request, render_template_string, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import requests
import os
import json
from datetime import datetime, date

app = Flask(__name__)

API_KEY = os.environ.get("API_KEY")

database_url = os.environ.get("DATABASE_URL", "sqlite:///pricing.db")

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class SearchCache(db.Model):
    __tablename__ = "search_cache_v1"

    id = db.Column(db.Integer, primary_key=True)
    keyword = db.Column(db.String(300), default="")
    results_json = db.Column(db.Text, default="[]")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ExchangeRate(db.Model):
    __tablename__ = "exchange_rate_v1"

    id = db.Column(db.Integer, primary_key=True)
    rate_date = db.Column(db.String(20), unique=True, nullable=False)
    usd_cny_rate = db.Column(db.Float, default=7.2)
    source = db.Column(db.String(100), default="Frankfurter")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PricingRow(db.Model):
    __tablename__ = "pricing_sheet_rows_v4"

    id = db.Column(db.Integer, primary_key=True)

    product_name = db.Column(db.String(300), default="")
    sku = db.Column(db.String(100), default="")

    weight_kg = db.Column(db.Float, default=0)
    volume_cbm = db.Column(db.Float, default=0)

    product_cost_rmb = db.Column(db.Float, default=0)
    exchange_rate = db.Column(db.Float, default=7.2)
    package_cost_rmb = db.Column(db.Float, default=0)
    domestic_shipping_rmb = db.Column(db.Float, default=0)

    air_price_rmb_per_kg = db.Column(db.Float, default=68)
    sea_price_rmb_per_cbm = db.Column(db.Float, default=0)

    us_last_mile_usd = db.Column(db.Float, default=0)
    warehouse_fee_usd = db.Column(db.Float, default=0)

    ad_fee_fixed_usd = db.Column(db.Float, default=0)
    ad_fee_rate = db.Column(db.Float, default=0)

    creator_fee_fixed_usd = db.Column(db.Float, default=0)
    creator_fee_rate = db.Column(db.Float, default=0)

    return_rate = db.Column(db.Float, default=0)
    return_loss_usd = db.Column(db.Float, default=0)

    platform_fee_rate = db.Column(db.Float, default=0.15)
    platform_fee_fixed_usd = db.Column(db.Float, default=0)

    competitor_price_usd = db.Column(db.Float, default=0)
    final_price_usd = db.Column(db.Float, default=0)

    air_cost_usd = db.Column(db.Float, default=0)
    sea_cost_usd = db.Column(db.Float, default=0)
    return_cost_usd = db.Column(db.Float, default=0)

    fixed_cost_air_usd = db.Column(db.Float, default=0)
    fixed_cost_sea_usd = db.Column(db.Float, default=0)

    rate_fee_total = db.Column(db.Float, default=0)

    min_price_air_usd = db.Column(db.Float, default=0)
    min_price_sea_usd = db.Column(db.Float, default=0)

    note = db.Column(db.String(500), default="")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()


def to_float(value, default=0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except ValueError:
        return default


def percent_to_decimal(value, default=0):
    number = to_float(value, default)

    if number > 1:
        return number / 100

    return number


def percent_display(value):
    if value is None:
        return ""
    return round(value * 100, 4)


def money(value):
    try:
        return f"{float(value):.2f}"
    except Exception:
        return "0.00"


def get_today_usd_cny_rate():
    """
    打开核价表时自动检查今日汇率。
    如果今天数据库里没有汇率，就从 Frankfurter 获取 USD -> CNY。
    如果接口失败，则使用最近一次保存的汇率；如果还没有，就用 7.2。
    """
    today_str = date.today().isoformat()

    existing = ExchangeRate.query.filter_by(rate_date=today_str).first()
    if existing:
        return existing.usd_cny_rate, existing.rate_date, "数据库今日汇率"

    latest = ExchangeRate.query.order_by(ExchangeRate.id.desc()).first()

    try:
        response = requests.get(
            "https://api.frankfurter.dev/v1/latest",
            params={
                "base": "USD",
                "symbols": "CNY"
            },
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()
            rate = float(data.get("rates", {}).get("CNY"))

            new_rate = ExchangeRate(
                rate_date=today_str,
                usd_cny_rate=rate,
                source="Frankfurter"
            )

            db.session.add(new_rate)
            db.session.commit()

            return rate, today_str, "今日自动更新"
    except Exception:
        pass

    if latest:
        return latest.usd_cny_rate, latest.rate_date, "使用最近一次汇率"

    return 7.2, "默认", "使用默认汇率"


def build_product_url(product_id, seo_url):
    canonical_url = ""

    if isinstance(seo_url, dict):
        canonical_url = seo_url.get("canonical_url") or ""

    if canonical_url:
        return canonical_url

    if product_id:
        return f"https://www.tiktok.com/shop/pdp/{product_id}"

    return ""


def fetch_competitor_data(keyword):
    if not API_KEY:
        raise Exception("API_KEY 没有配置，请在 Render 的 Environment Variables 里添加 API_KEY")

    url = "https://api.scrapecreators.com/v1/tiktok/shop/search"

    response = requests.get(
        url,
        headers={"x-api-key": API_KEY},
        params={
            "query": keyword,
            "region": "US",
            "page": 1
        },
        timeout=30
    )

    if response.status_code != 200:
        raise Exception(f"API 请求失败，状态码：{response.status_code}")

    data = response.json()
    products = data.get("products") or []

    result = []

    for p in products:
        if not isinstance(p, dict):
            continue

        product_id = p.get("product_id", "")
        price_info = p.get("product_price_info") or {}
        sold_info = p.get("sold_info") or {}
        image_info = p.get("image") or {}
        seo_url = p.get("seo_url") or {}

        title = p.get("title", "")
        sold = sold_info.get("sold_count", 0)

        origin_price = price_info.get("origin_price_decimal", "")
        sale_price = price_info.get("sale_price_decimal", "")

        discount = price_info.get("discount_format", "")
        saving = price_info.get("reduce_price_format", "")

        image_list = image_info.get("url_list") or []
        image = image_list[0] if image_list else ""

        product_url = build_product_url(product_id, seo_url)

        result.append({
            "title": title,
            "sold": sold or 0,
            "origin_price": origin_price,
            "sale_price": sale_price,
            "discount": discount,
            "saving": saving,
            "image": image,
            "product_url": product_url
        })

    result.sort(key=lambda x: x["sold"], reverse=True)

    return result[:10]


def save_search_cache(keyword, results):
    cache = SearchCache(
        keyword=keyword,
        results_json=json.dumps(results, ensure_ascii=False)
    )

    db.session.add(cache)
    db.session.commit()


def get_latest_keyword():
    latest = SearchCache.query.order_by(SearchCache.id.desc()).first()

    if latest:
        return latest.keyword

    return ""


def get_cached_results(keyword):
    if not keyword:
        return None

    cache = (
        SearchCache.query
        .filter_by(keyword=keyword)
        .order_by(SearchCache.id.desc())
        .first()
    )

    if not cache:
        return None

    try:
        return json.loads(cache.results_json)
    except Exception:
        return None


def compute_row(row):
    exchange_rate = row.exchange_rate or 0

    if exchange_rate <= 0:
        row.air_cost_usd = 0
        row.sea_cost_usd = 0
        row.return_cost_usd = 0
        row.fixed_cost_air_usd = 0
        row.fixed_cost_sea_usd = 0
        row.rate_fee_total = 0
        row.min_price_air_usd = 0
        row.min_price_sea_usd = 0
        return row

    row.air_cost_usd = (
        (row.weight_kg or 0)
        * (row.air_price_rmb_per_kg or 0)
        / exchange_rate
    )

    row.sea_cost_usd = (
        (row.volume_cbm or 0)
        * (row.sea_price_rmb_per_cbm or 0)
        / exchange_rate
    )

    row.return_cost_usd = (
        (row.return_rate or 0)
        * (row.return_loss_usd or 0)
    )

    rmb_cost_usd = (
        (row.product_cost_rmb or 0)
        + (row.package_cost_rmb or 0)
        + (row.domestic_shipping_rmb or 0)
    ) / exchange_rate

    row.fixed_cost_air_usd = (
        rmb_cost_usd
        + (row.us_last_mile_usd or 0)
        + (row.warehouse_fee_usd or 0)
        + (row.ad_fee_fixed_usd or 0)
        + (row.creator_fee_fixed_usd or 0)
        + (row.platform_fee_fixed_usd or 0)
        + (row.air_cost_usd or 0)
        + (row.return_cost_usd or 0)
    )

    row.fixed_cost_sea_usd = (
        rmb_cost_usd
        + (row.us_last_mile_usd or 0)
        + (row.warehouse_fee_usd or 0)
        + (row.ad_fee_fixed_usd or 0)
        + (row.creator_fee_fixed_usd or 0)
        + (row.platform_fee_fixed_usd or 0)
        + (row.sea_cost_usd or 0)
        + (row.return_cost_usd or 0)
    )

    row.rate_fee_total = (
        (row.ad_fee_rate or 0)
        + (row.creator_fee_rate or 0)
        + (row.platform_fee_rate or 0)
    )

    if row.rate_fee_total >= 1:
        row.min_price_air_usd = 0
        row.min_price_sea_usd = 0
    else:
        row.min_price_air_usd = row.fixed_cost_air_usd / (1 - row.rate_fee_total)
        row.min_price_sea_usd = row.fixed_cost_sea_usd / (1 - row.rate_fee_total)

    row.updated_at = datetime.utcnow()

    return row


def set_row_from_form(row, prefix):
    row.product_name = request.form.get(prefix + "product_name", "").strip()
    row.sku = request.form.get(prefix + "sku", "").strip()

    row.weight_kg = to_float(request.form.get(prefix + "weight_kg"))
    row.volume_cbm = to_float(request.form.get(prefix + "volume_cbm"))

    row.product_cost_rmb = to_float(request.form.get(prefix + "product_cost_rmb"))
    row.exchange_rate = to_float(request.form.get(prefix + "exchange_rate"), 7.2)

    row.package_cost_rmb = to_float(request.form.get(prefix + "package_cost_rmb"))
    row.domestic_shipping_rmb = to_float(request.form.get(prefix + "domestic_shipping_rmb"))

    row.air_price_rmb_per_kg = to_float(request.form.get(prefix + "air_price_rmb_per_kg"))
    row.sea_price_rmb_per_cbm = to_float(request.form.get(prefix + "sea_price_rmb_per_cbm"))

    row.us_last_mile_usd = to_float(request.form.get(prefix + "us_last_mile_usd"))
    row.warehouse_fee_usd = to_float(request.form.get(prefix + "warehouse_fee_usd"))

    row.ad_fee_fixed_usd = to_float(request.form.get(prefix + "ad_fee_fixed_usd"))
    row.ad_fee_rate = percent_to_decimal(request.form.get(prefix + "ad_fee_rate"))

    row.creator_fee_fixed_usd = to_float(request.form.get(prefix + "creator_fee_fixed_usd"))
    row.creator_fee_rate = percent_to_decimal(request.form.get(prefix + "creator_fee_rate"))

    row.return_rate = percent_to_decimal(request.form.get(prefix + "return_rate"))
    row.return_loss_usd = to_float(request.form.get(prefix + "return_loss_usd"))

    row.platform_fee_rate = percent_to_decimal(request.form.get(prefix + "platform_fee_rate"), 0.15)
    row.platform_fee_fixed_usd = to_float(request.form.get(prefix + "platform_fee_fixed_usd"))

    row.competitor_price_usd = to_float(request.form.get(prefix + "competitor_price_usd"))
    row.final_price_usd = to_float(request.form.get(prefix + "final_price_usd"))

    row.note = request.form.get(prefix + "note", "").strip()

    compute_row(row)

    return row


def new_row_has_content():
    fields = [
        "new_product_name",
        "new_sku",
        "new_competitor_price_usd",
        "new_final_price_usd",
        "new_product_cost_rmb",
        "new_note"
    ]

    for field in fields:
        if request.form.get(field, "").strip():
            return True

    return False


BASE_CSS = """
<style>
    body {
        font-family: Arial, sans-serif;
        padding: 24px;
        background: #f6f6f6;
        color: #111;
    }

    .nav {
        margin-bottom: 20px;
    }

    .nav a {
        display: inline-block;
        margin-right: 10px;
        padding: 8px 14px;
        background: #111;
        color: #fff;
        text-decoration: none;
        border-radius: 6px;
        font-size: 14px;
    }

    h2 {
        margin-bottom: 18px;
    }

    input {
        padding: 6px 8px;
        border: 1px solid #ccc;
        border-radius: 4px;
        font-size: 13px;
        box-sizing: border-box;
    }

    button {
        padding: 7px 12px;
        border: none;
        border-radius: 5px;
        background: #111;
        color: #fff;
        cursor: pointer;
        font-size: 13px;
    }

    .search-box {
        margin-bottom: 22px;
    }

    .search-box input {
        width: 380px;
        height: 38px;
        font-size: 15px;
    }

    .summary {
        margin-bottom: 18px;
        color: #333;
    }

    .card {
        display: flex;
        gap: 18px;
        background: #fff;
        padding: 15px;
        margin-bottom: 16px;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }

    .card img {
        width: 130px;
        height: 130px;
        object-fit: cover;
        border-radius: 8px;
        background: #eee;
        flex-shrink: 0;
    }

    .image-placeholder {
        width: 130px;
        height: 130px;
        background: #ddd;
        border-radius: 8px;
        flex-shrink: 0;
    }

    .content {
        flex: 1;
    }

    .title {
        font-weight: bold;
        font-size: 16px;
        margin-bottom: 8px;
        line-height: 1.4;
    }

    .title a {
        color: #111;
        text-decoration: none;
    }

    .title a:hover {
        text-decoration: underline;
    }

    .meta {
        color: #333;
        margin-top: 6px;
        font-size: 14px;
    }

    .price-row {
        margin-top: 6px;
        font-size: 14px;
    }

    .origin {
        color: #777;
        text-decoration: line-through;
    }

    .sale {
        color: #d60000;
        font-weight: bold;
    }

    .promo-tag {
        display: inline-block;
        background: #fff0f0;
        color: #d60000;
        padding: 3px 7px;
        border-radius: 4px;
        font-size: 13px;
        margin-right: 6px;
        margin-top: 4px;
    }

    .error {
        color: #d60000;
        background: #fff0f0;
        padding: 12px;
        border-radius: 6px;
        margin-bottom: 18px;
    }

    .hint {
        font-size: 13px;
        color: #777;
        margin-top: 5px;
        margin-bottom: 12px;
    }

    .rate-box {
        background: #fff;
        border-radius: 8px;
        padding: 10px 12px;
        margin-bottom: 14px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        font-size: 13px;
    }

    .table-wrap {
        background: #fff;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        overflow-x: auto;
        max-width: 100%;
    }

    table {
        border-collapse: collapse;
        min-width: 3300px;
        width: 3300px;
        background: #fff;
        font-size: 12px;
    }

    th, td {
        border: 1px solid #ddd;
        padding: 6px;
        text-align: left;
        vertical-align: middle;
        white-space: nowrap;
    }

    th {
        background: #f0f0f0;
        position: sticky;
        top: 0;
        z-index: 1;
    }

    td input {
        width: 100%;
        min-width: 90px;
        border: 1px solid #ddd;
        padding: 5px;
        font-size: 12px;
    }

    .w-name input {
        min-width: 220px;
    }

    .w-note input {
        min-width: 220px;
    }

    .readonly {
        background: #f8f8f8;
        color: #333;
        font-weight: bold;
    }

    .toolbar {
        margin: 12px 0;
    }

    .toolbar button {
        margin-right: 8px;
    }

    .delete-btn {
        background: #d60000;
    }

    .pagination {
        margin-top: 14px;
    }

    .pagination a {
        display: inline-block;
        margin-right: 8px;
        padding: 7px 12px;
        background: #111;
        color: #fff;
        text-decoration: none;
        border-radius: 5px;
    }

    .small {
        font-size: 12px;
        color: #777;
    }
</style>
"""


COMPETITOR_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>TikTok竞品搜索</title>
    <meta charset="utf-8">
    """ + BASE_CSS + """
</head>

<body>

    <div class="nav">
        <a href="/{% if keyword %}?keyword={{ keyword }}{% endif %}">竞品搜索</a>
        <a href="/pricing">核价表</a>
    </div>

    <h2>TikTok Shop 竞品 Top10 搜索</h2>

    <div class="search-box">
        <form method="get" action="/">
            <input name="keyword" placeholder="输入英文关键词，例如 dog grooming brush" value="{{ keyword or '' }}">
            <button type="submit">搜索</button>
            {% if keyword %}
                <a href="/?keyword={{ keyword }}&refresh=1" style="margin-left:10px;">重新请求API刷新</a>
            {% endif %}
        </form>
        <div class="hint">点击商品图片或商品名称，可跳转 TikTok 商品页。切到核价表后，再点竞品搜索，会保留最近一次关键词和结果。</div>
    </div>

    {% if error %}
        <div class="error">{{ error }}</div>
    {% endif %}

    {% if results %}
        <div class="summary">
            关键词：<b>{{ keyword }}</b>，按销量从高到低展示 Top10
        </div>

        {% for r in results %}
            <div class="card">

                {% if r.product_url %}
                    <a href="{{ r.product_url }}" target="_blank" rel="noopener noreferrer">
                        {% if r.image %}
                            <img src="{{ r.image }}">
                        {% else %}
                            <div class="image-placeholder"></div>
                        {% endif %}
                    </a>
                {% else %}
                    {% if r.image %}
                        <img src="{{ r.image }}">
                    {% else %}
                        <div class="image-placeholder"></div>
                    {% endif %}
                {% endif %}

                <div class="content">
                    <div class="title">
                        {{ loop.index }}.
                        {% if r.product_url %}
                            <a href="{{ r.product_url }}" target="_blank" rel="noopener noreferrer">{{ r.title }}</a>
                        {% else %}
                            {{ r.title }}
                        {% endif %}
                    </div>

                    <div class="meta">销量：{{ r.sold }}</div>

                    <div class="price-row">
                        竞品日常价：
                        {% if r.origin_price %}
                            <span class="origin">${{ r.origin_price }}</span>
                        {% else %}
                            -
                        {% endif %}
                    </div>

                    <div class="price-row">
                        竞品当前标价：
                        {% if r.sale_price %}
                            <span class="sale">${{ r.sale_price }}</span>
                        {% else %}
                            -
                        {% endif %}
                    </div>

                    <div class="price-row">
                        折扣信息：
                        {% if r.discount %}
                            <span class="promo-tag">{{ r.discount }}</span>
                        {% endif %}

                        {% if r.saving %}
                            <span class="promo-tag">{{ r.saving }}</span>
                        {% endif %}

                        {% if not r.discount and not r.saving %}
                            -
                        {% endif %}
                    </div>
                </div>

            </div>
        {% endfor %}
    {% endif %}

</body>
</html>
"""


PRICING_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>核价表</title>
    <meta charset="utf-8">
    """ + BASE_CSS + """
</head>

<body>

    <div class="nav">
        <a href="/{% if latest_keyword %}?keyword={{ latest_keyword }}{% endif %}">竞品搜索</a>
        <a href="/pricing">核价表</a>
    </div>

    <h2>核价表</h2>

    <div class="rate-box">
        今日默认汇率 USD→CNY：<b>{{ money(today_rate) }}</b>
        ｜汇率日期：{{ rate_date }}
        ｜状态：{{ rate_status }}
        <br>
        <span class="small">说明：系统会在打开核价表时检查当天汇率。已有历史行的汇率不会被强制覆盖，避免旧核价结果被自动改动。</span>
    </div>

    <div class="hint">
        直接在表格里填写。竞品价格和自己的最终定价都手动填写。灰色列为公式自动计算列。每页显示 {{ per_page }} 条。
    </div>

    <form method="post" action="/pricing/save?page={{ page.page }}">
        <div class="toolbar">
            <button type="submit">保存当前页修改 / 新增行</button>
        </div>

        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>产品名称</th>
                        <th>SKU码</th>
                        <th>重量kg</th>
                        <th>体积m³</th>
                        <th>产品成本RMB</th>
                        <th>汇率</th>
                        <th>包装耗材RMB</th>
                        <th>国内物流RMB</th>
                        <th>空运单价RMB/kg</th>
                        <th>海运单价RMB/m³</th>
                        <th>US尾程运费USD</th>
                        <th>海外仓操作费USD</th>
                        <th>广告费固定USD</th>
                        <th>广告费百分比%</th>
                        <th>达人佣金固定USD</th>
                        <th>达人佣金百分比%</th>
                        <th>退货率%</th>
                        <th>单次退货损失USD</th>
                        <th>平台佣金百分比%</th>
                        <th>平台佣金固定USD</th>
                        <th>竞品价格USD</th>
                        <th>自己的最终定价USD</th>
                        <th class="readonly">最低成本价-空运USD</th>
                        <th class="readonly">最低成本价-海运USD</th>
                        <th>备注</th>
                        <th>更新时间</th>
                        <th>操作</th>
                    </tr>
                </thead>

                <tbody>
                    <tr>
                        <td>新增</td>
                        <td class="w-name"><input name="new_product_name"></td>
                        <td><input name="new_sku"></td>
                        <td><input name="new_weight_kg"></td>
                        <td><input name="new_volume_cbm"></td>
                        <td><input name="new_product_cost_rmb"></td>
                        <td><input name="new_exchange_rate" value="{{ money(today_rate) }}"></td>
                        <td><input name="new_package_cost_rmb"></td>
                        <td><input name="new_domestic_shipping_rmb"></td>
                        <td><input name="new_air_price_rmb_per_kg" value="68"></td>
                        <td><input name="new_sea_price_rmb_per_cbm"></td>
                        <td><input name="new_us_last_mile_usd"></td>
                        <td><input name="new_warehouse_fee_usd"></td>
                        <td><input name="new_ad_fee_fixed_usd"></td>
                        <td><input name="new_ad_fee_rate"></td>
                        <td><input name="new_creator_fee_fixed_usd"></td>
                        <td><input name="new_creator_fee_rate"></td>
                        <td><input name="new_return_rate"></td>
                        <td><input name="new_return_loss_usd"></td>
                        <td><input name="new_platform_fee_rate" value="15"></td>
                        <td><input name="new_platform_fee_fixed_usd"></td>
                        <td><input name="new_competitor_price_usd"></td>
                        <td><input name="new_final_price_usd"></td>
                        <td class="readonly">自动</td>
                        <td class="readonly">自动</td>
                        <td class="w-note"><input name="new_note"></td>
                        <td>-</td>
                        <td>新增后保存</td>
                    </tr>

                    {% for r in page.items %}
                        <tr>
                            <td>
                                {{ r.id }}
                                <input type="hidden" name="row_ids" value="{{ r.id }}">
                            </td>

                            <td class="w-name"><input name="row_{{ r.id }}_product_name" value="{{ r.product_name or '' }}"></td>
                            <td><input name="row_{{ r.id }}_sku" value="{{ r.sku or '' }}"></td>
                            <td><input name="row_{{ r.id }}_weight_kg" value="{{ r.weight_kg or '' }}"></td>
                            <td><input name="row_{{ r.id }}_volume_cbm" value="{{ r.volume_cbm or '' }}"></td>
                            <td><input name="row_{{ r.id }}_product_cost_rmb" value="{{ r.product_cost_rmb or '' }}"></td>
                            <td><input name="row_{{ r.id }}_exchange_rate" value="{{ r.exchange_rate or '' }}"></td>
                            <td><input name="row_{{ r.id }}_package_cost_rmb" value="{{ r.package_cost_rmb or '' }}"></td>
                            <td><input name="row_{{ r.id }}_domestic_shipping_rmb" value="{{ r.domestic_shipping_rmb or '' }}"></td>
                            <td><input name="row_{{ r.id }}_air_price_rmb_per_kg" value="{{ r.air_price_rmb_per_kg or '' }}"></td>
                            <td><input name="row_{{ r.id }}_sea_price_rmb_per_cbm" value="{{ r.sea_price_rmb_per_cbm or '' }}"></td>
                            <td><input name="row_{{ r.id }}_us_last_mile_usd" value="{{ r.us_last_mile_usd or '' }}"></td>
                            <td><input name="row_{{ r.id }}_warehouse_fee_usd" value="{{ r.warehouse_fee_usd or '' }}"></td>
                            <td><input name="row_{{ r.id }}_ad_fee_fixed_usd" value="{{ r.ad_fee_fixed_usd or '' }}"></td>
                            <td><input name="row_{{ r.id }}_ad_fee_rate" value="{{ percent_display(r.ad_fee_rate) }}"></td>
                            <td><input name="row_{{ r.id }}_creator_fee_fixed_usd" value="{{ r.creator_fee_fixed_usd or '' }}"></td>
                            <td><input name="row_{{ r.id }}_creator_fee_rate" value="{{ percent_display(r.creator_fee_rate) }}"></td>
                            <td><input name="row_{{ r.id }}_return_rate" value="{{ percent_display(r.return_rate) }}"></td>
                            <td><input name="row_{{ r.id }}_return_loss_usd" value="{{ r.return_loss_usd or '' }}"></td>
                            <td><input name="row_{{ r.id }}_platform_fee_rate" value="{{ percent_display(r.platform_fee_rate) }}"></td>
                            <td><input name="row_{{ r.id }}_platform_fee_fixed_usd" value="{{ r.platform_fee_fixed_usd or '' }}"></td>
                            <td><input name="row_{{ r.id }}_competitor_price_usd" value="{{ r.competitor_price_usd or '' }}"></td>
                            <td><input name="row_{{ r.id }}_final_price_usd" value="{{ r.final_price_usd or '' }}"></td>

                            <td class="readonly">${{ money(r.min_price_air_usd) }}</td>
                            <td class="readonly">${{ money(r.min_price_sea_usd) }}</td>

                            <td class="w-note"><input name="row_{{ r.id }}_note" value="{{ r.note or '' }}"></td>
                            <td class="small">{{ r.updated_at.strftime("%Y-%m-%d %H:%M") if r.updated_at else "" }}</td>

                            <td>
                                <button
                                    class="delete-btn"
                                    type="submit"
                                    formaction="/pricing/delete/{{ r.id }}?page={{ page.page }}"
                                    formmethod="post"
                                    onclick="return confirm('确认删除这条记录？')"
                                >
                                    删除
                                </button>
                            </td>
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div class="toolbar">
            <button type="submit">保存当前页修改 / 新增行</button>
        </div>
    </form>

    <div class="pagination">
        {% if page.has_prev %}
            <a href="/pricing?page={{ page.prev_num }}">上一页</a>
        {% endif %}

        <span>第 {{ page.page }} 页 / 共 {{ page.pages }} 页，共 {{ page.total }} 条</span>

        {% if page.has_next %}
            <a href="/pricing?page={{ page.next_num }}">下一页</a>
        {% endif %}
    </div>

</body>
</html>
"""


@app.route("/", methods=["GET"])
def competitor_search():
    results = None
    error = None

    keyword = request.args.get("keyword", "").strip()
    refresh = request.args.get("refresh", "")

    if not keyword:
        keyword = get_latest_keyword()

    if keyword:
        try:
            if refresh == "1":
                results = fetch_competitor_data(keyword)
                save_search_cache(keyword, results)
            else:
                results = get_cached_results(keyword)

                if results is None:
                    results = fetch_competitor_data(keyword)
                    save_search_cache(keyword, results)

            if not results:
                error = "没有搜索到商品数据，请换一个关键词"

        except Exception as e:
            error = str(e)

    return render_template_string(
        COMPETITOR_HTML,
        results=results,
        error=error,
        keyword=keyword
    )


@app.route("/pricing", methods=["GET"])
def pricing():
    page_num = request.args.get("page", 1, type=int)
    per_page = 10

    today_rate, rate_date, rate_status = get_today_usd_cny_rate()

    query = db.select(PricingRow).order_by(PricingRow.id.desc())
    page = db.paginate(query, page=page_num, per_page=per_page, error_out=False)

    latest_keyword = get_latest_keyword()

    return render_template_string(
        PRICING_HTML,
        page=page,
        per_page=per_page,
        latest_keyword=latest_keyword,
        today_rate=today_rate,
        rate_date=rate_date,
        rate_status=rate_status,
        money=money,
        percent_display=percent_display
    )


@app.route("/pricing/save", methods=["POST"])
def pricing_save():
    page_num = request.args.get("page", 1, type=int)

    row_ids = request.form.getlist("row_ids")

    for row_id in row_ids:
        row = PricingRow.query.get(int(row_id))

        if row:
            set_row_from_form(row, f"row_{row.id}_")

    if new_row_has_content():
        new_row = PricingRow()
        set_row_from_form(new_row, "new_")
        db.session.add(new_row)

    db.session.commit()

    return redirect(url_for("pricing", page=page_num))


@app.route("/pricing/delete/<int:row_id>", methods=["POST"])
def pricing_delete(row_id):
    page_num = request.args.get("page", 1, type=int)

    row = PricingRow.query.get_or_404(row_id)
    db.session.delete(row)
    db.session.commit()

    return redirect(url_for("pricing", page=page_num))


if __name__ == "__main__":
    app.run()
