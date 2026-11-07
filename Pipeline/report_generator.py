import openai
from Pipeline.config import NEWS_API_KEY, NEWS_API_BACKUP, NEWS_API_BACKUP2, NEWS_API_BACKUP3, NEWS_API_BACKUP4, NEWS_API_BACKUP5, NEWS_API_BACKUP6, OPENAI_API_KEY, NEWS_LOOKBACK_DAYS, SECTOR_DEAL_TERMS, REGION_ANCHORS, ALPHA_VANTAGE_API_KEY
from newsapi.newsapi_client import NewsApiClient
import httpx
from datetime import datetime, timedelta
from pathlib import Path
import os
import requests
import json
from datetime import date, timedelta, timezone
import re
from newspaper import Article
import string
from Pipeline.additional_info_collector import get_company_info

#from main import base_path, json_path

base_path = Path(__file__).resolve().parent.parent 
raw_dir = base_path / 'api' / "static" / "assets" / "raw"
json_path = base_path/ 'api' / 'term_definitions.json'
brief_dir = base_path / 'api' / 'static' / 'assets' / 'briefs'
link_pat   = re.compile(r'\*\*(?P<title>.+?)\*\*\s*\(\s*\[Link\]\((?P<url>https?://[^\s)]+)\)\s*\)') #links

