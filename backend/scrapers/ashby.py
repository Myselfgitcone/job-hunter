"""
Ashby — public job board API per company.
POST api.ashbyhq.com/posting-api/job-board/{companySlug}
No auth required for public boards.

Company list sourced from jobseek (github.com/colophon-group/jobseek) — 855 companies.
"""
import httpx
import asyncio
from bs4 import BeautifulSoup
from scrapers.base import JobData, detect_country, CUTOFF_HOURS, is_relevant_title
from datetime import datetime, timezone, timedelta

BASE = "https://api.ashbyhq.com/posting-api/job-board/{company}"

COMPANIES = [
    "0x", "1mind", "1password", "30mpc", "8fleet-inc", "9-mothers", "Abridge", "Astro-Mechanica",
    "Flock%20Safety", "Hippocratic%20AI", "Jasper%20AI", "Linkup", "Nash", "NorthwoodSpace", "Solana%20Foundation", "Talos-Trading",
    "Tools%20for%20Humanity", "Valon", "a-team", "abacum", "abound", "academia", "accord", "acorns",
    "acquisition", "adapt", "adaption", "adaptive", "adaptivesecurity", "addi", "adonis", "aerovect",
    "agent", "aim", "aios", "airbyte", "airgarage", "airnxt", "airspace-intelligence.com", "aisle",
    "ajax", "akasa", "alan", "alembic", "aleph", "algo1", "allarahealth", "allium",
    "alloyenterprises", "allspice", "alpenlabs", "amber", "ambiencehealthcare", "ambient.ai", "amca", "american-housing",
    "ami", "amo", "amperos", "anagram", "andela", "anima", "anon", "anrok",
    "antithesis", "anyscale", "apex-technology-inc", "aplazo", "applied", "appliedlabs", "apron", "arb-interactive",
    "arbor", "arcade", "arch.co", "architect", "arena", "arenanet", "artie", "artisan",
    "artsy", "ashby", "aspora", "assembly", "astra", "astronomer", "ataraxis-ai", "atlan",
    "atlas", "atticus", "attio", "auditless", "august-health", "aureliussystems", "aurorasolar", "avala",
    "aven", "avid4", "avra", "away", "axiom", "axiom-co", "axle-careers", "azuki",
    "backflip", "backmarket", "barkbus", "base", "base-power", "baseten", "bastion", "beam-up",
    "beamery", "bedrock", "bedrock-robotics", "belvo", "benchling", "bestow", "betterup", "billups",
    "binance.us", "bio", "blink", "bliro", "block-labs", "blockdaemon", "blockit", "blockworks",
    "blue-energy", "blueberrypediatrics", "bluedot", "boom", "bounce", "brainco", "braintrust", "branchinsurance",
    "bravehealth", "brigit", "browserbase", "bubble", "bug-bounty-switzerland", "build", "built-robotics", "camber",
    "cambly", "campfire", "canals", "cantina", "cape", "capsule", "caribou", "category-labs",
    "cedar", "chaidiscovery", "change", "character", "charge-robotics", "checkly", "chestnut", "chief",
    "chromatic", "circuithub", "clarity", "clarium", "classdojo", "cleric", "clerk", "clickup",
    "close", "cloudtrucks", "clove", "clubhouse", "coalesce", "cobot", "codat", "coder",
    "cognition", "cohere", "cohort", "cointracker", "collective", "colonist", "column", "comity",
    "commonroom", "compound", "comulate", "conductor", "conductorai", "conduit", "confluent", "console",
    "continue", "conversion", "convex-dev", "coreflow", "cosmos", "cosuno", "counsel", "coverdash",
    "cradlebio", "craftdocs", "creditgenie", "crisp", "cruxclimate", "cryptio", "cube", "cubesoftware",
    "cubist", "cursor", "cyberhaven", "cybret", "d-matrix", "dandelion", "dash0", "datologyai",
    "dave", "decagon", "decimal", "deel", "deepgram", "deepjudge", "deepnote", "delinea",
    "deliveroo", "delphi", "demandbase", "dialogueai", "dispatch", "docker", "docplanner", "doctoralia-brasil",
    "doctoralia-colombia", "doctoralia-mexico", "doctoralia-spain", "doktortakvimi", "domestika.org", "doss", "double", "dovetail",
    "drata", "dryft", "duck-duck-go", "dune", "dusk", "dust", "dyna-robotics", "e2b",
    "echo", "eigen-labs", "electronx", "elevenlabs", "ellipsislabs", "empirical", "envoy", "espresso",
    "ethereum-foundation", "ethyca", "evervault", "every-io", "evolve", "exa", "extend", "f2-ai",
    "fable", "fabrion", "fanvue.com", "far.ai", "fastino-ai", "fathom.video", "filmhub", "fin",
    "firecrawl", "firetiger", "flaglerhealth", "fleek", "fleetworks", "flint", "float", "flora",
    "flutterflow", "flux", "focus", "folio", "forerunner", "forge", "forma", "formance",
    "formenergy", "forto", "forum-ventures", "foundry-robotics", "foursquare", "foxglove", "freed", "freeplay",
    "freetrade", "freewill", "freshpaint", "frontcareers", "fullstory", "furtherai", "fuse", "gamma",
    "gecko-robotics", "gelato", "genesis-molecular-ai", "genies", "genomics", "genpeach", "gitbook", "glide",
    "glimpse", "golinks", "gooddata", "goody", "gorgias", "govsignals", "gptzero", "grand",
    "graphite", "gravityclimate", "graymatter-robotics", "greatquestion", "grepr", "greptile", "griffin", "guild",
    "h3x-technologies", "haast", "hackerone", "hang", "happyrobot.ai", "harmattan-ai", "harmonic", "harrison.ai",
    "harvey", "hatch", "hawk", "haystacknews", "hcompany", "hedra", "heron-power", "higgsfieldai",
    "hiive", "hike-medical", "hivemq", "hiya", "homebase", "homevision", "hook", "hookmusic",
    "hopper", "httpie", "hubstaff", "humaans", "hyperbolic", "hyperexponential", "ideogram", "illumio",
    "immersivelabs", "imprint", "improbable", "incident", "indent", "inductive-bio", "infinity-constellation", "infisical",
    "influxdata", "inngest", "insitro", "inspiration-commerce-group", "instructure", "interplay", "intro", "intus",
    "invert", "inworld-ai", "jameda", "january", "jbs-dev", "jellyfish", "jellyfishcareers", "jobber",
    "jua", "juicebox", "julius", "jump", "jump-app", "kaizenlabs", "kalshi", "kayak",
    "kernel", "kestra", "keycard-labs", "keystone", "kilocode", "kin", "kindred", "kira",
    "kit", "kittl", "knoetic", "knot", "knowlix", "known", "kombo", "kong",
    "kraken.com", "krea", "kustomer", "lakera.ai", "lambda", "lancedb", "langchain", "langdock",
    "langfuse", "lassie", "laurel", "lavendo", "lawdepot", "layerfi", "leap", "leapsome",
    "ledger", "legionhealth", "lemlist", "lemonade", "lens", "leona", "letta", "level",
    "li.fi", "light", "lightdash", "lightning", "lightspark", "lightspeedhq", "lindushealth", "linear",
    "lio", "liquid-ai", "litmus", "livekit", "llamaindex", "lorikeet", "lottie", "lumana",
    "lunar", "luxor", "magiceden", "mainstay", "maple", "marianaminerals", "marshmallow", "materialsecurity",
    "mechanize", "medal", "medely", "megazone", "melotech", "mem", "mend-io", "meridian",
    "meshy", "method", "method.security", "meticulous", "midstream", "mindrobotics", "mintlify", "miodottore",
    "mirage", "miso", "mithrl", "modal", "moderntreasury", "molg", "mollie", "moment",
    "monad.foundation", "monumental", "morse-micro", "mosaic", "motherduck", "motion", "multiply", "mural",
    "mux", "mydr", "mystenlabs", "myvillage", "n1", "nabla", "namespace", "neon",
    "neon-health", "nerdwallet", "netwealth", "neuralconcept", "newfront", "nivoda", "noise-labs", "nomad",
    "norm-ai", "notabene", "notable", "notion", "noto", "novel", "novo", "numeral",
    "oboe", "obviant", "odyssey", "office-hours", "omniscient", "onecrew", "oneleet", "onoshealth",
    "ontic", "ontra", "opal", "openai", "opengov", "openrouter", "opensea", "oplabs",
    "orb", "orbital", "orca", "orchard", "oscilar", "osmo", "oso", "output",
    "outtake", "oxio", "oyster", "p2p.org", "paddle", "palmstreet", "panoptyc", "parabola-io",
    "paradigm", "parafin", "paragon", "pareto-ai", "parity", "parker", "partiful", "passage",
    "patch.io", "patreon", "pax-historia", "paxos", "paxoslabs", "pearl", "pearlhealth", "peec",
    "pennylane", "percepta", "periodic-labs", "perk", "perplexity", "persona", "phantom", "phoebe-work",
    "phylo", "physicalintelligence", "pika", "pinecone", "pivot", "plaid", "plain", "plane",
    "playground", "plinth", "plot", "pluralfinance", "pocus", "pod-network", "point-one-navigation", "polar",
    "polygon-labs", "polymarket", "poolside", "popl", "posh", "poshmark", "post", "posthog",
    "posting-api", "prefect", "prelude", "preply", "primary", "prime", "primeintellect", "primer",
    "prior-labs", "procurify", "project-expedition", "prompt", "proofofplay", "propel", "protege", "pryzm",
    "psi", "pulse", "pure", "pylon", "qualified", "quantum", "quicknode", "quora",
    "radai", "radar", "radiant-industries", "railway", "ramp", "range", "rasa", "read-ai",
    "real", "recraft", "redis", "reflect-orbital", "reflectionai", "reframesystems", "relay", "render",
    "replit", "replo", "resend", "rev", "revenuecat", "rho", "rillet", "root-access",
    "ropes", "rula", "runetech", "runway-ml", "rwa.xyz", "sable", "safe", "salient",
    "sanity", "sardine", "saturn", "savvy", "scaled-cognition", "scalemath", "sciforium", "scribe",
    "se3", "secfix", "sei-labs", "semgrep", "sentilink", "sentry", "sequence", "sequoia",
    "sesame", "sfcompute", "shift", "shiftsmart", "sieve", "sift", "signoz", "simpleclosure",
    "singular", "siteminder", "skyflow", "skymavis", "slash-financial", "slate", "sleeper", "snappy",
    "socket", "socure", "sola", "solink", "sona", "sosafe", "source-multiplier", "spacial",
    "span", "spare", "speakeasy", "spector-ai", "spekit", "sphinx", "spotlight", "sprig",
    "sprinter-health", "spruceid", "squint.ai", "stable", "stainlessapi", "standardfleet", "starbridge", "statsig",
    "stayai", "stedi", "stellar", "strava", "stream", "stronghold", "stuut-ai", "stytch",
    "substack", "suno", "sunrise", "supabase", "super.com", "supercell", "superhuman", "svix",
    "swan", "sweep", "sylvera", "syndica", "synthesia", "synthflow", "tacto", "tailwind",
    "tako", "talentful", "talkiatry", "tandem", "tapblaze", "tavus", "techtorch", "tekion",
    "tem", "tempo", "tenex", "tenjin", "tennr", "tensorwave", "terraai", "terranova",
    "thatgamecompany", "the-flex", "theydo", "thinkific", "thndr", "thought-machine", "threataware", "thumbtack",
    "tiger", "tight", "tilt", "tilthq", "titan", "titan-ai", "tonal", "traba",
    "tracebit", "tracelabs", "trading212", "trainline", "traversal", "trucksmarter", "trulioo", "trust-wallet",
    "tuotempo", "turnkey", "turquoise-health", "twelve", "twenty", "two-dots", "uberall", "uipath",
    "ultra", "uncountable", "unify", "union", "uniswap", "unit", "unlikelyai", "unto-labs",
    "unwrap", "upflow", "upside", "upvest", "v7labs.com", "valon", "valonvm", "vanilla",
    "vanta", "vantage", "vapi", "vcluster", "vector", "vetcove", "vibe", "virtahealth",
    "vitalize", "voladynamics", "voldex", "vorto", "vow", "vultr", "walrusfi", "warp",
    "watershed", "wayflyer", "webai", "weekend", "what3words", "whatnot", "wheel", "whitecircle",
    "whoop", "windmill", "windranger", "wirescreen", "withclutch", "withdaydream", "woflow", "wordware.ai",
    "workos", "world-foundation", "worldly", "wrapbook", "writer", "xbowcareers", "xdof", "xenon",
    "xero", "ycombinator", "yepoda", "yondr", "zapier", "zayzoon", "zed", "zello",
    "zero", "zeromark", "zettabyte-space", "zip", "znanyLekarz",
    # ── Additional high-value Data Engineering employers ───────────────────
    # Cloud / Data Infra
    "astronomer", "hex", "metaplane", "recurrency", "sdf-labs",
    "paradime", "lightdash", "evidence-dev", "y42", "datacoves",
    "siffletdata", "acceldata", "datafold", "piperider",
    "cloudquery", "databand", "obsrvbl", "anomalo",
    # AI / ML platforms
    "weights-and-biases", "determined-ai", "anyscale",
    "together-ai", "replicate", "modal-labs", "baseten",
    "lightning-ai", "lambdalabs", "scale-ai", "humanloop",
    "cohere", "ai21labs", "mistral-ai", "aleph-alpha",
    # Fintech / Payments
    "ramp", "brex", "rippling", "gusto", "deel",
    "remote-com", "oyster-hr", "papaya-global",
    "addepar", "altruist", "apex-fintech",
    # Consumer / Marketplace
    "faire", "whatnot", "patreon", "substack",
    "cameo", "masterclass", "brilliant-org",
    # Data / Analytics SaaS
    "sigma-computing", "mode-analytics", "atscale",
    "dremio", "kyligence", "incorta", "yellowbrick",
    "rockset", "firebolt", "materialize", "eventstore",
    # Indian IT
    "mindtree", "birlasoft", "nttdata-india", "cgi-india",
]

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_SEM = asyncio.Semaphore(50)


