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
</head>
<body>
    <h2>输入关键词（英文）</h2>

    <form method="post">
        <input name="keyword" style="width:300px;height:30px">
        <button type="submit">搜索</button>
    </form>

    {% if results %}
        <h3>Top10竞品</h3>
        {% for r in results %}
            <div style="margin:20px 0;">
                <img src="{{r.image}}" width="120"><br>
                <b>{{r.title}}</b><br>
                销量：{{r.sold}}<br>
                价格：{{r.price}}<br>
            </div>
        {% endfor %}
    {% endif %}
</body>
</html>
"""

def fetch_data(keyword):
    url = "https://api.scrapecreators.com/v1/tiktok/shop/search"

    res = requests.get(
        url,
        headers={"x-api-key": API_KEY},
        params={
            "query": keyword,
            "region": "US",
            "page": 1
        },
        timeout=30
    )

    data = res.json()
    products = data.get("products", [])

    result = []

    for p in products:
        if not isinstance(p, dict):
            continue

        sold = (p.get("sold_info") or {}).get("sold_count", 0)
        price = (p.get("product_price_info") or {}).get("sale_price_decimal", "")
        title = p.get("title", "")

        image_list = (p.get("image") or {}).get("url_list") or []
        image = image_list[0] if image_list else ""

        result.append({
            "title": title,
            "sold": sold,
            "price": price,
            "image": image
        })

    result.sort(key=lambda x: x["sold"], reverse=True)

    return result[:10]


@app.route("/", methods=["GET", "POST"])
def home():
    results = None

    if request.method == "POST":
        keyword = request.form.get("keyword")
        results = fetch_data(keyword)

    return render_template_string(HTML, results=results)


if __name__ == "__main__":
    app.run()