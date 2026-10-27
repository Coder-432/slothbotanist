# SlothBotanist
SlothBotanist, an AI-powered herbal drink maker that transforms the ingredients you already have into two distinct drink creations(Heritage Elixir and Modern Refresh).

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![SerpApi](https://img.shields.io/badge/SerpApi-008080?style=for-the-badge&logo=google&logoColor=white)
![Qwen](https://img.shields.io/badge/Qwen_2.5--1.5B-615eff?style=for-the-badge&logo=huggingface&logoColor=white)
![Transformers](https://img.shields.io/badge/HF_Transformers-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black)
![HTML/CSS/JS](https://img.shields.io/badge/HTML5_/_CSS3_/_JS-E34F26?style=for-the-badge&logo=html5&logoColor=white)
![pip](https://img.shields.io/badge/pip_26.x-3776AB?style=for-the-badge&logo=pypi&logoColor=white)
![Unit Testing](https://img.shields.io/badge/Python_unittests-brightgreen?style=for-the-badge&logo=python&logoColor=white)

## What is SlothBotanist?
SlothBotanist, an AI-powered herbal drink maker that transforms the ingredients you already have into two distinct drink creations.

**1. Heritage Elixir**
_For the traditional soul._
This option focuses on traditional-inspired preparations, such as infusions and slow decoctions. It explores how everyday ingredients can become comforting herbal drinks.

**2. Modern Refresh**
_For the experimental soul._
This option explores contemporary preparations, including cold brews, infused water, and smoothies.
Both options start with the same pantry but approach it differently.
The goal is to help users discover new combinations without turning every drink into a shopping list.

## Key Features
**1. Multi-Engine Recipe Generation:** Input your drink goal, shelf ingredients, and allergies to get two distinct drinks (Heritage Elixir and Modern Refresh) created by a local LLM powered by 10 parallel SerpApi search engines. Includes one-click Copy and Print.
**2.Complete Recipe Intelligence:** View allergen exclusions, safety cautions, seasonal interest peak charts, picture links, research notes, and a live "Search Crew" dashboard showing the status of all 10 engines.
**3.Visual Identification:** Upload a photo or paste an image link to identify unknown herbs using Google Lens (SerpApi). Pick from top matches and click Add to my shelf directly from an editable input box.
**4.Distraction-Free Reader:** Paste any recipe or web article link to strip out ads and clutter, leaving only clean plain text via SerpApi’s Extract API.
**5.Location Search & Privacy Control:** Search your city to auto-set local country, language, and Google domain parameters. Features a 2-click browser reset button. All user data (shelf, allergies, location) is kept 100% private in local browser storage.

## Navigation & App Architecture
**1. Brew It (Main Page):** Input drink goals, available ingredients, and allergies to generate two customized recipes—a traditional Heritage Elixir and a modern Modern Refresh (with Copy/Print actions). Runs 10 SerpApi search engines in parallel for the local LLM to author recipes. Displays allergen exclusion notes, safety cautions, seasonal trend charts, source notes, image links, and a "Search Crew" engine status dashboard.

<img width="1910" height="947" alt="Screenshot 2026-10-27 091826" src="https://github.com/user-attachments/assets/d2aec210-035f-4939-8a4d-67f8220f51c3" />

<img width="1906" height="937" alt="Screenshot 2026-10-27 091855" src="https://github.com/user-attachments/assets/20b1a56c-04fb-4ea3-97a5-fe7da1520623" />

<img width="1901" height="955" alt="Screenshot 2026-10-27 091959" src="https://github.com/user-attachments/assets/8551f5cb-0e29-466c-85fd-578dea49d209" />


**2. Identify:** Upload a photo or image URL to identify unknown botanicals via Google Lens (SerpApi). Handles single ("This looks like") or multiple candidate matches, with an editable box to instantly add items to your shelf.

<img width="1840" height="903" alt="Screenshot 2026-10-27 092149" src="https://github.com/user-attachments/assets/3349dea9-f30f-4b78-8574-08b0cc6712c2" />


**3. Pages:** Paste any recipe or article link to extract and read clean, clutter-free plain text using SerpApi’s Extract API.

<img width="1906" height="917" alt="Screenshot 2026-10-27 092418" src="https://github.com/user-attachments/assets/f0c398fe-02c2-4163-9431-6849b9d7c70f" />


**4. Ledger:** Real-time analytics dashboard tracking brews made, searches saved, unique listings, allergen-blocked recipes, and an engine query bar chart (hydrated live from saved search logs).

<img width="1896" height="897" alt="Screenshot 2026-10-27 092452" src="https://github.com/user-attachments/assets/9d5fc5a8-03a6-47cb-bf68-31fc526d1e38" />


**5. Settings:** Localize searches by selecting your city (auto-configures country, language, and Google domain) and manage local data via a two-click browser reset. All user inputs (shelf, allergies, location) are stored 100% locally in your browser for total privacy.

<img width="1897" height="915" alt="Screenshot 2026-10-27 093527" src="https://github.com/user-attachments/assets/59842bd3-7e48-4899-bf37-a10c056fcdc6" />


## 📁 Project Directory Structure

```
SlothBotanist/
├── main.py
├── apothecary_core.py
├── test_core.py
├── weekly_scan.py
├── eval_brews.py
├── requirements.txt
├── README.md
└── static/
    ├── index.html
    ├── style.css
    └── app.js

```

## Installation & Running Locally

**Clone the repository:**
```
git clone [https://github.com/your-username/SlothBotanist.git](https://github.com/your-username/SlothBotanist.git)

cd SlothBotanist
```

**- Install Dependencies:**

```
pip install -r requirements.txt
```

**- Set Your SerpApi Key:**

```
export SERPAPI_KEY="your_serpapi_key_here"
```

**- Start the FastAPI Backend:**

```
uvicorn main:app --reload
```

**- Access the Application:** 

```
http://localhost:8000.
```


**- Run Tests, Evaluations & Safety Scans:**
 
a. Unit & Integration Tests:

```
python test_core.py
```
b. Run Evaluation Suite:

```
python eval_brews.py
```
 c. Run Weekly Safety Watchlist Scan:

```
python weekly_scan.py
```


## System Architecture

```
+------------------------------------------------------------------+
|                       USER INTERFACE                             |
+------------------------------------------------------------------+
|  Pantry Ingredients | Drink Mood | Allergy Exclusions            |
|  Brew It | Identify | Pages | Ledger | Settings                  |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
|                       FASTAPI BACKEND                            |
+------------------------------------------------------------------+
|  Input Processing             |     Search Coordination          |
|  Allergy Filtering            |     Duplicate-Query Filtering    |
|  Drink Generation             |     Output Validation            |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
|                  SERPAPI INTEGRATION LAYER                       |
+------------------------------------------------------------------+
|  SEARCH ENGINES                                                  |
|  +------------------------------------------------------------+  |
|  | Google Search          | Recipes and preparation           |  |
|  | DuckDuckGo             | Ingredient discovery              |  |
|  | Google Scholar         | Academic and allergy research     |  |
|  | Google Books           | Traditional herbal sources        |  |
|  | Google Patents         | Extraction methods                |  |
|  | Google News            | Safety warnings and recalls       |  |
|  | YouTube                | Preparation demonstrations        |  |
|  | Google Trends Trending | Current trending topics           |  |
|  | Google Trends          | Search interest over 12 months    |  |
|  | Google Images          | Visual results for the UI         |  |
|  +------------------------------------------------------------+  |
|  ADDITIONAL APIS                                                 |
|  +------------------------------------------------------------+  |
|  | Google Lens            | Photo-based herb discovery        |  |
|  | Extract API            | Recipe-page content               |  |
|  | Search Archive API     | Previous results by search ID     |  |
|  | Locations API          | Supported search locations        |  |
|  | Account API            | Account usage information         |  |
|  +------------------------------------------------------------+  |
|  RELIABILITY                                                     |
|  +------------------------------------------------------------+  |
|  | Successful-search caching in .sloth_cache/                 |  |
|  | HTTP 401/429 handling and 10-second engine cooldown        |  |
|  | Cached-result fallback                                     |  |
|  | Retry without rejected _sasl / _saslop parameters          |  |
|  | SLOTH_OFFLINE=1 for cached research                        |  |
|  +------------------------------------------------------------+  |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
|                  SEARCH CONTEXT ASSEMBLY                         |
+------------------------------------------------------------------+
|  Search Results | Ingredient Information | Numbered Sources      |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
|                      LOCAL QWEN MODEL                            |
+------------------------------------------------------------------+
|  Model: Qwen/Qwen2.5-1.5B-Instruct                               |
|  Generates: Heritage Elixir + Modern Refresh                     |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
|                  APPLICATION VALIDATION                          |
+------------------------------------------------------------------+
|  Allergen Checks | Pantry Checks | Citation Validation           |
|  Regeneration or Withholding When Checks Fail                    |
+------------------------------------------------------------------+
                                |
                                v
+------------------------------------------------------------------+
|                       YOUR TWO BREWS                             |
+------------------------------------------------------------------+
|       HERITAGE ELIXIR         |         MODERN REFRESH           |
+------------------------------------------------------------------+
```

## Tech Stack

- **Backend:** Python, FastAPI
- **Search and ingredient discovery:** SerpApi
- **Open-weight AI:** Qwen/Qwen2.5-1.5B-Instruct
- **Model runtime:** Hugging Face Transformers
- **Frontend:** HTML, CSS and JavaScript
- **Package Management:** pip 26.x
- **Testing:** Python unit tests
- **Additional utilities:** evaluation suite(eval_brews.py) and weekly safety-Watchlist scanner(weekly_scan.py)

## SerpApi: The Secret Ingredient Behind Every Brew

<img width="766" height="400" alt="Serpapi" src="https://github.com/user-attachments/assets/1cdaa350-0873-4a09-88bd-522d18405bb6" />

In SlothBotanist, SerpApi is not an auxiliary add-on, a side widget, or a simple wrapper—it is the core architectural engine that powers the entire system. While standard applications rely on single-endpoint web lookups, SerpApi is Architectural Backbone of SlothBotanist.

#### Architectural Highlights:

- **High-Performance Concurrency & Ecosystem Workflows:** Search requests execute simultaneously using asyncio.gather while run_in_threadpool runs blocking SerpApi calls in worker threads to keep the main event loop unblocked. The 10 integrated engines are _Google Search (google), DuckDuckGo (duckduckgo), Google Scholar (google_scholar), Google Books (google_books), Google Patents (google_patents), Google News (google_news), YouTube (youtube), Google Trends Trending Now (google_trends_trending_now), Google Trends (google_trends), _and _Google Images (google_images)_. Beyond search, it incorporates _Google Lens (google_lens),Extract API (engine=extract), Search Archive API (search_metadata.id),_ Account API, and _Locations API (location, gl, hl, google_domain)_.
- **Dual-Format Intelligence Routing:** Prioritizes Books, Patents, and Scholar for traditional Heritage Elixirs, while routing Trends, YouTube, News, and Web Search for contemporary Modern Refreshes.
- **Allergy Safety Layer:** Automates _google_scholar_ botanical cross-reactivity checks (ragweed, birch, soy, tree nuts etc) and _google_news_ recall sweeps prior to recipe generation.
- **Trend & Seasonality Analysis:** Aggregates weekly interest data into monthly averages and peak demand months.
- **Data Normalization & Citation Integrity:** Request-scoped URL deduplication, isolates source registries per request, and strips hallucinated citations ([S99]) via _resolve_citations_.
- **Production Resilience & Offline Mode:** Features 401 key protection, 429 rate-limit cooldowns, parameter fallbacks, explicit no_cache / zero_trace flags, disk caching (.sloth_cache/), and zero-quota offline replay (SLOTH_OFFLINE=1).



## Why SlothBotanist?

| Dimension | Standard Botanical & Recipe Apps | **SlothBotanist** |
| :--- | :--- | :--- |
| **Search Coverage** | Basic single-source web search | **Multi-Source Discovery:** Cross-references search engines, scientific papers, historical books, patents, trend data, news, and video tutorials. |
| **User Privacy** | Query histories and personal searches saved on third-party servers | **Strict Privacy First:** Enforces privacy parameters to ensure query data isn't logged or persistent upstream. |
| **Recipe Customization** | Generic, one-size-fits-all recommendations | **Dual-Format Intelligence:** Tailors queries specifically for traditional heritage elixirs versus modern craft drinks. |
| **Safety & Verification** | Standard databases that miss recent recalls | **Real-Time Safety Checks:** Automatically scans current news for product recalls and checks medical literature for plant cross-reactivities. |
| **Seasonal Sourcing** | Static seasonal calendars | **Live Market Demand:** Tracks real-time interest shifts to identify peak seasonal availability for herbs and ingredients. |
| **Reliability** | Slow loading times or crashes when databases go down | **Always Available:** Runs searches seamlessly in parallel and includes built-in offline modes when connectivity is lost. |
| **Output Quality** | Made-up ingredients or broken source links | **Verified Information:** Filters out fake citations and cleans up web sources before generating recipes. |


## 🍵 Your Next Brew Awaits: Time to Take a Sip
Next time you look into your kitchen and see a wedge of lime, half a cucumber, or a pod of green cardamom, don't just reach for a plain mug of hot water.
Let the sloth do the heavy lifting. Discover what your pantry has been trying to tell you all along. Delightfully effortless—your next favorite elixir is already sitting on your counter.

_**"Pantry odds, perfect brews."⭐**_
_**"Slow down, brew up."✨**_

<img width="1408" height="768" alt="glasses" src="https://github.com/user-attachments/assets/8df4bfa1-63e9-40a0-898c-4e8579449b7b" />

> **📝 Note on Repository Updates:** 
> While the core project code, pipeline logic, and instrumentation were completed during the official Hacktoberfest challenge window, `README.md` was polished and structured later for enhanced clarity and ease of setup.