def _is_recent(date_str: str) -> bool:
    if not date_str:
        return True
    try:
        # Date-only strings (e.g. "2026-05-10") — treat as end of day to avoid
        # cutting off jobs posted early that day
        if "T" not in date_str and len(date_str) == 10:
            date_str = date_str + "T23:59:59+00:00"
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= datetime.now(timezone.utc) - timedelta(hours=CUTOFF_HOURS)
    except Exception:
        return True


_ASHBY_DEBUG_DONE = False

async def _fetch_company(client: httpx.AsyncClient, company: str) -> list[dict]:
    global _ASHBY_DEBUG_DONE
    async with _SEM:
        try:
            url = BASE.format(company=company)
            resp = await client.get(url)
            if resp.status_code in (404, 403, 410):
                return []
            resp.raise_for_status()
            data = resp.json()

            # One-shot debug for first company with postings
            if not _ASHBY_DEBUG_DONE and data.get("jobPostings"):
                _ASHBY_DEBUG_DONE = True
                sample = data["jobPostings"][0]
                print(f"[Ashby DEBUG] company={company} keys={list(sample.keys())}")
                print(f"[Ashby DEBUG] sample title={sample.get('title')} date={sample.get('publishedDate')} loc={sample.get('locationName')} remote={sample.get('isRemote')}")

            jobs = []
            for item in data.get("jobPostings") or data.get("jobs", []):
                title = item.get("title", "")
                if not is_relevant_title(title):
                    continue

                published = item.get("publishedAt", "") or item.get("publishedDate", "")
                if not _is_recent(published):
                    continue

                job_url = item.get("jobUrl", "")
                if not job_url:
                    continue

                location  = item.get("location", "") or item.get("locationName", "") or ""
                is_remote = bool(item.get("isRemote", False)) or item.get("workplaceType", "") == "Remote"

                country = detect_country(location, default="USA" if (is_remote or not location) else "")
                if country not in ("USA", "India", "Remote"):
                    continue

                desc_html = item.get("descriptionHtml", "")
                desc = (
                    BeautifulSoup(desc_html, "lxml").get_text(separator="\n", strip=True)
                    if desc_html else ""
                )

                company_name = (
                    item.get("organizationName")
                    or company.replace("-", " ").title()
                )

                jobs.append(JobData(
                    title=title,
                    company=company_name,
                    url=job_url,
                    source="Ashby",
                    description=desc,
                    location=location,
                    country=country,
                    salary="",
                    remote=is_remote or "remote" in (title + location).lower(),
                    posted_at=published,
                ).to_dict())

            return jobs
        except Exception:
            return []


async def fetch(settings: dict) -> list[dict]:
    companies = settings.get("_ashby_slugs") or COMPANIES
    print(f"[Ashby] Scraping {len(companies)} companies…")
    sem = asyncio.Semaphore(30)

    async def _bounded(client, co):
        async with sem:
            return await _fetch_company(client, co)

    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        tasks = [_bounded(client, co) for co in companies]
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

    print(f"[Ashby] {len(jobs)} jobs from {len(companies)} companies")
    return jobs

