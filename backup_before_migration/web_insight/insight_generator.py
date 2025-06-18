"""
Main class to identify trends, query the web, and build web-enhanced insights.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import datetime

import openai

from . import config, search_utils, search_utils_async

# --------------------------------------------------------------------------- #
# Logging & OpenAI setup
# --------------------------------------------------------------------------- #
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
openai.api_key = config.OPENAI_API_KEY


class WebEnhancedInsightGenerator:
    """Generate insights that combine ISM data with fresh web evidence."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or config.ISM_DB_PATH
        self.conn = self._get_db_connection()
        self._create_insights_table()

    # ---------------------  DB helpers  --------------------- #
    def _get_db_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_insights_table(self):
        cur = self.conn.cursor()
        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS web_insights (
            insight_id TEXT PRIMARY KEY,
            report_date DATE NOT NULL,
            index_name TEXT NOT NULL,
            trend_description TEXT NOT NULL,
            search_queries TEXT NOT NULL,
            evidence TEXT NOT NULL,
            analysis TEXT NOT NULL,
            investment_implications TEXT NOT NULL,
            created_at DATETIME NOT NULL
        )"""
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_web_insights_date ON web_insights(report_date)"
        )
        self.conn.commit()

    # -------------------  Trend detection  ------------------ #
    def identify_significant_trends(self, months_to_analyze: int = 2) -> list[dict]:
        try:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT report_date, month_year FROM reports ORDER BY report_date DESC LIMIT ?",
                (months_to_analyze,),
            )
            rows = [dict(r) for r in cur.fetchall()]
            if len(rows) < 2:
                return []

            curr, prev = rows[0], rows[1]

            def indices_for(date):
                cur.execute(
                    """
                    SELECT index_name,index_value,direction
                    FROM pmi_indices WHERE report_date=?""",
                    (date,),
                )
                return {r["index_name"]: dict(r) for r in cur.fetchall()}

            curr_idx, prev_idx = indices_for(curr["report_date"]), indices_for(prev["report_date"])

            trends = []
            for name, cd in curr_idx.items():
                if name not in prev_idx:
                    continue
                cv, pv = float(cd["index_value"]), float(prev_idx[name]["index_value"])
                change = cv - pv
                if abs(change) >= config.SIGNIFICANT_CHANGE_THRESHOLD:
                    desc = (
                        f"{name} rose {abs(change):.1f} points to {cv:.1f} in {curr['month_year']}"
                        if change > 0
                        else f"{name} fell {abs(change):.1f} points to {cv:.1f} in {curr['month_year']}"
                    )
                    trends.append(
                        {
                            "index_name": name,
                            "current_value": cv,
                            "previous_value": pv,
                            "change": change,
                            "direction": cd["direction"],
                            "month_year": curr["month_year"],
                            "report_date": curr["report_date"],
                            "description": desc,
                        }
                    )
            return sorted(trends, key=lambda t: abs(t["change"]), reverse=True)
        except Exception as exc:
            logger.error("identify_trends error: %s", exc)
            return []

    # --------------------  Evidence fetch  ------------------ #
    async def _fetch_and_process(self, results: list[dict]) -> list[dict]:
        urls = [r["url"] for r in results if r.get("url")]
        html_map = await search_utils_async.fetch_articles_concurrently(urls, 5)

        processed = []
        for r in results:
            url = r.get("url")
            if not url or url not in html_map:
                continue
            html = html_map[url]
            extraction = search_utils_async.extract_article_content(
                html, url, config.MAX_ARTICLE_LENGTH
            )
            date = r.get("date") or search_utils_async.extract_date_from_metadata(html)
            processed.append(
                {
                    "source": r.get("source", ""),
                    "title": extraction["title"] or r.get("title", ""),
                    "url": url,
                    "snippet": r.get("snippet", ""),
                    "date": date,
                    "content": extraction["content"],
                }
            )
        return processed

    # -----------------------  LLM  --------------------------- #
    def _analyse_with_llm(self, trend: dict, evidence: list[dict]) -> str:
        evidence_block = (
            "No relevant evidence found."
            if not evidence
            else "\n".join(
                f"SOURCE {i1}: {ev['source']} – {ev['title']}\nEXCERPT: {ev['content'][:400]}…\n"
                for i, ev in enumerate(evidence)
            )
        )

        prompt = f"""
You are an expert macro-economist and equity strategist.

**Task**  
Analyse the manufacturing-trend below **and return ONLY valid JSON** that
summarises investment implications.  Do NOT wrap it in code fences or add any
extra commentary.

