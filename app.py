from flask import Flask, request, render_template_string
import requests
import os

app = Flask(__name__)

API_KEY = os.environ.get("API_KEY")

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>TikTok竞品分析工具</title>
    <meta charset="utf-8">

    <style>
        body {
            font-family: Arial, sans-serif;
            padding: 30px;
            background: #f6f6f6;
        }

        h2 {
            margin-bottom: 20px;
        }

        .search-box {
            margin-bottom: 25px;
        }

        input {
            width: 380px;
            height: 38px;
            padding: 0 12px;
            font-size: 16px;
            border: 1px solid #ccc;
            border-radius: 6px;
        }

        button {
            height: 40px;
            padding: 0 20px;
            font-size: 16px;
            cursor: pointer;
            border: none;
            border-radius: 6px;
            background: #111;
            color: white;
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
            margin-bottom: 20px;
        }
    </style>
</head>

<body>

    <h2>TikTok Shop 竞品 Top10 分析工具</h2>

    <div class="search-box">
        <form method="post">
            <input name="keyword" placeholder="输入英文关键词，例如 dog grooming brush" value="{{ keyword or '' }}">
            <button type="submit">搜索</button>
        </form>
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

                {% if r.image %}
                    <img src="{{ r.image }}">
                {% else %}
                    <div class="image-placeholder"></div>
                {% endif %}

                <div class="content">
                    <div class="title">{{ loop.index }}. {{ r.title }}</div>

                    <div class="meta">销量：{{ r.sold }}</div>

                    <div class="price-row">
                        日常价：
                        {% if r.origin_price %}
                            <span class="origin">${{ r.origin_price }}</span>
                        {% else %}
                            -
                        {% endif %}
                    </div>

                    <div class="price-row">
                        活动价 / 当前价：
                        {% if r.sale_price %}
                            <span class="sale">${{ r.sale_price }}</span>
                        {% else %}
                            -
                        {% endif %}
                    </div>

                    <div class="price-row">
                        促销信息：
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


def fetch_data(keyword):
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

        price_info = p.get("product_price_info") or {}
        sold_info = p.get("sold_info") or {}
        image_info = p.get("image") or {}

        title = p.get("title", "")
        sold = sold_info.get("sold_count", 0)

        # 日常价 / 原价
        origin_price = price_info.get("origin_price_decimal", "")

        # 活动价 / 当前展示价
        sale_price = price_info.get("sale_price_decimal", "")

        # 促销信息：折扣与节省金额
        # 说明：这不是严格意义上的“券后价”，而是当前 Search 接口里能稳定拿到的促销展示信息
        discount = price_info.get("discount_format", "")
        saving = price_info.get("reduce_price_format", "")

        image_list = image_info.get("url_list") or []
        image = image_list[0] if image_list else ""

        result.append({
            "title": title,
            "sold": sold or 0,
            "origin_price": origin_price,
            "sale_price": sale_price,
            "discount": discount,
            "saving": saving,
            "image": image
        })

    result.sort(key=lambda x: x["sold"], reverse=True)

    return result[:10]


@app.route("/", methods=["GET", "POST"])
def home():
    results = None
    error = None
    keyword = ""

    if request.method == "POST":
        keyword = request.form.get("keyword", "").strip()

        if not keyword:
            error = "请输入关键词"
        else:
            try:
                results = fetch_data(keyword)
                if not results:
                    error = "没有搜索到商品数据，请换一个关键词"
            except Exception as e:
                error = str(e)

    return render_template_string(
        HTML,
        results=results,
        error=error,
        keyword=keyword
    )


if __name__ == "__main__":
    app.run()