class IBDMarketAnalyst:
    def __init__(self):
        self.news_api = NewsApiClient(api_key=NEWS_API_KEY)
        self.customHttpXClient = httpx.Client(timeout=httpx.Timeout(120.0), # 120 s for connect/read/write/pool
                                              limits=httpx.Limits(max_connections=5, max_keepalive_connections=5)
                                             )
        self.openai_client = openai.Client(api_key=OPENAI_API_KEY,
                                            http_client=self.customHttpXClient)
        self.briefs_dir = base_path / 'api' /'static'/'assets'/'briefs'
        os.makedirs(self.briefs_dir, exist_ok=True)

        self.SECTOR_DEAL_TERMS = SECTOR_DEAL_TERMS
        self.REGION_ANCHORS = REGION_ANCHORS
    
    def _deal_terms_for(self, sector: str) -> str:
        """
        Return a NewsAPI-ready OR string like:
        "(merger OR acquisition OR buyout)"
        """
        raw_terms = self.SECTOR_DEAL_TERMS.get(
            sector.lower(), self.SECTOR_DEAL_TERMS["_default"]
        )
        # de-duplicate & lower-case for safety, then join
        or_block = " OR ".join({t.lower() for t in raw_terms})
        or_block = f"({or_block})"
        return f"({or_block})"
    
    def _anchors_for_region(self, region):
        """
        Return a NewsAPI-ready OR string like:
        "(European Commission OR DG COMP OR Frankfurt)"
        """
        raw_terms = self.REGION_ANCHORS.get(region, None)
        if not raw_terms:
            return None
        anchors = " OR ".join(raw_terms)
        anchors = f"({anchors})"
        return anchors

    def collect_news(self, categories, region, days_back: int = NEWS_LOOKBACK_DAYS):
        """
        Return list-of-lists of formatted article strings.
        First try qInTitle; if empty, fall back to q= (full-text).
        """
        start_cutoff = (datetime.now(timezone.utc) -
                        timedelta(days=days_back)).date()   

        max_pages  = 2
        page_size  = 10
        news_items = []

        for cat in categories:
            sector     = cat.split()[0].lower()
            deal_terms = self._deal_terms_for(sector)
            anchors = self._anchors_for_region(region)     
            query = f"{sector} AND {deal_terms}"
            if anchors:
                query = f"{query} AND {anchors}"

            def fetch(use_title_filter: bool):
                hits = []
                api_keys = [NEWS_API_KEY, NEWS_API_BACKUP, NEWS_API_BACKUP2, NEWS_API_BACKUP3, NEWS_API_BACKUP4, NEWS_API_BACKUP5, NEWS_API_BACKUP6]
                
                for current_key in api_keys:  # main key first, then fallback
                    headers = {"x-api-key": current_key}
                    for page in range(1, max_pages + 1):
                        params = {
                            "from": start_cutoff.isoformat(),
                            "language": "en",
                            "sortBy": "publishedAt",
                            "pageSize": page_size,
                            "page": page
                        }
                        params["qInTitle" if use_title_filter else "q"] = query
            
                        r = requests.get("https://newsapi.org/v2/everything", params=params, headers = headers, timeout=15)
            
                        if r.status_code == 429:
                            print(f"[NewsAPI 429] Rate limit hit for API key {current_key}")
                            break  # try next API key
            
                        if r.status_code != 200:
                            print(f"[NewsAPI {r.status_code}] {r.json().get('message')}")
                            break
            
                        for a in r.json().get("articles", []):
                            pub_date = a.get("publishedAt", "")[:10]
                            try:
                                pub_date = datetime.strptime(pub_date, "%Y-%m-%d").date()
                            except ValueError:
                                continue
                            if pub_date < start_cutoff:
                                continue
            
                            hits.append(
                                "Title: {title}\nDescription: {desc}\nSource: {src}\n"
                                "Published: {pub}\nURL: {url}\n".format(
                                    title=a.get("title", ""),
                                    desc=a.get("description", "") or "",
                                    src=a.get("source", {}).get("name", "N/A"),
                                    pub=pub_date,
                                    url=a.get("url", "")
                                )
                            )
                        if len(hits) >= 40:
                            break  # avoid unnecessary pages
                    if hits:
                        break  # stop retrying once successful
                return hits

            results = fetch(True) or fetch(False)
            print(f"Collected {len(results)} for '{cat}'.")
            news_items.append(results)

        return news_items


    def choose_best_news_with_gpt(self, news_items, sections, sector, region):
        links = []
        companies_by_section : list[list[str]] = []
        number_of_articles_to_choose = 4
        for articles, section in zip(news_items, sections):
            if not articles:                        
                print(f"No articles for section {section}; skipping GPT.")
                links.append([])
                companies_by_section.append([])
                continue

            companies_set = set()
            print(f"Choosing {number_of_articles_to_choose} from section {section}, which contains {len(articles)} articles...")
            news_by_cat = "\n\n".join(articles)

            system_message = (
            "You are a precise research assistant. "
            "Follow the format exactly. Never fabricate or modify URLs. "
            "If fewer valid items exist than requested, return fewer. "
            "Do not include numbering.")

            user_message = f"""Based on the title and preview of the following news articles, pls select EXACTLY {number_of_articles_to_choose} articles that BEST represents {section} in the {sector} sector. 
            
                            DO NOT INVENT OR HALLUCINATE ARTICLES. YOU MUST SELECT {number_of_articles_to_choose} UNLESS THE ARTICLES GIVEN ARE LESS THAN THE AMOUNT REQUIRED.
                            IT DOESN'T MATTER IF THE ARTICLE IS LACKING IN QUALITY, YOU MUST GIVE {number_of_articles_to_choose} RETURNS

                            Your output should be in this form EXACTLY (DO NOT DO IT IN ANY OTHER WAY):
                            **Link title** ([Link](https://linkURL))

                            For instance:
                            **JPMorgan Reports Increased M&A Activity in Healthcare Sector** ([Link](https://www.businessinsider.com/merger-acquisition-trends-1h-hreport-sponsors-volumes-anu-aiyengar-jpmorgan-2025-7))


                            Then at the end of your response, you should include a list of company names mentioned in the following format EXACTLY
                            COMPANIES: company name1 %% company name2 %% company name3 %% company name 4

                            For instance:
                            COMPANIES: Apple %% Microsoft %% JP Morgan %% GE HealthCare
                            

                            Do not include line numbers
                            Here are your news to choose from:
                            {news_by_cat}

                            YOU SHOULD ONLY USE THE ARTICLES PROVIDED, AND COPY THE LINKS EXACTLY AS IS 
                            """

            messages = [{"role": "system", "content": system_message},
            {"role": "user", "content": user_message}]
            print("Asking gpt...")

            response = self.openai_client.chat.completions.create(
                        model = "gpt-4o-mini",
                        messages = messages,
                        temperature=0.2
                    ).choices[0].message.content
            if not response:
                links.append([])
                companies_by_section.append([])
                print(f"Got no response for {section}")
                continue
            print("✓ Got response")
            lines = [ln.strip() for ln in response.splitlines() if ln.strip()]
            row = []
            for line in lines:
                if not line:
                    continue
                m = link_pat.match(line)
                if m:
                    row.append(f"{m['url']}")
                elif line.startswith("COMPANIES:") and len(line) > len("COMPANIES:"):
                    raw = line[len("COMPANIES:"):] 
                    company_names = raw.split("%%")
                    for company in company_names:
                        companies_set.add(re.sub(r"\s+", " ", company).strip(" ,.;:|").lower()) #cleanup and normalize the names before storing for return
            if row:
                if len(row) > number_of_articles_to_choose:
                    row = row[:number_of_articles_to_choose]
                links.append(row)
                companies_by_section.append(sorted(companies_set))   # append for this section
            else:
                links.append([])
                companies_by_section.append([])                      # keep shapes aligned
                print(f"No suitable articles found for section: {section}")
            print(f"✓ Got {len(row)} links for section: '{section}' region: {region} ")
            print(f"✓ Identified {len(companies_set)} companies for section: '{section}' region: {region}\n")
        print(f"✓ Got links for all {len(links)} sections region: {region}")
        print(f"✓ Got info for all {len(companies_by_section)} sections region: {region}")
        return links, companies_by_section

    def find_news_populate_context(self, links, companies, region):
        news_items = []
        section_tracker = 0
        for category, section_company in zip(links, companies):
            context = []
            if len(category) == 0:
                news_items.append(f"No articles found for this sector...")
                print(f"No news context for {section_tracker}, populated with place holder instead")
                section_tracker += 1
                continue

            if len(section_company) == 0:
                #Still process and include the article texts
                for link in category:
                    try:
                        article = Article(link)
                        article.download()
                        article.parse()
                        text = self.clean_article_text(article.text)
                        context.append(f"[TITLE]{article.title}:\n[TEXT]\n{text}\n[Source link]: {link}\n")
                    except Exception:
                        context.append(f"[Failed to load article at {link}]\n")
                
                #Add a note about missing company info
                context.append("No companies mentioned in this section")
                
                #Save the whole context string into news_items
                news_items.append("\n\n".join(context))
                section_tracker += 1
                continue


            for link in category:
                try:
                    article = Article(link)
                    article.download()
                    article.parse()
                    text = self.clean_article_text(article.text)
                    context.append(f"[TITLE]{article.title}:\n[TEXT]\n{text}\n[Source link]: {link}\n")


                except Exception as e:
                    print(f"Failed to process {link}")
                    context.append(f"[Failed to load article at {link}]\n")
            
            context.append("===== Company info for companies mentioned in news =====")
            print(f"Now gathering information on identified companies: {section_company}")
            for company_name in section_company:
                try:
                    company_info_dict = get_company_info(company_name, region)
                except Exception as e:
                    company_info_dict = {"name": company_name, "symbol": None, "error": str(e)}
                formatted = self.format_company_info(company_info_dict, company_name)  # see item 9
                context.append(formatted)
            section_tracker += 1
            
            news_items.append("\n\n".join(context))
            print(f"✓ Got news context for {section_tracker}")
        print("✓ All articles has been stored")
        return news_items
    
    def format_company_info(self, company_info_dict: dict, company_name: str) -> str:
        lines = [f"Company name: {company_name}"]
        for key, value in company_info_dict.items():
            lines.append(f"{key}: {value}")
        lines.append("-" * 66)
        return "\n".join(lines)

    def clean_article_text(self, text: str) -> str:
        """Remove boilerplate text, marketing filler, and irrelevant footers."""
        patterns = [
            r"(?i)about\s+(us|researchandmarkets\.com|the company|.*inc)\s*:?.*?(source link:|$)",
            r"(?i)cautionary note.*?(source link:|$)",
            r"(?i)for more information.*?(source link:|$)",
            r"(?i)why this report matters.*?(source link:|$)",
            r"(?i)sign up.*?(source link:|$)",
            r"(?i)browse related reports.*?(source link:|$)",
            r"(?i)conference call information.*?(source link:|$)",
            r"(?i)market.*?segmentation.*?(source link:|$)",
            r"(?i)forward-looking statements.*?(source link:|$)",
            r"(?i)press release.*?(source link:|$)",
            r"(?i)logo:.*?(source link:|$)",
            r"(?i)^source link:.*?$",
        ]
        for pat in patterns:
            text = re.sub(pat, "", text, flags=re.DOTALL)
        text = re.sub(r'\n{3,}', '\n\n', text)  # clean up blank lines
        return text.strip()



    def analyze_news(self, news_items, prompts, categories_required, CATEGORIES):
        if not prompts:
            raise TypeError("Prompts matrix is missing or empty.")
        if len(news_items) != categories_required:
            raise ValueError(f"Mismatch: expected {categories_required} categories, got {len(news_items)}")

        # ─── Fill prompt contexts ───────────────────────────────────────────
        for idx, articles in enumerate(news_items):
            if not articles:
                raise ValueError(f'No news for category "{CATEGORIES[idx]}"')
            prompts[idx][1] = articles

        analysis  = ""
        SYSTEM_MSG = (
            """You are a senior Investment Banking MD specializing in TMT M&A.
            Provide precise, data-driven analysis. Expand generic phrases into concrete 
            examples with tickers, use bullet points, and link Recommended Readings to the report.
            You should only use articles provided by the users.
            Take special care to formatting and follow the guidelines provided by users strictly.
            When adding links, use this EXACT format: **Link title** ([Link](https://linkURL))
            example: **JPMorgan Reports Increased M&A Activity in TMT Sector** ([Link](https://www.businessinsider.com/merger-acquisition-trends-1h-hreport-sponsors-volumes-anu-aiyengar-jpmorgan-2025-7))
            MAKE SURE THE LINKS MATCH THEIR TITLES
            For each link, ensure the link format is strictly maintained without any changes,
            and ensure that the link is valid and reachable. Do not modify the URL, and avoid any broken links."""
        )
        messages  = [{"role": "system", "content": SYSTEM_MSG}]

        # ——— Sections 1-5 ————————————————————————————————————————————————
        for idx, (section_prompt, context, max_tokens) in enumerate(prompts[:5]):
            max_token_limit = f"You have a maximum of {max_tokens}.\n Consider the token limit when writing reports and delegate them fairly."
            user_prompt = max_token_limit + section_prompt + ("\n You should only use these following news for this section: \n\n" + context if context else "")
            messages.append({"role": "user", "content": user_prompt})

            #keep system + last 2 turns (sliding window)
            context_window = [messages[0]] + messages[-2:]

            print(f"Sending section {idx + 1} …")
            resp = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=context_window,
                max_tokens=max_tokens,
                temperature=0.3,
                timeout=120
            )
            reply = resp.choices[0].message.content.strip()
            print(f"✓ got section {idx + 1}")

            analysis += "\n\n" + reply
            messages.append({"role": "assistant", "content": reply})

        # ——— Section 6 – Recommended Readings ————————————————
        readings_prompt, _, max_tokens = prompts[5]
        messages.append({"role": "user", "content": readings_prompt})

        print("Generating Recommended Readings …")
        resp = self.openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[messages[0], messages[2], messages[-1]],   # just system + response for section 1+ this user prompt
            max_tokens=max_tokens,
            temperature=0.3,
            timeout=120
        )
        readings = resp.choices[0].message.content.strip()
        analysis += "\n\n" + readings
        print(f"✓ got recommended readings")

        return analysis
    
    def verify_link(self, url: str) -> bool:
        try:
            response = requests.head(url, allow_redirects=True, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if response.ok:
                return True
            # fallback if HEAD unsupported
            response = requests.get(url, allow_redirects=True, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            return response.ok
        except requests.RequestException:
            return False
        
    def gather_information_via_gpt(self, user_prompt: str, link: str = None):
        """
        Simple helper method to gether information via gpt4o-mini-search-preview
        Pass in user prompt and optional source link to look at specifically
        """
        if link:
            user_prompt += "\n\n" + f"This is the link: {link}"

        response = self.openai_client.chat.completions.create(
            model="gpt-4o-mini-search-preview", 
            web_search_options={},
            messages=[{"role": "user", "content": user_prompt}]
        )
        response = response.choices[0].message.content.strip()
        return response


    def search_article_via_gpt(self, title, link):
        print(f"searching for link for {title}...")
        search_prompt = f"""Please search for the latest news article with the title '{title}' on the same website as this link: {link}. 
        Provide the full URL if available. And have ONLY ONE WORKING URL (which is the URL for the article you found) in an independent line in your response and NOTHING ELSE.
        When adding links, use this EXACT format: **Link title** ([Link](https://linkURL))
        example: **JPMorgan Reports Increased M&A Activity in TMT Sector** ([Link](https://www.businessinsider.com/merger-acquisition-trends-1h-hreport-sponsors-volumes-anu-aiyengar-jpmorgan-2025-7))
        """
        
        kwargs = {
            "model": "gpt-4o-mini-search-preview",
            "messages": [{"role": "user", "content": search_prompt}],
        }
        try:
            completion = self.openai_client.chat.completions.create(
                web_search_options={}, **kwargs
            )
        except TypeError:
            # Older openai SDKs don’t know web_search_options – use plain call
            completion = self.openai_client.chat.completions.create(**kwargs)

        response = completion.choices[0].message.content.strip()

        # Extract the URL from the response
        found_url = re.findall(r'\[Link\]\((https?://[^\s\)]+)\)', response)
        
        # Check if URL looks valid and return it
        if found_url:  # basic check to see if URL is provided
            url = found_url[0]
            print(f"Found url {url}")
            return url
        else:
            return None

    def replace_broken_links(self, analysis: str):
        link_pat   = re.compile(r'\*\*(?P<title>.+?)\*\*\s*\(\s*\[Link\]\((?P<url>https?://[^\s)]+)\)\s*\)') #links
        hits = re.findall(link_pat, analysis)
        for hit in hits:
            title = hit[0]
            link = hit[1]
            if link and not self.verify_link(link):
                # Search for the article using GPT
                new_link = self.search_article_via_gpt(title, link)

                if new_link and self.verify_link(new_link):
                    print(f"✓ found working link for {title}")
                    print(f"Replaced link for {title}")
                    # Replace old broken link with new one
                    analysis = analysis.replace(link, new_link)
                else:
                    print(f"link not found for '{title}'...")
        
        return analysis
            

    def detect_technical_terms(self, analysis: str) -> dict:
        find_terms_prompt = f"""I need you to read this following report on daily news, and identify every technical terms that 
                            someone that just got into the industry will find confusing. Then list them along side their definition in
                            this exact format:
                            term : short one line definition
                            Example:
                            instead of '1. CSSC: China State Shipbuilding Corporation' or '- CSSC: China State Shipbuilding Corporation', do 'CSSC:China State Shipbuilding Corporation'
                            Here's your report:
                            {analysis}
                            Note: do not include line numbers, and do not include overly simple words like "risks"
                            """
        try:
            response = self.openai_client.chat.completions.create(
                model = "gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an expert finance instructor. Read the user-supplied TMT report, "
                    "find every technical finance, M&A, or market term that a newcomer might "
                    "not understand, and output them as one term per line in the exact format "},
                    {'role': 'user', 'content': find_terms_prompt}
                ],
                temperature=0.2
            )
        except Exception as e:
            raise e
        
        #parse raw glossary from gpt3.5 and put them into glossary dictionary
        raw_glossary = response.choices[0].message.content
        glossary = {}
        for line in raw_glossary.splitlines():
            if ":" not in line:
                continue
            term, definition = line.split(": ", 1)
            if term and definition:
                term: str = term.strip().lower()
                definition: str = definition.strip().lower()
                print(f"{term} : {definition}")
                glossary[term] = definition
        #print(f"terms gathered today: \n{glossary}")

        #get the dictionary from json file, put it into master_terms dict
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    print("\n\nFound JSON dictionary")
                    master_terms = json.load(f)
            except json.JSONDecodeError:
                print("Failed to get JSON dictionary")
                master_terms = {}
        else:
            print(f"Error: JSON file doesn't exist in path {json_path.resolve()}")
            master_terms = {}

        #merge the glossary from gpt3.5 with master dict and write it back
        print("Merging and writing updated glossary...")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(master_terms, f, indent=2, ensure_ascii=False)
        print(f"✓ Glossary written successfully")

        return glossary

    
    def list_past_briefs(self):
        """List all past briefs"""
        try:
            briefs = []
            if os.path.exists(self.briefs_dir):
                for file in os.listdir(self.briefs_dir):
                    if file.startswith('brief_') and file.endswith('.pdf'):
                        briefs.append(file)
            return sorted(briefs, reverse=True)
        except Exception as e:
            print(f"Error listing briefs: {str(e)}")
            return []

    def generate_TLDR(self, analysis, sector, region):
            user_message = f"""
                Please take the following analysis on the {region} {sector} market and produce a 30 second TL;DR (it means the summary should be covered within 30 seconds by normal talking speed), followed by a 1 minute TL;DR, and followed by a 2 minutes TL;DR. You should briefly summarize the deal and/or big events happened, list out valuation multiples, and give a simple explanation on the implications
                ============================================================
                Formatting guidelines:
                Use ### as start of sections
                Use #### as start of subsections
                Use **title:** as start of subsections
                Use - ** as bullet points
                Use @@@ to bold a line

                IMPORTANT!
                USE ONLY ONE FORMATTING PATTING PER LINE AND ONLY USE AT THE START OF A LINE!
                =============================================================
                Example:

                ### 1. 30-Second TL;DR
                - BGC Group acquired Macro Hive to enhance its trading capabilities, integrating AI-driven analytics.
                - MOG Digitech invested in Luckyins Technology to boost its insurtech offerings with AI and blockchain.
                - The TMT sector shows cautious optimism, with an average EV/EBITDA multiple of 15.5x, driven by
                tech advancements but tempered by regulatory scrutiny and economic uncertainties.
                ### 2. 1-Minute TL;DR
                - BGC Group's acquisition of Macro Hive aims to strengthen its technology-driven trading strategy,
                although specific financials remain undisclosed.
                - MOG Digitech's strategic investment in Luckyins Technology focuses on enhancing insurtech
                capabilities through AI and blockchain.
                - The TMT sector is characterized by cautious optimism, with an average EV/EBITDA multiple of 15.5x
                across subsectors. High-growth areas like software and AI command premiums, while traditional
                sectors like telecom and media trade lower due to slower growth.
                - Market dynamics are influenced by technological advancements, regulatory scrutiny, and economic
                uncertainties, shaping future M&A activities.
                ### 3. 2-Minute TL;DR
                - BGC Group's recent acquisition of Macro Hive, a provider of macro market analytics, is part of its
                strategy to enhance technology-driven trading solutions, particularly in Rates and FX markets. The deal
                size is undisclosed, and while the valuation multiples are not available, the integration of AI analytics is
                expected to improve trading volumes and margins. Risks include potential integration challenges and
                reliance on market volatility.
                - MOG Digitech's strategic investment in Luckyins Technology aims to leverage AI and blockchain to
                optimize insurance processes, although specific financial details are not disclosed. This investment
                positions MOG as a leader in the evolving insurtech landscape.
                - The TMT sector is navigating a landscape of cautious optimism, with an average EV/EBITDA multiple
                of 15.5x. High-growth sectors like software (20.3x) and AI (22.5x) are attracting investor interest, while
                traditional sectors like telecom (9.8x) and media (12.1x) face challenges due to slower growth.
                - Key market drivers include technological advancements and robust investment in tech and fintech,
                while headwinds consist of regulatory scrutiny and economic uncertainties. Analysts predict continued
                consolidation in the secto
                ============================================================
                Here's your analysis to summarize 
                {analysis}
            """

            messages = [{"role": "user", "content": user_message}]

            response = self.openai_client.chat.completions.create(
                        model = "gpt-4o-mini",
                        messages = messages,
                        temperature=0.2
                    ).choices[0].message.content
            
            return response 
        
def clean_term(raw: str) -> str:
    # extra_chars covers common bullet / dash characters that aren't in string.punctuation
    extra_chars = "•–—-"          # U+2022 bullet, en-dash, em-dash, plain dash
    return raw.lstrip(string.whitespace + string.punctuation + extra_chars)






    