Required JSON schema:
{{
  "sectors": [{{"name":"","impact":"bullish/bearish","reasoning":""}}],
  "companies": [{{"name":"","ticker":"","impact":"","reasoning":""}}],
  "timing":""
}}

**Trend**  
{trend['description']}  (current {trend['current_value']} vs {trend['previous_value']}; Δ {trend['change']} pts, {trend['direction']})

**Key Evidence**  
{evidence_block}
"""
        client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are an expert economic analyst."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()

    def _extract_investment_json(self, raw_json: str) -> dict:
        """
        raw_json is already intended to be pure JSON.  Parse it, and if that fails
        use a regex fallback that crudely looks for 'Sector:' / 'Company:' lines.
        """
        try:
            return json.loads(raw_json)
        except Exception:
            import re

            sectors, companies = [], []
            for line in raw_json.splitlines():
                if m := re.match(r"[-*]\s*Sector[:\-]\s*(.?)\s*\((bullish|bearish)\)", line, re.I):
                    sectors.append({"name": m[1].strip(), "impact": m[2].lower(), "reasoning": ""})
                elif m := re.match(r"[-*]\s*Company[:\-]\s*(.?)\s*\((bullish|bearish)\)", line, re.I):
                    companies.append({"name": m[1].strip(), "ticker": "", "impact": m[2].lower(), "reasoning": ""})
            return {"sectors": sectors, "companies": companies, "timing": ""}

    # -------------------  Main entry point  ----------------- #
    def generate_insight(self, trend_index: int = 0) -> dict:
        trends = self.identify_significant_trends()
        if not isinstance(trends, list) or not trends:
            return {"error": "No significant trends identified"}

        trend_index = trend_index if trend_index < len(trends) else 0
        trend = trends[trend_index]

        queries = search_utils.generate_month_aware_queries(trend, 4)
        all_results = []
        for q in queries:
            all_results.extend(
                search_utils.search_web(q, num_results=10, fetch_all_pages=True)
            )
        # de-dupe
        url_seen = set()
        uniq_results = [r for r in all_results if not (r["url"] in url_seen or url_seen.add(r["url"]))]

        evidence = asyncio.run(self._fetch_and_process(uniq_results[:20]))
        evidence = search_utils.filter_articles_by_similarity_and_freshness(
            evidence, trend["description"], 45, config.MAX_SEARCH_RESULTS
        )

        raw_json = self._analyse_with_llm(trend, evidence)
        implications = self._extract_investment_json(raw_json)

        insight = {
            "insight_id": f"INS-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            **trend,
            "search_queries": queries,
            "evidence": evidence,
            "analysis": analysis,
            "investment_implications": implications,
        }
        self._store_insight(insight)
        return insight

    def _store_insight(self, ins: dict) -> None:
        try:
            cur = self.conn.cursor()
            cur.execute(
                """
            INSERT INTO web_insights (
              insight_id, report_date, index_name, trend_description,
              search_queries, evidence, analysis, investment_implications,
              current_value, previous_value, change,
              created_at

            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ins["insight_id"],
                    ins["report_date"],
                    ins["index_name"],
                    ins["description"],
                    json.dumps(ins["search_queries"]),
                    json.dumps(ins["evidence"]),
                    ins["analysis"],
                    json.dumps(ins["investment_implications"]),
                    ins["current_value"],
                    ins["previous_value"],
                    ins["change"],
                    datetime.now().isoformat(),
                ),
            )
            self.conn.commit()
            logger.info("Insight stored %s", ins["insight_id"])
        except Exception as exc:
            logger.error("Store insight error: %s", exc)

    # ------------------- Retrieval helpers ------------------ #
    def get_all_insights(self, limit: int = 10) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM web_insights ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            r["search_queries"] = json.loads(r["search_queries"])
            r["evidence"] = json.loads(r["evidence"])
            r["investment_implications"] = json.loads(r["investment_implications"])
            # SQLite returns None for the new REAL columns when reading old rows;
            # guard so pills don’t blow up
            for k in ("current_value", "previous_value", "change"):
                r[k] = float(r.get(k) or 0)
        return rows

    def get_insight(self, iid: str) -> dict | None:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM web_insights WHERE insight_id=?", (iid,))
        row = cur.fetchone()
        if not row:
            return None
        r = dict(row)
        r["search_queries"] = json.loads(r["search_queries"])
        r["evidence"] = json.loads(r["evidence"])
        r["investment_implications"] = json.loads(r["investment_implications"])
        for k in ("current_value", "previous_value", "change"):
            r[k] = float(r.get(k) or 0)
        return r

    def delete_insight(self, iid: str) -> bool:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM web_insights WHERE insight_id=?", (iid,))
        self.conn.commit()
        return cur.rowcount > 0
