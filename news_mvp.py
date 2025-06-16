from flask import Flask, request, render_template
import requests
import os
from datetime import datetime, timedelta
from openai import OpenAI

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

GOOGLE_API_KEY = os.getenv("GOOGLE_CUSTOM_SEARCH_API_KEY")
SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

@app.route("/news")
def news_form():
    return render_template("news_simple.html")

@app.route("/news/summary", methods=["POST"])
def get_summary():
    company = request.form.get("company", "").strip()
    if not company:
        return render_template("news_simple.html", error="Please enter a company name")
    
    articles = fetch_google_news(company)
    summaries = generate_summaries(company, articles)
    return render_template("news_results.html", company=company, summaries=summaries)

def fetch_google_news(company):
    try:
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        query = f"{company} news after:{thirty_days_ago}"
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": GOOGLE_API_KEY,
            "cx": SEARCH_ENGINE_ID,
            "q": query,
            "sort": "date",
            "num": 10
        }
        res = requests.get(url, params=params)
        res.raise_for_status()
        return [{"title": i["title"], "snippet": i["snippet"], "link": i["link"]} for i in res.json().get("items", [])]
    except Exception as e:
        print(f"Error fetching news: {e}")
        return []

def generate_summaries(company, articles):
    if not articles:
        return {
            "executive": ["No recent articles found."],
            "investor": ["No recent articles found."],
            "consumer": ["No recent articles found."]
        }
    try:
        article_text = "\n".join(f"- {a['title']}: {a['snippet']} ({a['link']})" for a in articles)
        prompt = (
            f"You are a financial analyst. Summarize the following news about {company} "
            f"in three distinct styles:\n\n"
            f"{article_text}\n\n"
            f"1. Executive Summary:\n"
            f"2. Investor Insights:\n"
            f"3. Consumer Perspective:\n\n"
            f"Each section should include 3 bullet points and cite sources."
        )

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You summarize financial news for different audiences."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return parse_summaries(response.choices[0].message.content)
    except Exception as e:
        print(f"Error generating summaries: {e}")
        return {
            "executive": ["Error generating summary."],
            "investor": ["Error generating summary."],
            "consumer": ["Error generating summary."]
        }

def parse_summaries(text):
    sections = {"executive": [], "investor": [], "consumer": []}
    current = None
    for line in text.strip().splitlines():
        line = line.strip()
        if line.lower().startswith("1. executive"):
            current = "executive"
        elif line.lower().startswith("2. investor"):
            current = "investor"
        elif line.lower().startswith("3. consumer"):
            current = "consumer"
        elif line.startswith("-") and current:
            sections[current].append(line.lstrip("- ").strip())
    return sections
