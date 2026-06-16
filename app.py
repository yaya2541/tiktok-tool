from flask import Flask, request, render_template_string, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import requests
import os
from datetime import datetime

app = Flask(__name__)

API_KEY = os.environ.get("API_KEY")

database_url = os.environ.get("DATABASE_URL", "sqlite:///pricing.db")

# Render / Heroku 有时会给 postgres://，SQLAlchemy 需要 postgresql://
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class PricingRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    product_name = db.Column(db.String(300), default="")
    sku = db.Column(db.String(100), default="")

    competitor_price = db.Column(db.Float, default=0)
    product_cost_rmb = db.Column(db.Float, default=0)
    exchange_rate = db.Column(db.Float, default=7.2)

    package_cost_rmb = db.Column(db.Float, default=0)
    domestic_shipping_rmb = db.Column(db.Float, default=0)

    weight_kg = db.Column(db.Float, default=0)
    volume_cbm = db.Column(db.Float, default=0)

    air_price_rmb_per_kg = db.Column(db.Float, default=68)
    sea_price_rmb_per_cbm = db.Column(db.Float, default=0)

    us_last_mile_usd = db.Column(db.Float, default=0)
    warehouse_fee_usd = db.Column(db.Float, default=0)

    platform_rate = db.Column(db.Float, default=0.15)
    ad_rate = db.Column(db.Float, default=0)
    creator_rate = db.Column(db.Float, default=0)

    return_rate = db.Column(db.Float, default=0)
    return_loss_usd = db.Column(db.Float, default=0)

    target_price = db.Column(db.Float, default=0)

    air_cost_usd = db.Column(db.Float, default=0)
    sea_cost_usd = db.Column(db.Float, default=0)
    return_cost_usd = db.Column(db.Float, default=0)

    breakeven_air_price = db.Column(db.Float, default=0)
    breakeven_sea_price = db.Column(db.Float, default=0)

    profit_air = db.Column(db.Float, default=0)
    profit_sea = db.Column(db.Float, default=0)

    profit_rate_air = db.Column(db.Float, default=0)
    profit_rate_sea = db.Column(db.Float, default=0)

    note = db.Column(db.String(500), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()


BASE_CSS = """
<style>
    body {
        font-family: Arial, sans-serif;
        padding: 30px;
        background: #f6f6f6;
    }

    .nav {
        margin-bottom: 25px;
    }

    .nav a {
        display: inline-block;
        margin-right: 12px;
        padding: 8px 14px;
        background: #111;
        color: white;
        text-decoration: none;
        border-radius: 6px;
        font-size: 14px;
    }

    h2 {
        margin-bottom: 20px;
    }

    input, textarea {
        padding: 7px 8px;
        border: 1px solid #ccc;
        border-radius: 5px;
        font-size: 14px;
        box-sizing: border-box;
    }

    button {
        padding: 8px 14px;
        border: none;
        border-radius: 6px;
        background: #111;
        color: white;
        cursor: pointer;
        font-size: 14px;
    }

    .search-box {
        margin-bottom: 25px;
    }

    .search-box input {
        width: 380px;
        height: 38px;
    }

    .summary {
        margin-bottom: 20px;
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

    .open-link {
        display: inline-block;
        margin-top: 10px;
        padding: 6px 12px;
        background: #111;
        color: #fff;
        text-decoration: none;
        border-radius: 5px;
        font-size: 14px;
    }

    .error {
        color: #d60000;
        background: #fff0f0;
        padding: 12px;
        border-radius: 6px;
        margin-bottom: 20px;
    }

    .hint {
        font-size: 13px;
        color: #777;
        margin-top: 4px;
    }

    .form-panel {
        background: white;
        padding: 18px;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        margin-bottom: 25px;
    }

    .grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
    }

    .field label {
        display: block;
        font-size: 13px;
        color: #333;
        margin-bottom: 4px;
    }

    .field input {
        width: 100%;
    }

    .field-wide {
        grid-column: span 2;
    }

    .field-full {
        grid-column: span 4;
    }

    table {
        width: 100%;
        border-collapse: collapse;
        background: white;
        font-size: 13px;
    }

    th, td {
        border: 1px solid #ddd;
        padding: 8px;
        text-align: left;
        vertical-align: top;
    }

    th {
        background: #f0f0f0;
        white-space: nowrap;
    }

    .num {
        text-align: right;
    }

    .action-link {
        display: inline-block;
        margin-right: 6px;
        color: #111;
        text-decoration: underline;
    }

    .danger {
        color: #d60000;
    }

    .small {
        font-size: 12px;
        color: #777;
    }
</style>
"""


def to_float(value, default=0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except ValueError:
        return default


def percent_to_decimal(value, default=0):
    """
    支持两种输入：
    15 表示 15%
    0.15 也表示 15%
    """
    number = to_float(value, default)
    if number > 1:
        return number / 100
    return number


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


def calculate_pricing(form):
    product_cost_rmb = to_float(form.get("product_cost_rmb"))
    exchange_rate = to_float(form.get("exchange_rate"), 7.2)

    package_cost_rmb = to_float(form.get("package_cost_rmb"))
    domestic_shipping_rmb = to_float(form.get("domestic_shipping_rmb"))

    weight_kg = to_float(form.get("weight_kg"))
    volume_cbm = to_float(form.get("volume_cbm"))

    air_price_rmb_per_kg = to_float(form.get("air_price_rmb_per_kg"))
    sea_price_rmb_per_cbm = to_float(form.get("sea_price_rmb_per_cbm"))

    us_last_mile_usd = to_float(form.get("us_last_mile_usd"))
    warehouse_fee_usd = to_float(form.get("warehouse_fee_usd"))

    platform_rate = percent_to_decimal(form.get("platform_rate"), 0.15)
    ad_rate = percent_to_decimal(form.get("ad_rate"), 0)
    creator_rate = percent_to_decimal(form.get("creator_rate"), 0)

    return_rate = percent_to_decimal(form.get("return_rate"), 0)
    return_loss_usd = to_float(form.get("return_loss_usd"))

    target_price = to_float(form.get("target_price"))
    competitor_price = to_float(form.get("competitor_price"))

    air_cost_usd = 0
    sea_cost_usd = 0

    if exchange_rate > 0:
        air_cost_usd = weight_kg * air_price_rmb_per_kg / exchange_rate
        sea_cost_usd = volume_cbm * sea_price_rmb_per_cbm / exchange_rate

    return_cost_usd = return_rate * return_loss_usd

    rmb_fixed_cost_usd = 0
    if exchange_rate > 0:
        rmb_fixed_cost_usd = (product_cost_rmb + package_cost_rmb + domestic_shipping_rmb) / exchange_rate

    variable_rate = platform_rate + ad_rate + creator_rate

    fixed_air = rmb_fixed_cost_usd + air_cost_usd + us_last_mile_usd + warehouse_fee_usd + return_cost_usd
    fixed_sea = rmb_fixed_cost_usd + sea_cost_usd + us_last_mile_usd + warehouse_fee_usd + return_cost_usd

    if variable_rate >= 1:
        breakeven_air_price = 0
        breakeven_sea_price = 0
    else:
        breakeven_air_price = fixed_air / (1 - variable_rate)
        breakeven_sea_price = fixed_sea / (1 - variable_rate)

    final_target_price = target_price or competitor_price

    profit_air = 0
    profit_sea = 0
    profit_rate_air = 0
    profit_rate_sea = 0

    if final_target_price > 0:
        profit_air = final_target_price * (1 - variable_rate) - fixed_air
        profit_sea = final_target_price * (1 - variable_rate) - fixed_sea
        profit_rate_air = profit_air / final_target_price
        profit_rate_sea = profit_sea / final_target_price

    return {
        "air_cost_usd": air_cost_usd,
        "sea_cost_usd": sea_cost_usd,
        "return_cost_usd": return_cost_usd,
        "breakeven_air_price": breakeven_air_price,
        "breakeven_sea_price": breakeven_sea_price,
        "profit_air": profit_air,
        "profit_sea": profit_sea,
        "profit_rate_air": profit_rate_air,
        "profit_rate_sea": profit_rate_sea,
        "platform_rate": platform_rate,
        "ad_rate": ad_rate,
        "creator_rate": creator_rate,
        "return_rate": return_rate
    }


COMPETITOR_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>TikTok竞品分析工具</title>
    <meta charset="utf-8">
    """ + BASE_CSS + """
</head>

<body>

    <div class="nav">
        <a href="/">竞品搜索</a>
        <a href="/pricing">核价表</a>
    </div>

    <h2>TikTok Shop 竞品 Top10 分析工具</h2>

    <div class="search-box">
        <form method="post">
            <input name="keyword" placeholder="输入英文关键词，例如 dog grooming brush" value="{{ keyword or '' }}">
            <button type="submit">搜索</button>
        </form>
        <div class="hint">点击商品图片、商品名称或“打开商品”按钮，可跳转 TikTok 商品页。部分商品可能因地区、登录状态或 TikTok Web 限制无法直达。</div>
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

                    {% if r.product_url %}
                        <a class="open-link" href="{{ r.product_url }}" target="_blank" rel="noopener noreferrer">
                            打开商品
                        </a>
                    {% endif %}
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
        <a href="/">竞品搜索</a>
        <a href="/pricing">核价表</a>
    </div>

    <h2>核价表</h2>

    <div class="form-panel">
        <h3>{% if edit_record %}编辑核价记录{% else %}新增核价记录{% endif %}</h3>

        <form method="post" action="{% if edit_record %}/pricing/update/{{ edit_record.id }}{% else %}/pricing/add{% endif %}">

            <div class="grid">

                <div class="field field-wide">
                    <label>商品名称</label>
                    <input name="product_name" value="{{ edit_record.product_name if edit_record else '' }}">
                </div>

                <div class="field">
                    <label>SKU</label>
                    <input name="sku" value="{{ edit_record.sku if edit_record else '' }}">
                </div>

                <div class="field">
                    <label>参考竞品价 USD</label>
                    <input name="competitor_price" value="{{ edit_record.competitor_price if edit_record else '' }}">
                </div>

                <div class="field">
                    <label>商品进价 RMB</label>
                    <input name="product_cost_rmb" value="{{ edit_record.product_cost_rmb if edit_record else '' }}">
                </div>

                <div class="field">
                    <label>汇率</label>
                    <input name="exchange_rate" value="{{ edit_record.exchange_rate if edit_record else '7.2' }}">
                </div>

                <div class="field">
                    <label>包装耗材 RMB</label>
                    <input name="package_cost_rmb" value="{{ edit_record.package_cost_rmb if edit_record else '' }}">
                </div>

                <div class="field">
                    <label>国内物流 RMB</label>
                    <input name="domestic_shipping_rmb" value="{{ edit_record.domestic_shipping_rmb if edit_record else '' }}">
                </div>

                <div class="field">
                    <label>重量 kg</label>
                    <input name="weight_kg" value="{{ edit_record.weight_kg if edit_record else '' }}">
                </div>

                <div class="field">
                    <label>体积 m³</label>
                    <input name="volume_cbm" value="{{ edit_record.volume_cbm if edit_record else '' }}">
                </div>

                <div class="field">
                    <label>空运单价 RMB/kg</label>
                    <input name="air_price_rmb_per_kg" value="{{ edit_record.air_price_rmb_per_kg if edit_record else '68' }}">
                </div>

                <div class="field">
                    <label>海运单价 RMB/m³</label>
                    <input name="sea_price_rmb_per_cbm" value="{{ edit_record.sea_price_rmb_per_cbm if edit_record else '' }}">
                </div>

                <div class="field">
                    <label>US尾程运费 USD</label>
                    <input name="us_last_mile_usd" value="{{ edit_record.us_last_mile_usd if edit_record else '' }}">
                </div>

                <div class="field">
                    <label>海外仓操作费 USD</label>
                    <input name="warehouse_fee_usd" value="{{ edit_record.warehouse_fee_usd if edit_record else '' }}">
                </div>

                <div class="field">
                    <label>平台佣金 %</label>
                    <input name="platform_rate" value="{{ (edit_record.platform_rate * 100) if edit_record else '15' }}">
                </div>

                <div class="field">
                    <label>广告费 %</label>
                    <input name="ad_rate" value="{{ (edit_record.ad_rate * 100) if edit_record else '' }}">
                </div>

                <div class="field">
                    <label>达人佣金 %</label>
                    <input name="creator_rate" value="{{ (edit_record.creator_rate * 100) if edit_record else '' }}">
                </div>

                <div class="field">
                    <label>退货率 %</label>
                    <input name="return_rate" value="{{ (edit_record.return_rate * 100) if edit_record else '' }}">
                </div>

                <div class="field">
                    <label>单次退货损失 USD</label>
                    <input name="return_loss_usd" value="{{ edit_record.return_loss_usd if edit_record else '' }}">
                </div>

                <div class="field">
                    <label>目标售价 USD</label>
                    <input name="target_price" value="{{ edit_record.target_price if edit_record else '' }}">
                </div>

                <div class="field field-full">
                    <label>备注</label>
                    <input name="note" value="{{ edit_record.note if edit_record else '' }}">
                </div>

            </div>

            <br>

            <button type="submit">{% if edit_record %}保存修改{% else %}新增并保存{% endif %}</button>

            {% if edit_record %}
                <a class="action-link" href="/pricing">取消编辑</a>
            {% endif %}

        </form>
    </div>

    <h3>已保存核价记录</h3>

    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>商品</th>
                <th>SKU</th>
                <th>竞品价</th>
                <th>进价RMB</th>
                <th>最低不亏价-空运</th>
                <th>最低不亏价-海运</th>
                <th>目标售价</th>
                <th>利润-空运</th>
                <th>利润率-空运</th>
                <th>利润-海运</th>
                <th>利润率-海运</th>
                <th>备注</th>
                <th>时间</th>
                <th>操作</th>
            </tr>
        </thead>

        <tbody>
            {% for r in records %}
                <tr>
                    <td>{{ r.id }}</td>
                    <td>{{ r.product_name }}</td>
                    <td>{{ r.sku }}</td>
                    <td class="num">${{ "%.2f"|format(r.competitor_price or 0) }}</td>
                    <td class="num">{{ "%.2f"|format(r.product_cost_rmb or 0) }}</td>
                    <td class="num">${{ "%.2f"|format(r.breakeven_air_price or 0) }}</td>
                    <td class="num">${{ "%.2f"|format(r.breakeven_sea_price or 0) }}</td>
                    <td class="num">${{ "%.2f"|format(r.target_price or 0) }}</td>
                    <td class="num">${{ "%.2f"|format(r.profit_air or 0) }}</td>
                    <td class="num">{{ "%.1f"|format((r.profit_rate_air or 0) * 100) }}%</td>
                    <td class="num">${{ "%.2f"|format(r.profit_sea or 0) }}</td>
                    <td class="num">{{ "%.1f"|format((r.profit_rate_sea or 0) * 100) }}%</td>
                    <td>{{ r.note }}</td>
                    <td class="small">{{ r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "" }}</td>
                    <td>
                        <a class="action-link" href="/pricing/edit/{{ r.id }}">编辑</a>

                        <form method="post" action="/pricing/delete/{{ r.id }}" style="display:inline;">
                            <button class="danger" type="submit" onclick="return confirm('确认删除这条记录？')">删除</button>
                        </form>
                    </td>
                </tr>
            {% endfor %}
        </tbody>
    </table>

</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def competitor_search():
    results = None
    error = None
    keyword = ""

    if request.method == "POST":
        keyword = request.form.get("keyword", "").strip()

        if not keyword:
            error = "请输入关键词"
        else:
            try:
                results = fetch_competitor_data(keyword)
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
    records = PricingRecord.query.order_by(PricingRecord.id.desc()).all()

    return render_template_string(
        PRICING_HTML,
        records=records,
        edit_record=None
    )


@app.route("/pricing/add", methods=["POST"])
def add_pricing_record():
    form = request.form
    calc = calculate_pricing(form)

    record = PricingRecord(
        product_name=form.get("product_name", "").strip(),
        sku=form.get("sku", "").strip(),

        competitor_price=to_float(form.get("competitor_price")),
        product_cost_rmb=to_float(form.get("product_cost_rmb")),
        exchange_rate=to_float(form.get("exchange_rate"), 7.2),

        package_cost_rmb=to_float(form.get("package_cost_rmb")),
        domestic_shipping_rmb=to_float(form.get("domestic_shipping_rmb")),

        weight_kg=to_float(form.get("weight_kg")),
        volume_cbm=to_float(form.get("volume_cbm")),

        air_price_rmb_per_kg=to_float(form.get("air_price_rmb_per_kg")),
        sea_price_rmb_per_cbm=to_float(form.get("sea_price_rmb_per_cbm")),

        us_last_mile_usd=to_float(form.get("us_last_mile_usd")),
        warehouse_fee_usd=to_float(form.get("warehouse_fee_usd")),

        platform_rate=calc["platform_rate"],
        ad_rate=calc["ad_rate"],
        creator_rate=calc["creator_rate"],

        return_rate=calc["return_rate"],
        return_loss_usd=to_float(form.get("return_loss_usd")),

        target_price=to_float(form.get("target_price")),

        air_cost_usd=calc["air_cost_usd"],
        sea_cost_usd=calc["sea_cost_usd"],
        return_cost_usd=calc["return_cost_usd"],

        breakeven_air_price=calc["breakeven_air_price"],
        breakeven_sea_price=calc["breakeven_sea_price"],

        profit_air=calc["profit_air"],
        profit_sea=calc["profit_sea"],
        profit_rate_air=calc["profit_rate_air"],
        profit_rate_sea=calc["profit_rate_sea"],

        note=form.get("note", "").strip()
    )

    db.session.add(record)
    db.session.commit()

    return redirect(url_for("pricing"))


@app.route("/pricing/edit/<int:record_id>", methods=["GET"])
def edit_pricing_record(record_id):
    edit_record = PricingRecord.query.get_or_404(record_id)
    records = PricingRecord.query.order_by(PricingRecord.id.desc()).all()

    return render_template_string(
        PRICING_HTML,
        records=records,
        edit_record=edit_record
    )


@app.route("/pricing/update/<int:record_id>", methods=["POST"])
def update_pricing_record(record_id):
    record = PricingRecord.query.get_or_404(record_id)
    form = request.form
    calc = calculate_pricing(form)

    record.product_name = form.get("product_name", "").strip()
    record.sku = form.get("sku", "").strip()

    record.competitor_price = to_float(form.get("competitor_price"))
    record.product_cost_rmb = to_float(form.get("product_cost_rmb"))
    record.exchange_rate = to_float(form.get("exchange_rate"), 7.2)

    record.package_cost_rmb = to_float(form.get("package_cost_rmb"))
    record.domestic_shipping_rmb = to_float(form.get("domestic_shipping_rmb"))

    record.weight_kg = to_float(form.get("weight_kg"))
    record.volume_cbm = to_float(form.get("volume_cbm"))

    record.air_price_rmb_per_kg = to_float(form.get("air_price_rmb_per_kg"))
    record.sea_price_rmb_per_cbm = to_float(form.get("sea_price_rmb_per_cbm"))

    record.us_last_mile_usd = to_float(form.get("us_last_mile_usd"))
    record.warehouse_fee_usd = to_float(form.get("warehouse_fee_usd"))

    record.platform_rate = calc["platform_rate"]
    record.ad_rate = calc["ad_rate"]
    record.creator_rate = calc["creator_rate"]

    record.return_rate = calc["return_rate"]
    record.return_loss_usd = to_float(form.get("return_loss_usd"))

    record.target_price = to_float(form.get("target_price"))

    record.air_cost_usd = calc["air_cost_usd"]
    record.sea_cost_usd = calc["sea_cost_usd"]
    record.return_cost_usd = calc["return_cost_usd"]

    record.breakeven_air_price = calc["breakeven_air_price"]
    record.breakeven_sea_price = calc["breakeven_sea_price"]

    record.profit_air = calc["profit_air"]
    record.profit_sea = calc["profit_sea"]

    record.profit_rate_air = calc["profit_rate_air"]
    record.profit_rate_sea = calc["profit_rate_sea"]

    record.note = form.get("note", "").strip()

    db.session.commit()

    return redirect(url_for("pricing"))


@app.route("/pricing/delete/<int:record_id>", methods=["POST"])
def delete_pricing_record(record_id):
    record = PricingRecord.query.get_or_404(record_id)
    db.session.delete(record)
    db.session.commit()

    return redirect(url_for("pricing"))


if __name__ == "__main__":
    app.run()
