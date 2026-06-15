"""
BambooHR — public job widget API per company.
GET https://{slug}.bamboohr.com/jobs/embed2.php  → HTML listing
GET https://{slug}.bamboohr.com/careers/{id}/detail → JSON (date, location, description)

No auth required. 400+ companies from kalil0321/ats-scrapers.
"""
import httpx
import asyncio
from bs4 import BeautifulSoup
from scrapers.base import JobData, detect_country, is_relevant_title, is_recent

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/json",
}
_SEM = asyncio.Semaphore(30)

COMPANIES = [
    "10web","1global","37signals","abcellera","acceldata","acommerce","actian","adapt",
    "adcouncil","aerospike","affinity","aircall","airtrunk","airwallex","alan","alector",
    "algolia","alltrails","alma","alpaca","altanaai","amagi","ambergroup","andesite",
    "antares","anyvan","appnovation","appviewx","aquant","arc","archlynk","armada",
    "artelia","ascendanalytics","aspectbiosystems","astra","ati","atomic","attune",
    "audinate","augmenta","avertium","awin","axiom","axios","azul",
    "banyansoftware","barkley","base","beam","behavox","bestow","beyondidentity",
    "bitgo","bitly","blacklane","blanclabs","blankstreet","blockstream","bloomreach",
    "botpress","boulevard","brainco","brainpop","branch","brevo","brightai",
    "brightmachines","brinqa","britecore","captivateiq","caribou","capco","capintel",
    "caseware","chief","cin7","clarityai","clear","clearcapital","clickhouse",
    "cloudtalk","coast","cobot","codasip","cognigy","cohere","coinmarketcap","color",
    "conduit","consensus","creatoriq","crexi","cribl","curai","cyara","cyware",
    "dashlane","datacamp","datacor","datatonic","deepgram","deepintent","delterra",
    "dept","devrev","dfinity","digitalfish","distilled","dlocal","docker",
    "domaintools","donorbox","dreamdata","dscout","dubber","duckduckgo","dune",
    "easyship","edpuzzle","educative","elasticstage","emburse","enable",
    "energyaspects","enhesa","enveritas","episodesix","equalexperts","equativ",
    "etg","everflow","exa","fabledata","famoco","fauna","figure","financeit",
    "firstcircle","firstintuition","fleetio","flipdish","flutterflow","formenergy",
    "fortanix","forterra","forward","fourhands","freetrade","freshprints","freshworks",
    "fundraiseup","g2","gausslabs","gbg","generalcatalyst","genesis","getbits",
    "getmidas","givedirectly","goatgroup","goglobal","goodnotes","gravisrobotics",
    "graylog","grayscale","grover","hackerrank","halter","headway","helloheart",
    "helpscout","hive","holocene","hometogo","hopper","hourly","hubble","hudabeauty",
    "hypebeast","immutable","impact","indebted","indexventures","influxdata",
    "infosum","instabase","instead","integra","integral","intuitive","ion",
    "janeasystems","january","jobandtalent","journey","junglescout","juvare",
    "karat","kasada","keboola","kindred","kinetic","klearnow","knowde","knownwell",
    "koala","kobiton","koho","kpler","kroll","kuda","labelyourdata","lakesidesoftware",
    "landytech","later","leadbank","learnupon","lendable","level","levitate","liberis",
    "linear","liveperson","loopio","lucidlink","mailerlite","mainstay","malt",
    "marqvision","masterclass","measured","mediavine","medium","memx","menlosecurity",
    "merge","metalab","metalenz","mettel","mirakl","mochihealth","modifi","moneysmart",
    "moniepoint","moo","moodle","morningbrew","mosaic","mozilla","muckrack",
    "musixmatch","muttdata","nansen","natech","natilik","nayya","nearmap","neo4j",
    "netlify","nexthink","ninjatrader","nitor","noodle","novibet","novo",
    "nozominetworks","nuclera","nucleus","oci","ocorian","offchainlabs","ogury",
    "optoinvest","opusclip","oracle","orchard","orgvue","osaro","outdoorsy",
    "outschool","overstory","pacvue","pagaya","palantir","papa","parallel",
    "patsnap","paystack","paytm","pdtpartners","peopleai","peoplecert","persado",
    "philo","pipedrive","pivotal","planetlabs","posthog","praxent","prestolabs",
    "procogia","procurify","prodigyeducation","promise","promiserobotics","provectus",
    "proxymity","ptc","pushsecurity","pythian","qctrl","radar","radformation",
    "rapdev","rapidai","rapidsos","randstad","recargapay","recordpoint","recurly",
    "relay","reltio","rendernetworks","rescale","residenthome","rightformula","rivr",
    "rokt","rystadenergy","saasgroup","sambatv","samsungnext","sana","sandbox",
    "sandboxvr","santex","sapiosciences","saucelabs","scality","searchstax",
    "securecodewarrior","securitize","seerinteractive","semaphore","semperis",
    "sentra","sequence","sessionai","signal","simpplr","sitetracker","skymavis",
    "skydance","smallpdf","smarsh","smartbear","smartnews","solace","sona",
    "sorare","source","sparkland","spin","splashfinancial","spotter","squiz",
    "stackline","starrez","storehub","stream","striveworks","subsplash","suki",
    "sundrivesolar","synthesia","tagboard","tailscale","tala","talonone","tandem",
    "tango","taskforce","tavily","teikametrics","tempo","tines","titancloud",
    "tombras","treasuryprime","treatwell","trellis","tresata","trevipay","trulioo",
    "trustwallet","trustly","truveta","tula","turvo","twelvelabs","twingate",
    "udacity","upguard","userlane","valneva","valtech","vayyar","vellum",
    "veracross","vercel","versaterm","vertigis","verto","vevo","vgw","vida",
    "vivun","voodoo","vulcanforms","waabi","wattpad","wearebulletproof","wellspring",
    "wheel","whiteswandata","worthai","wrapbook","xtm","yapily","yousician",
    "zerofox","zipdev","zushealth","zyte",
]


async def _fetch_company(client: httpx.AsyncClient, slug: str) -> list[dict]:
    async with _SEM:
        try:
            import re as _re
            # 1. Widget HTML — get all job titles + IDs
            resp = await client.get(f"https://{slug}.bamboohr.com/jobs/embed2.php")
            if resp.status_code in (404, 403, 410, 301, 302):
                return []
            if len(resp.content) < 300:  # empty widget
                return []

            soup = BeautifulSoup(resp.text, "lxml")

            # Extract real company name from page title "Jobs at Company Name | BambooHR"
            company_name = slug.replace("-", " ").title()
            title_tag = soup.find("title")
            if title_tag and title_tag.string:
                m = _re.search(r"Jobs at (.+?)(?:\s*\||\s*$)", title_tag.string, _re.IGNORECASE)
                if m:
                    company_name = m.group(1).strip()

            job_links = soup.select("a[href*='/careers/']")

            candidates = []
            for a in job_links:
                title = a.get_text(strip=True)
                if not is_relevant_title(title):
                    continue
                href = a.get("href", "")
                # extract job ID from href like /careers/1234/detail or ?id=1234
                import re
                m = re.search(r"/careers/(\d+)", href) or re.search(r"id=(\d+)", href)
                if m:
                    candidates.append((title, m.group(1)))

            if not candidates:
                return []

            jobs = []
            for title, job_id in candidates:
                try:
                    det = await client.get(
                        f"https://{slug}.bamboohr.com/careers/{job_id}/detail"
                    )
                    if det.status_code != 200:
                        continue
                    data = det.json()
                    result = data.get("result", {}).get("jobOpening", {})

                    posted = result.get("datePosted", "")
                    if not is_recent(posted):
                        continue

                    loc_obj = result.get("location", {})
                    city    = loc_obj.get("city", "")
                    state   = loc_obj.get("state", "")
                    country_raw = loc_obj.get("addressCountry", "")
                    location = ", ".join(filter(None, [city, state, country_raw]))

                    loc_type = str(result.get("locationType", ""))
                    is_remote = loc_type in ("2", "remote") or "remote" in location.lower()

                    country = detect_country(location, default="USA" if (is_remote or not location) else "")
                    if country not in ("USA", "India", "Remote"):
                        continue

                    desc_html = result.get("description", "")
                    desc = BeautifulSoup(desc_html, "lxml").get_text(separator="\n", strip=True) if desc_html else ""

                    job_url = f"https://{slug}.bamboohr.com/careers/{job_id}"
                    jobs.append(JobData(
                        title=title,
                        company=company_name,
                        url=job_url,
                        source="BambooHR",
                        description=desc[:3000],
                        location=location,
                        country=country,
                        salary=result.get("compensation", ""),
                        remote=is_remote,
                        posted_at=posted,
                    ).to_dict())
                except Exception:
                    continue

            return jobs
        except Exception:
            return []


async def fetch(settings: dict) -> list[dict]:
    async with httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=True) as client:
        tasks = [_fetch_company(client, slug) for slug in COMPANIES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    jobs: list[dict] = []
    seen: set[str] = set()
    for batch in results:
        if isinstance(batch, Exception):
            continue
        for j in batch:
            url = j.get("url", "")
            if url and url not in seen:
                seen.add(url)
                jobs.append(j)

    print(f"[BambooHR] {len(jobs)} jobs from {len(COMPANIES)} companies")
    return jobs
