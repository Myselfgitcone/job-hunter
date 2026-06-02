"""
Greenhouse — public board API per company.
boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true
No auth required for public boards.

Company list sourced from jobseek (github.com/colophon-group/jobseek) — 2400+ boards.
"""
import httpx
import asyncio
from scrapers.base import JobData, detect_country, CUTOFF_HOURS
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

BASE = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"

BOARDS = [
    "10alabs", "10xgenomics", "12twenty", "1800contacts", "2k", "3cloud", "3redpartners", "66degrees",
    "6sense", "7shifts", "a16z", "a24", "abacusinsights", "abbyy", "abc", "abcellera",
    "abilitypath", "abinbev", "ably30", "abnormalsecurity", "absci", "acadiapharmaceuticals", "accela", "accelerationpartners",
    "accelschools", "accenturefederalservices", "accesshealthca", "accesso", "accrue", "accuweather", "acilearning", "aclu",
    "acluinternships", "aclunj", "acog", "acommerce", "acquia", "acrisureinnovation", "acryldata", "acumen",
    "acurussolutions", "ada18", "adahealth", "adamevenyc", "adcouncil", "addepar1", "adfinternational", "adswerveinc",
    "advancedspace", "adyen", "aechelontechnology", "aerospike", "aestudio", "aevexaerospace", "affinidi", "affinipay1",
    "affirm", "affirmedrxpbc", "afresh", "afscareersmarketplace", "agebold", "agecareers", "agencywithin", "agilisys",
    "agilityrobotics", "agoda", "agwestfarmcredit", "aiedu", "aift", "airia", "airship", "airspace",
    "airtable", "airtrunk", "aisquared", "aizerhealth", "akersystems", "akidolabs", "akko", "akuity",
    "akunacapital", "alamarbiosciences", "alarmcom", "albertmackenziellp", "alchemy", "alertmedia", "alexandralozanoimmigrationlawpllc", "algolia",
    "align", "alixpartners", "allcareers", "allencontrolsystems", "alliancedefendingfreedom", "allinc", "alloy", "allwebleads",
    "alma31", "aloyoga", "alpaca", "alphafmcroles", "alphagrepsecurities", "alphalion", "alphasense", "alphasenseindia",
    "alpineinternships", "alpineinvestors", "alt", "altanaai", "altentechnologyusa", "altium", "altoslabs", "altscore",
    "alu", "alumniventures", "alvys", "alxafrica", "amaehealth", "ambiententerprises", "amendconsulting", "amenitiz",
    "americaninstitute", "amoriabond", "amount", "amperity", "amplemarket", "amplitude", "ampsortation", "amwell",
    "anaplan", "anchanto", "andurilindustries", "angi", "angitiaincorporatedlimited", "animalmedicalcenter", "aninebing", "anodize",
    "ansa", "answerrocket", "antenna", "anteriad", "anthropic", "antora", "apaleo", "apartmentiq",
    "aperaaiinc", "aperiasolutions", "apiiro", "apiphani", "aplayers", "apollo", "apolloio", "appdirect",
    "appian", "appier", "appletreeprep", "appliedengineering", "appliedintuition", "applovin", "applytoaktos", "appnovation",
    "appodeal", "appomni", "appsflyer", "appspace", "apptronik", "appviewx", "aptoslabs", "aqr",
    "aquaticcapitalmanagement", "arcadiacareers", "arcanaanalytics", "arcboatcompany", "arceeai", "arcesiumllc", "archer56", "archera",
    "archrival", "arcinstitute", "arenanet", "arenaphysica", "arine", "arizeai", "arkestroinc", "arkoselabs",
    "arlosolutionsllc", "armada", "armissecurity", "arrayeducation", "artefact", "artefactjobs", "artisanpartners", "asana",
    "ascendanalytics", "asgjobs", "ashfieldadvisory", "asm", "aspectbiosystems", "assemblyai", "assetliving", "assetwatch",
    "assuredguaranty", "assystinc", "asteraearlycareer2026", "asteralabs", "astranis", "atbayjobs", "athinkingape", "athleticsbaseballops",
    "athleticsbusinessops", "atlasxhm", "atomiccartoons", "atomicwork", "atropos", "attain", "attainpartners", "attentive",
    "attivopartners", "atwellgroup", "auctane", "audaxgroup", "audibenehearcom", "augmentcomputing", "augury", "aurorainnovation",
    "aurosglobal", "auterion", "authenticbrandsgroup", "automatticcareers", "autoproff", "autoscout24", "autura", "avalabs",
    "avantium", "aviary", "aviatrix", "avidxchangeinc", "avride", "awin", "axicom", "axicorpfinancialservicesptyltd",
    "axiom", "axios", "axle", "axon", "axonius", "axontalentcommunity", "axs", "aypapower",
    "azuritypharmaceuticals", "azuritypharmaceuticalsindia", "b12", "babylist", "backblaze", "baidu", "bamboohr17", "bandainamco",
    "bandwidth", "banyansoftware", "bark", "barkley", "baroncapital", "basejobs", "baselayer", "bauerhockeycascademaveriklacrosse",
    "bayasystems", "bbposlimited", "bcscareers", "bdainc", "beaconbiosignals", "beaconsoftware", "beam", "beamtherapeutics",
    "beautifulai", "behavox", "benchmarkpt", "benchprep", "berlinbrands", "berlincity", "berlinpackaging", "berlinrosen",
    "bertramcapitalmanagement", "bestpass", "betsson", "betterhelp", "betterment", "bevicareers", "beyondfinance", "beyondtrust",
    "bgeinc", "bigid", "billcom", "billiontoone", "biograph", "biohub", "bird", "bishopfox",
    "bitcoindepot", "bitgo", "bitmex", "bitpanda", "bitso", "blackbirdhealth", "blackcanyonconsulting", "blackduck",
    "blackforestlabs", "blacklane", "blacksky", "blankstreet", "blastpoint", "blend", "blenheimchalcotindia", "blockchain",
    "bloomerang", "bloomreach", "bluecrestcapitalmanagement", "blueprintteach", "blueroseresearch", "blueskyinnovators", "blueskytelepsych", "bluevineindia",
    "bluevineus", "bluewaterthinking", "blusharkdigital", "blytheco", "bobbie", "bolcomen", "boldbusiness", "bombas",
    "bonfirestudios", "bonsbyhvacplumbing", "boomentertainment", "botauto", "bottomlinetechnologies", "bouldercare", "boulevard", "boxinc",
    "bpcs", "bracebridgecapital", "brainpop", "brainstation", "branch", "brandtechplus", "brave", "bravo",
    "braze", "breezeairways", "breezecash", "breezeway", "brennan", "brex", "bridgebio", "bridgewater89",
    "brightai", "brightcoreenergy", "brightflag", "brileysecurities", "bringg", "brinqa", "broadsign", "broadwayventures",
    "brooklinen", "brunswickgroup", "bswift", "bswiftindia", "btgpactual", "btig27", "bubbleskincare", "bugcrowd",
    "builder", "buildkite", "buildops", "builtin", "burnt", "butternutbox", "buyersedgeplatformrecruiting", "buynomics",
    "buzzfeed", "buzzsolutions", "bvnk", "bybit", "byd", "bythebayhealth", "c3iot", "c6bank",
    "cabify", "cabrillohospice", "caddellconstruction", "cadencesolutions", "cadwell", "cais", "calendly", "californiaacademyofsciences",
    "californiaautismcenter", "calm", "calyxo", "camp", "candidly", "cannabisandglass", "cannondesign", "canonical",
    "canopytax", "canto", "capco", "capintel", "capitalfarmcredit", "capitalontap", "capitalrx", "capitaltg",
    "capstonedc", "carbonchain", "carbondirect", "carbonfuture", "careaccess", "carecom", "caredxinc", "careem",
    "careerteam", "carefeed", "cargomatic", "cargurus", "cariadinc", "caribou", "carmichaellynch", "caronsale",
    "carrotfertility", "carta", "cartwheelcare", "casechek", "caseguard", "casetify", "castaigroupinc", "catenaclearing",
    "catonetworks", "cattaneozanetto", "caylent", "cbinsights", "cdpjobs", "ceg", "celigo", "celonis",
    "censys", "centerforemploymentopportunities", "centessapharmaceuticalsinc", "centralreach", "centrumhealth", "cerebrassystems", "ceribell", "cfoinsights",
    "chainguard", "chalkinc", "championsgroupholdings", "chanzuckerberginitiative", "chaosindustries", "chargepoint", "chariotdefense", "charlesriverassociates",
    "charterup", "chathamfinancial", "checkbook", "checkr", "chenmoore", "cherryventures", "chicagotrading", "chile",
    "chime", "chipcity", "chompscareers", "chowbus", "ciazumano", "circleci", "circleso", "cision",
    "citian", "citrushealthgroup", "cityoffortworth", "civilscience", "clara", "clariticloudinc", "clarityinnovates", "classpass",
    "clear", "clearscoretechnologylimited", "clearstreet", "clearviewhealthcarepartners", "clearwayjobs", "cleo", "cleoindia", "clerk-ai",
    "clevelandpreparatoryacademy", "clickhouse", "climatefinancesolutions", "climatex", "clinchoice", "cloudbeds", "cloudchamberfr", "cloudflare",
    "cloudsek", "cloverhealth", "clubmonaco", "clutch", "cmbluenergyag", "coalition", "coast", "cobaltio",
    "cobaltservicepartners", "cobblestoneenergy4", "cobre", "cockroachlabs", "codalinc", "code3", "codepath", "coefficient",
    "cofertility", "cofraholding", "cogstateinc", "coherehealth", "coinbase", "colabsoftware", "colemanresearch", "collibra",
    "comet", "commerceiq", "commercetools", "commonthreadcollective", "commvault", "compeerfinancial", "compliancygroupllc", "complyadvantage",
    "compunetinc", "computergeneratedsolutions", "comstock", "concentric", "conga", "connectedcannabis", "connectwise", "consensys",
    "constantcontact", "constructionresources", "constructortech", "consumeredge", "contentful", "contentstack", "contextualai", "convene",
    "convera", "cooksys", "cookunity", "copperco", "cordance", "corelight", "coreweave", "corpsyn",
    "cortex", "cortica", "corviascorporateservicesllc", "costar", "cotevegas", "cotullaeducation", "couchbaseinc", "counterpart",
    "coursera", "covar", "coverahealth", "cpm", "cranialtechnologies", "creativex", "crederacampusrecruiting", "credible",
    "creditkarma", "creditunionofcolorado", "crescolabs", "cresta", "crexi", "cribl", "crisprecruit", "criticalmass",
    "crometrics", "crossriverbank", "crunchyroll", "css", "cssmerge", "cti", "cultureamp", "curaleaf",
    "curicapital", "currenciesdirect", "current81", "customerio", "cvx", "cybereason", "cybersheath", "cybrid",
    "cyware", "d2consulting", "d2l", "d3", "dagsterlabs", "danieloconnellssons", "darkwolfsolutions", "dashlane",
    "databento", "datacamp", "datacor", "datadog", "dataiku", "datarails", "davidzwirnergallery", "davisdevelopment",
    "daylight", "daymarkhealth", "dbeconorthamerica", "dbtlabsinc", "ddome", "debtbook", "debutbiotech25", "decathlontechnology",
    "decimainternational", "deepintent", "defenseunicorns", "definitivehc", "degreed", "deliveryassociates", "dental365", "dept",
    "descript", "designedconveyorsystems", "detroitlions", "devrev", "devtechnology", "dexisconsultinggroup", "dhigroupinc", "dialecticch",
    "dialpad", "dianahealth94", "digible", "digrestaurants", "diligent", "diligentcorporation", "diligentrobotics", "disco",
    "discord", "distantjob", "divergent", "dkatalislabs", "dlhcorporation", "dlrgroup", "dmgevents", "doctolib",
    "doitintl", "domeconstruction", "dominodatalab", "donorbox", "doordashaustralia", "doordashcanada", "doordashindia", "doordashinternational",
    "doordashmexico", "doordashusa", "doppel", "dorsia", "dotccareers", "doubleverify", "doximity", "dragos",
    "drayerpt", "drdental", "dreemhealth", "drivewealth", "dropbox", "drsquatch", "druva", "drweng",
    "drwfr", "duckworksmillworksolutions", "dudeperfect", "duettoresearch", "dunnhumby", "duolingo", "durable", "dustyrobotics",
    "dv01", "dvtrading", "dxacirca", "dynamisinc", "dynamitegames", "dyopath", "earnin", "easygo",
    "easyship", "eatgron", "ebanx", "echodynecorp", "eclinicalsolutions", "eclipsetrading", "ecoatmgazelle", "edgewoodpartnersinsurancecenter",
    "edmentum", "edo", "educate", "education", "eei", "effectual", "efficientcomputer", "eikontherapeutics",
    "eknengineering", "elastic", "eleoshealth", "elevationscreditunion", "eliotcommunityhumanservices", "elitedentalpartnersllc", "elitetechnology", "elliginthealth",
    "emarketer", "embed", "embrace", "emergentlabsinc", "emergingtalent", "employerdirecthealthcare", "emslinqinc", "enavatecareers",
    "encoura", "endorlabs", "energyexemplarllc", "energyhub", "energysolutions", "engelhart", "engine", "engineersgate",
    "enhesa", "enigmaio", "ennoblecare", "enova", "ensco", "ensemble", "entera", "enterpret",
    "entersekt", "enveritas", "envisionconsulting", "enviva", "envoyglobalinc", "eosfitness", "eositsolutions", "epicgames",
    "epickids", "episodesix", "episodesixlinkedin", "eqtcorporation", "eqtpartners", "equalexperts", "eqvilentjobs", "ernestpackagingsolutions",
    "escribers", "esri", "ess", "etec", "ethernovia", "ethoslife", "eucalyptus", "euclidpower",
    "eudia", "eve", "ever", "everdriven", "evergreennephrology", "evergreenservicesgroup", "everlane", "everlaw",
    "everway", "evismart", "evolutionaryscale", "evolutioniq", "evydtech", "exadelinc", "excelsportsmanagement", "exodus54",
    "expertnetwork", "expressvpn", "extend", "extenteam", "extrahopnetworks", "ezcaterinc", "factored", "factorialenergy",
    "faircomny", "faire", "fairlife", "fal", "falconx", "fambrands", "familyoffice", "familyofkidz",
    "familywell", "faradayfuture", "fartherfinance", "fashionnova", "fastly", "federato", "feedzai", "fender",
    "fetch", "feverup", "fgsglobal", "fictiv", "fieldwire", "figma", "figure", "figureai",
    "filescom", "filson", "financialtechnologypartners", "financialtimes33", "finanzcheck", "finsterai", "fireblocks", "fireworksai",
    "firmus", "firstconnectinsurance", "firstmind", "firstprinciples", "five9", "fiveringsevents", "fiveringsllc", "fivetran",
    "flagshippioneeringinc", "flagstone", "flatironhealth", "fleetio", "fletcherjonesautomotivegroup", "flex", "flexport", "flighthub",
    "flip", "flockhomes", "flohealth", "flowfuse", "flowtraders", "fluxon", "flyr", "flywheeldigital",
    "flyzipline", "flyziplinenigeria", "flyziplineur", "focusfinancialpartners", "focuspartnersaustralia", "foleyhoag", "follettsoftware", "folxhealth",
    "forafinancial", "forbes", "forgebiologics", "formationbio", "formhealth", "formlabs", "forter", "forwardnetworks",
    "fosphamarketing", "fossainc", "found", "foundationriskpartners", "founders", "fourhands", "fourkites", "freeformfuturecorp",
    "freenome", "freenow", "freshprints", "frontierdermatologyprovidercareers", "fschumacherco", "fueledcareers", "fulfil", "fundraiseup",
    "funga", "fusionworldwide", "fuzehealth", "g2it", "galaxydigitalservices", "galileo", "galileofinancialtechnologies", "gallup",
    "gameseven", "gametimeunited", "gardacp", "garnerhealth", "gassouth", "gatherai", "gatikaiinc", "gelato",
    "gelbergroup", "gelberhandshake", "gemini", "genea", "generalassembly", "generalatlantic", "generalmatter", "generatebiomedicines",
    "genetixbiotherapeutics", "genevatrading", "geniussports", "genscript", "gensyn", "geotab", "getbuilt", "getnet",
    "getwellnetwork", "getyourguide", "ghost", "gigaenergy", "gillig", "gingerlabsinc", "ginkgobioworks", "gitlab",
    "givecampus", "givedirectly", "givewell", "glance", "gleanwork", "glencoreukwx", "glide", "globalaccelerator",
    "globalenergyallianceforpeopleandplanetgeappllc", "globalhealthcareexchangeinc", "globalizationpartners", "globalli", "globalwebindex", "glossgenius", "glossier", "glydways",
    "goatgroup", "gocardless", "gofundme", "goguardian", "goldenapplefoundationcareers", "goldenstate", "golin", "gomotive",
    "gongio", "goodbysilversteinpartners", "goodfire", "goodjobgames", "goodnotes", "goodwaygroup", "goop", "goremutualinsurance",
    "gorjana", "gormanbunch", "gostudent", "gotion", "govini", "govtechbarbados", "gr8tech", "gradial",
    "gradientai", "grafanalabs", "grahamcapitalmanagement", "gramgamescareers", "graphcore", "grayscaleinvestments", "greenpeace", "greenthumbindustries",
    "greenworkssunriseglobalmarketing", "griffisresidential", "groomecareers", "group14", "groupon", "grovecollaborative", "grover", "growe",
    "growtherapy", "groww", "gruns", "gsdm", "gtb", "guerrilla-games", "guidelighthealth", "guidepoint",
    "guidepointsecurity", "guidepostmontessori", "guidewheel", "guild", "gusto", "gymshark", "habitathealth", "hackerrank",
    "haizelabs", "hala", "halcyon", "hanwharenewables", "happymoney", "harbingermotors", "harborglobal", "harmonic",
    "harnessinc", "harpergroup", "harrisassociates", "harrowhealth", "harrys", "hatchcareers", "haven", "havenhub",
    "hawthornemachineryco", "hazel", "headlandsresearch", "headoutlinkedin", "headway", "healtheconnections", "healthverity", "hearcom",
    "hearcomin", "heartaerospace", "heartflowinc", "hebbia", "helium10", "hellofresh", "hellofreshprivate", "helloheart",
    "helsing", "heraldapi", "hereio", "hexagonbio", "hexarmor", "hextechnologies", "heygen", "hibu",
    "highdive", "higherlogic", "highnote", "hightouch", "hillel", "hillhousehome", "hive", "hivefinancialsystems",
    "hivestack", "homelight", "hometap", "homewardhealth", "honehealth", "honeycomb", "honor", "hoodhp",
    "hook", "hootsuite", "hoppr", "hopskipdrive", "horacemannservicecorporation", "horizonindustrieslimited", "houseaccount", "housecall",
    "housemarque", "housinganywhere", "hover", "hoyoverse", "hpiq", "hs", "hubspotjobs", "hudl",
    "hudsonrouge", "hugeinc", "humanagency", "humaninterest", "humanrightswatch", "humansignal", "humeai", "hungaryomg",
    "hungryroot", "huntress", "hut8", "hyannisportresearch", "hyperiondev", "hyphenconnect", "hypori", "ians",
    "ibkr", "ibkrexternal", "icapitalnetwork", "icb", "icemiller", "iconcareers", "iconiq", "ideo",
    "idme", "ieqcapital", "ifoodcarreiras", "iftother", "iherb", "imagentechnologies", "imaginepediatrics", "imagineworldwide",
    "imbibeinc", "imc", "impact", "impinjexternal", "impiricus", "imply", "imubit", "inceptive",
    "inchargeenergy", "incidentiq", "incode", "indiaomd", "industrialelectricmanufacturing", "industriouslabs", "inflectionai", "infuse",
    "inhometherapy", "inizio", "iniziomedical", "inkhousehq", "inkind", "inmobi", "insider", "insomniac",
    "inspiraeducation", "inspiremedicalsystemsinc", "inspiren", "instabase", "instawork", "instead", "instride", "insurance",
    "insurify", "insurtechinsights", "integra", "integrityrehabgroup", "intelluminc", "interbrand", "intercom", "interfaceai",
    "intermexwiretransfer", "internaljobsatlush", "interstellarlab", "interviewengineering", "interviewkickstart", "interworks", "inthepocket", "intradiem",
    "intrinsicrobotics", "inversionspace", "invgate", "invisibletech", "invivyd", "ionos", "ionq", "iovancebiotherapeutics",
    "iowacannabiscompany", "ipxpower", "isaac", "isccareers", "isomorphiclabs", "ispottv", "itd", "iterable",
    "iterativehealth", "itslogisticsllc", "ivalua", "ixllearning", "jadebiosciences", "janeasystems", "janestreet", "janestreetevents",
    "jazzx-ai", "jdsports", "jensenhughes", "jetbrains", "jetzero", "jfrog", "jobsatphamily", "johnsonlawgroup",
    "joinaffect", "joinparadigm", "jomboymedia", "joskoasp", "jshiddenevents", "jukeboxhealth", "jumia", "jumio",
    "jumpcrypto", "jumptrading", "junglescout", "juno", "justanswer", "justworks", "juullabs", "k2spacecorporation",
    "kairospower", "kalepa", "kallesgroup", "kalshi", "kapitus", "karat", "karbon", "kargo",
    "karya", "kasa", "kayak", "keelinfrastructure", "keepersecurity", "kellerpostman", "kentik", "keplergroup",
    "kernalbio", "ketchumuscareers", "ketryx", "kettle", "keystone", "khanacademy", "khealthcareers", "kiavi",
    "kickstarter", "kinders", "kinexus", "kitchenpark", "kizen", "klaviyo", "klaviyocampus", "knowbe4",
    "known", "koalafi", "koboldmetals", "koboldmetalsdrc", "koddi", "kodiak", "kodiaksolutions", "koleyjessen",
    "kolmacintegratedbehavioralhealth", "komodohealth", "konovo", "kraftonamericas", "krollbondratingagency", "kronosresearch", "kulficollective", "kunai",
    "kuraoncology", "kyocare", "kyowakirinusa90", "la2028", "la28careers", "labelbox", "landor", "larkinstreetyouthservices",
    "lasenza", "laskoproducts", "lastpass", "later", "latitude", "lattice", "launch2", "launchdarkly",
    "launchpadtechnologiesinc", "lawzero", "layerhealth", "layerzerolabs", "leadingeducators", "leagueinc", "leapwork", "learneo",
    "learnlux", "learnupon", "ledgy", "legalservicesnyc", "legendcareers", "legion", "lendingtree", "levanta",
    "levelaccess", "levio", "levitate", "lgelectronics", "lgenergyaz", "liberate", "liberis", "life360",
    "lifeskillsautismacademy", "lifetrading", "liftoff", "lightfeatheriollc", "lightforceorthodontics", "lighthouse", "lightmatter", "lightningai",
    "lightricks", "lightspeeddms", "lightspeedhq", "lightspeedhqfr", "lightspeedsystems", "lilasciences", "lincoln", "link",
    "liquiddeath", "liquidiv", "lirio", "lisc", "lithic", "litify", "littlepay", "livescore9",
    "llrpartnersjobs", "lob", "locusrobotics", "lodestarspace", "logicgate", "logos", "lokainc", "lookoutinc",
    "loop", "lpc", "lpl", "ltse", "lucidbots", "lucidmotors", "lucidsoftware", "lumahealth",
    "lumimeds", "lumos", "lumosfiber", "lunarenergy", "luno", "lush", "lydech", "lyft",
    "lynxanalytics", "m3", "m9solutions", "mabl", "madano", "madisonenergyinfrastructure", "magicleap", "magnolia",
    "maintainx", "makeawishamerica", "mako", "mammothbrands", "mangroup", "manscaped", "mantrahealth", "manychat",
    "map", "maplighttherapeutics", "mark43", "marketaxesscorporation", "markspainrealestate", "marqeta", "marqvision", "martellgrowthsolutions",
    "massarcapital", "masterclass", "materialbank", "materialize", "matherheadquarters", "matteprojects", "mattermost", "mavenclinic",
    "mavensecuritiesholdingltd", "maymobility", "mazetherapeutics", "mbooth", "mcadams", "mcculloughrobertson", "mcghealth", "mcmastercarr",
    "mco", "mcs", "medeloop", "mediabrands", "medicalinformaticsengineering", "medier", "medsien", "mejuri",
    "melio", "meltplan", "memx", "menaconsultant", "mentalhealthcenterofdenver", "mento", "merakimanagement", "mercari",
    "merceradvisors", "mercury", "merge", "meridianpartners", "meritamerica", "meriton", "merqube", "mesh",
    "metabittechnologyllc", "metacore", "metalab", "metoxinternationalinc", "metronome", "metropolis", "metropolitancommercialbank", "mgtinsurance",
    "mhi", "midihealth", "mill", "milliondollarbabyco", "mindbody", "mineralystherapeutics", "minio", "minitab",
    "miopartners", "miqdigital", "mirakl", "mirakllabs", "mirumpharmaceuticals", "misfitsmarket", "missionlane", "mithril",
    "mitratech", "mitsogoinc", "mitsubishimotorsna", "mixpanel", "mlbevents", "mntn", "mobentertainment", "mobilityware",
    "mochihealth", "modernanimal", "modernhealth", "modulrfinance", "moduscreate", "moia", "moloco", "momence",
    "momentumcompany3", "momentumfinancialservicesgroup", "moneyherogroup", "moneysmart", "mongodb", "moniepoint", "monroetractor", "monumentalsports",
    "monzo", "moonlite", "morganmorganjobsapplynow", "morsemicro", "mossnewyorkllc", "motional", "movementstrategy", "mozilla",
    "mqreferrals", "mrapple", "mrapplecareers", "mrbeastyoutube", "msfcareers", "mthreerecruitingportal", "muckrack", "muonspace",
    "myfitnesspal", "myfundedfutures", "myriad360", "myshell", "n26", "n2co", "nabis", "nanonets",
    "nansen", "narvar", "nascompany", "natera", "nationaldbs1", "nationallifeinsurancecompany", "nationalpublicradioinc", "naturesbakery",
    "naughtydog", "navapbc", "navervietnam", "navierboat", "navvis", "nayya", "nearform", "nearspacelabs",
    "nearsure", "nebius", "neighborsbank", "neo4j", "neoris", "neptuneai", "nerdy", "nerostechnologies",
    "netdocuments", "neteasegames", "netlify", "netskope", "neuehealth", "neuraflash", "neuralink", "neweratech",
    "newlabcareers", "newleafenergy", "newlimit", "newrelic", "newsbreak", "newsela", "newsweek", "nex",
    "nexgencloud", "nextinsurance66", "neysanetwork", "nflcareers", "ngrokinc", "nice", "nift", "nimblegravity",
    "ninjatrader", "nintendo", "niraenergy", "nitricity", "nix", "nlcventures", "nmcareers", "nmi",
    "nomiso", "nonprofitfinancefund", "northbeam", "northmarq", "northwestpipefittings", "novacredit", "novafounders", "nozominetworks",
    "nscaleoperationsukltd", "ntconcepts", "nttdatausa", "nubank", "numagroupgmbh", "numerix", "numus", "nuro",
    "nutrafol", "nycedc", "nyiso", "oafkenya", "obexp", "obsidiansecurity", "ocadogroup", "ocrolusinc",
    "octave", "octus", "oddball", "odeko", "odlesalescareers", "offerup", "offerzen", "officehours",
    "officespacesoftware", "offshorelaunch", "ogilvy", "ogilvyaus", "ogilvycanada", "ogilvygermany", "ogilvyhealthcanada", "ogilvyhealthuk",
    "ogilvyhealthusa", "ogilvymena", "ogilvyspain", "ogilvyuk", "ogt", "ohalogenetics", "ohio", "oklo",
    "okta", "okx", "olema", "olipop", "olivai", "oliver", "olly", "olsson",
    "olympusproperty", "omadahealth", "omgcamontreal", "omgcamontrealfr", "omgcaphd", "omgnetherlands", "omguk", "omgus",
    "omgusannalect", "omgushs", "omgusomd", "omgusphd", "omnicomhealth", "omnicommediagroupmxomg", "omnicomproduction", "onbe",
    "onboardmeetings", "oneacrefund", "oneimaging", "onenergy", "onrunning", "onxmaps", "ooma", "opendoor",
    "openeye", "openfarminc", "openly", "opensesame", "opentable", "openwork", "ophelia", "ophelos",
    "opj", "oportun", "opploans", "optimalcare", "optimaldynamics", "optiverprivate", "optoinvest", "orcasecurity",
    "orchard", "orderly", "oriongroup", "orioninnovationnaukri", "orkes", "osano", "oscar", "oshihealth",
    "otter", "otterai", "ottoaviation", "oura", "ourgroup", "outfit7", "outrider", "outschool",
    "outsetmedical", "overstory", "pacificlegalfoundation", "pacnyc", "pacvue", "pagaya", "pagerduty", "pagonxt",
    "pairteam", "pallet", "palmettocleantech", "paloit", "pandadoc", "panthalassa", "pantheon", "pantheonpublic",
    "pantherlabs", "papa", "paperlessparts", "parachutehealth", "parallellearning", "paratekpharmaceuticals", "parloa", "parsleyhealth",
    "particle41llc", "pathai", "pathrobotics", "pathward", "patientpoint", "patterndata", "paveakatroveinformationtechnologies", "paxlabs",
    "pay2dc", "payoneer", "paypay", "paypaycard", "paystack", "paytient", "pcdm", "pdtpartners",
    "peakdesign", "peloton", "pendo", "penninteractive", "pep", "peregrinetechnologies", "perfectserve", "perionnetworkltd",
    "perryellisinternational", "perryellisinternationalretail", "perscholashires", "personalisinc", "personalizedbeautydiscoveryincdbaipsy", "pfm", "pharmacann", "pharomanagement",
    "phasev", "philliesbaseballoperations", "philo", "philzcoffeecareers", "phiture2", "phizenix", "phoenixcontact", "phonepe",
    "physicsx", "picoquantitativetrading", "pieinsurance", "piermontbank", "pilothq", "pineparkhealth", "pingidentity", "pinterestjobadvertisements",
    "pipe17", "pitchbookdata", "placementsio", "placerlabs", "planetlabs", "planetscale", "planradar", "platacard",
    "platformscience", "plexusworldwidellc", "plos", "plscareers", "pluspower", "pmc", "pmg", "podium81",
    "point72", "pointc", "pointdigitalfinance", "poka", "pokemoncareers", "polyai", "polychaincapital", "pomelocare",
    "pontera", "poppulo", "porternovelli", "possiblefinancialinc", "postman", "postscript", "powerdigitalmarketing", "practicebetter",
    "praxent", "praxisprecisionmedicines", "precisionaq", "precisionmedicinegroup", "premiertruckrental", "presencelearning", "presidents", "presidentsinstitutesweden",
    "prevail", "prezzee", "pricefox", "privateequityinsights", "prodigal", "profluent", "project44", "projectaservicesgmbhcokg",
    "prolaio", "prolific", "prometheusrealestategroup", "propel", "prophecysimpledatalabs", "propublica", "prosek", "proshares",
    "prosperhealth", "prove", "psibufet", "psiquantum", "public", "pubmatic", "pulley", "pulumicorporation",
    "pumpcareers", "purestorage", "putnamassociatesllc", "qcentrix", "qualia", "qualifieddigital", "qualifiedhealth", "qualio",
    "qualtrics", "quanata", "quanthealth", "quantumcoffee", "quantumsi25", "quartzbio", "quberesearchandtechnologies", "queracomputinginc",
    "quillbot", "quince", "quintoandar", "quisitivejobs", "qventus", "rackner", "radar", "radiantsecurity",
    "radicalnumerics", "radiclehealth", "radixexperienced", "raft", "raisin", "range", "rapidsos", "rapp",
    "razorpaysoftwareprivatelimited", "reach3insights", "reactivate", "realchemistry", "realtimeboardglobal", "rebag", "rebuildmanufacturing", "recharge",
    "recidiviz", "recordedfuture", "recruitis", "rectanglehealth", "recursionpharmaceuticals", "redcellpartners", "reddit", "redpandadata",
    "redstoneresidential", "redwoodmaterials", "redwoodsoftware", "reemahealth", "reformation", "regscale", "relativity", "relaygraduateschoolofeducation",
    "relaypayments", "relaypro", "relaytherapeutics", "reltio", "relyance", "remoracarbon", "remotasks", "remotecom",
    "remotepeople", "remotetcx", "renaissancelearning-nam", "renttherunway", "res", "researchpartnership", "residenthome", "resilience",
    "resolvetosavelives", "resortpass", "resultspt", "retailinsights", "reunionmarketing", "revero", "rewardsnetwork", "rfsmart",
    "rga", "rhombuspower", "rhythmsoftwareinc", "rigup", "riotgames", "ripple", "rise8", "riskified",
    "rithum", "rithumliboard", "ritual", "rivaltechnologies", "roadie", "roadrunner", "roblox", "roboforce",
    "roboyo", "rocketchat", "rocketlab", "rocketlawyer", "rocketmiles", "rockstargames", "roku", "roller",
    "rondoenergy", "roo", "roofr", "roofstock", "rti", "rubrik", "ruggable", "runpod",
    "runwise", "rushstreetinteractive", "rvi", "rxr", "rxsense", "rzr", "saasgroup", "sabertech",
    "safariai", "salesloft", "salsify", "saltsecurity", "samainc", "sambanovasystems", "samsara", "samsungresearchamericainternship",
    "samsungsemiconductor", "sandstonecare", "sandtechholdingslimited", "sanfranciscocampusforjewishliving", "saucelabs", "saxllp", "sayari", "scaleai",
    "scandit", "scangroup", "schonfeld", "schrdinger", "scopely", "scorpionenterprisesllc", "scotch", "scout24",
    "scoutai", "scoutmotors", "seamlessai", "seatgeek", "seattlesoundersfc", "secondarysocials", "secretariatadvisorsllc", "securitize",
    "securityscorecard", "seed", "seesaw", "selectmanagementgroup", "selffinancial", "selinicapital", "semafor", "sendbird",
    "seniordoc", "senrasystems", "seoulrobotics", "septerna", "serhant", "sertis", "sertradingsa", "sesamm",
    "sesolabor", "setpoint", "sevenresearch", "seyond", "sezzle", "sfaf", "sfox", "shakepay",
    "shardeumfoundation", "sharebite", "sharegateen", "sharkninjaoperatingllc", "shein", "shieldshealthsolutions", "shift4", "shift5",
    "shifttechnology", "shimizunorthamerica", "shipbobinc", "shipwell", "shopfully", "shopltk", "shopmy", "showpad",
    "shunnarahcareers", "siei", "sifthealthcare", "sightlinemediagroup", "sigmacomputing", "sigmoid", "signerscareers", "signifyd95",
    "siliconranch", "silverado", "silvus", "similarweb", "simplesense", "simplextrading", "simplifynext", "simtrabps",
    "simulamet", "singlestore", "sironamedical", "sisense", "siteline", "sixfold", "skhynixamerica", "skhynixmemorysolutionsamericainc",
    "skildai-careers", "skinclique", "skinlaundry", "skylighthq", "skylotechnologies", "skyscanner", "slice", "slingshotaerospace",
    "smartasset", "smartbear", "smarterdx", "smartling", "smartlyio", "smartrent", "smartsheet", "smavagmbh",
    "smcp", "smcpnorthamerica44hq", "smithrx", "snapmobileinc", "snorkelai", "snowcompanies", "soci", "sociallab",
    "sofi", "sohohouseco", "sojern", "soldejaneiro", "solera", "solidpower", "sollishealth", "sonatus",
    "sonicwall", "sonobello", "sonyinteractiveentertainmentglobal", "sonymusicasiacareers", "sonymusiccareersnetherlands", "sonymusiccareerspoland", "sonymusicde", "sonymusicentertainment",
    "sonypicturesanimation", "sonypicturesimageworks", "sothebys", "sourcegraph91", "southcolumbuspreparatoryacademygermanvillage", "southstarcareers", "southworks", "spacekinetic",
    "spacex", "spacexglobal", "spade", "sparkadvisors", "sparkland", "sparksoftcorporation", "sparrow", "spauldingridge",
    "spcareers", "specterops", "speechify", "speechmatics", "spektrum", "sphinxdefense", "spin", "spire",
    "splice", "sponsorsforeducationalopportunity", "spothopper", "spotter", "sprengnetter", "springboard", "springboardmentors", "springhealth66",
    "spsnorthamerica", "spsnorthamericaselected", "spycloud", "squarepointcapital", "squarespace", "srsacquiom", "stabilityai", "stackadapt",
    "stackav", "stackblitz", "stackexchange", "stackline", "stambaughness", "standardnuclearinc", "stanley1913-us", "starburst",
    "starcloud", "starrez", "startcampus", "startree", "steercrm", "stemhealthcare", "sterlingtonpllc", "stitchfix",
    "stockx", "stoiximan", "stone", "storespace", "storycannabis", "straightarrownews", "strandtherapeutics", "stratacareers",
    "stratainformationgroup", "strategichr", "striiminc", "strike", "strivehealth", "striveworks", "strongholdim", "stubhubinc",
    "studapart", "studiokraftonboard", "studycontractors", "suki", "summer", "summitonevanderbilt", "sumologic", "sumup",
    "sunnyside", "sunrise", "superbet", "superblocks", "supportingstrategies", "sureify", "surveymonkey", "sustainabletalent",
    "sustainment", "swarmaero", "sweetgreen", "sylogist", "symbolica", "synack", "syndigo", "synerg",
    "synthesishealth", "system", "systemiq", "systemstechnologyresearch", "tabapay", "tailorcare2023", "tailscale", "takealotcom",
    "takealotgroup", "taketwo", "talkdesk2", "talkspacepsychiatry", "talkspacetherapist", "talonone", "tandemlaunch", "tandemmoneylimited",
    "tangogameworks", "tanium", "tanius", "targetrwe", "taskrabbit", "tastytrade", "tatari", "taxbit",
    "tbhcdelivers", "tbwachiatday", "tdinternational", "teachablecareers", "teague", "teampicnic", "tebra", "techholding",
    "tecovas", "tegnainc", "tekion", "tekmetric", "tellius", "telnyx54", "temporal", "temporaltechnologies",
    "temus", "tenableinc", "teneolinkedin", "tensorops", "tenstorrent", "tenstorrentuniversity", "tenstorrentunlisted", "teravision",
    "terrabis", "terranorbitalcorporation", "thanx", "thatch", "thatsnomoonentertainment", "thealleninstitute", "thebrattlegroup", "thedailybeast31",
    "thedurstorganization", "thedutchie", "theeconomistgroup", "thefarmersdog", "thefloridapanthers", "thefork", "theiconic", "thejewishfederationsofnorthamerica",
    "thejpbfoundation", "theknotworldwide", "thelibragroup", "themartinagency", "themjcos", "themuseumofscience", "thenewyorktimes", "thenuclearcompany",
    "thepharmacyhub", "thequalitygroupgmbh2", "thesiscareers", "thetradedesk", "thevirtussolution", "theweathercompany", "thiess", "think-cell",
    "thinkacademyus", "thinkingmachines", "threatlocker", "thrive", "thrivecart", "thumbtack", "thymecare", "tia",
    "tide", "tigergraph", "tines", "tintai", "tipaltisolutions", "toast", "togetherai", "tomofunfurbo",
    "tomorrow", "toogoodtogo", "topcompare", "topsort", "topsteptrader", "toradex", "torcrobotics", "torq",
    "toshibaglobalcommercesolutions", "tosscareers", "touchbistro", "towerpeak", "tpcengineeringholdingsllc", "tpreducationllc", "trace3", "trackomc",
    "traderepublicbank", "tradingacademy2025", "trailerpark", "transcarent", "transcendinc", "transmarketgroup", "trase", "trellahealth",
    "tripactions", "tripadvisor", "triplewhale", "triumvirateenvironmental", "trueanomalyinc", "truebill", "truecaller", "trueclassicteesllc",
    "truelayer", "trufflesecurity", "trufru", "trustbank", "trustpilot", "trustwill", "truveta", "try-picnic",
    "tubitv", "tucows", "tudorgroup", "tulip", "turbineone", "turbotenant", "turing", "twilio",
    "twinhealth", "twistbioscience", "twitch", "twosixtechnologies", "typeface", "typeform", "uberfreight", "udacity",
    "udemy", "udemybedi", "udio", "ultimagenomics", "umaeducationinc", "unchainedlabs", "underdogfantasy", "understoodcare",
    "unispace", "unitedfirm", "unitedmasterstranslation", "uniteus", "universal", "unlockhealth", "unrealsnacks", "unybrands",
    "upbound", "updater", "upgrade", "upkeep", "upriteconstruction", "upshop", "upside", "upstart",
    "upwork", "urbansportsclub", "urschellaboratoriesinc", "usamechasp", "usconec", "usenourish", "v1", "vacasa",
    "vaco", "vailclinicincdbavailhealthhospital", "valerahealth", "valohealth", "vanmetre", "vannahealth", "vannevarlabs", "vardaspace",
    "varicent", "vast", "vaticlabs", "vaxcyte", "vectara", "vectranetworks", "veeamsoftware", "velir",
    "venncity", "veocorporatecareers", "veracode", "veracyte", "verainstituteofjustice", "verantos", "veratherapeuticsinc", "vercel",
    "veriff", "verifone", "verisign", "veristainc", "verkada", "verramobility", "versaterm", "verse",
    "verstela", "vestmark", "vestwell", "veza", "vgw", "via", "viamrobotics", "vikingglobalinvestors",
    "viralnation", "virbiotechnologyinc", "virtru", "virtu", "viseai", "visiersolutionsinc", "visualconcepts", "vitablehealth",
    "vmlcanadaen", "vmlenterprisesolutions", "vonage", "voxmedia", "voyagertechnologiesinc", "vpaofflorida", "vsco39", "vtex",
    "vts", "vulcanelements", "vulncheck", "vynamic", "wallapop", "walleyecapital-external-fulltime", "wallstreetprep", "waltzhealth",
    "warburgpincusllc", "wargamingen", "warp", "wasabi", "watershed", "waymark", "waymo", "wayve",
    "wayvia", "webchartnow", "webershandwick", "webflow", "wecommunications", "weedmaps77", "weee", "wehrtyou",
    "weinsteinproperties", "weissassetmanagement", "welbehealth", "weploy", "wesingapore", "wettermarkkeith", "wfclainc", "whalarinc",
    "wheelhouse", "whogivesacrap", "wikimedia", "wilsonelser", "wingspan", "winhomeinspection", "withcoverage", "wizardcommerce",
    "wizinc", "wolt", "wonderschool", "wonderstudios", "woo", "woolpert", "workatbackbase", "workato",
    "workboard", "workera", "workhelix", "workleap", "workoverseas", "workstream", "workwize", "worldlabs",
    "worldquant", "wovencare", "wpp", "wppmedia", "wrike", "wundercapital", "wyndlabs", "xai",
    "xairatherapeutics", "xantium", "xapo61", "xealth", "xebiausa", "xendit", "xhiring", "xntltd",
    "xometry", "xometryeurope", "xpengmotors", "xtxmarketstechnologies", "xund", "yesenergy", "yext", "yipitdata",
    "yipitdatajobs", "ylopo", "yotpo", "youcom", "yougov", "yousician", "ysoftcorporation", "yubico",
    "yugabyte", "yurtsai", "zam", "zambold", "zenbusiness", "zengrc", "zennioptical", "zenoti",
    "zephyrhome", "zevia", "zind-erprogram", "zinnia", "zipcolimited", "ziprecruiter", "zocdoc", "zone5technologies",
    "zonecompanysoftwareconsultingllc", "zoominfo", "zscaler", "zulualphakilo", "zuora", "zupinnovation", "zwift", "zyngacareers",
    # ── Additional high-value Data Engineering employers ───────────────────
    # Cloud / Data platforms
    "databricks", "snowflake", "airflow", "dbtlabs", "fivetran",
    "hightouch", "singlestore", "clickhouse", "starburst", "imply",
    "acryldata", "atlan", "datacatalog", "selectstar", "metaphor",
    "airbyte", "meltano", "prefecthq",
    # Fintech / Banking
    "stripe", "plaid", "brex", "ramp", "chime", "sofi",
    "marqeta", "nerdwallet", "robinhood", "coinbase", "ripple",
    "kraken", "blockchain", "gemini",
    # Consumer tech
    "airbnb", "netflix", "doordash", "instacart", "lyft",
    "pinterest", "snapchat", "reddit", "twitter", "tiktok",
    "shopify", "etsy", "ebay",
    # SaaS / B2B
    "notion", "figma", "miro", "airtable", "asana", "monday",
    "zendesk", "intercom", "hubspot", "salesforcedev",
    "gitlab", "hashicorp", "confluent", "mongodb", "elastic",
    "datadog", "pagerduty", "newrelic", "splunk",
    "twilio", "sendgrid", "segment", "amplitude", "mixpanel",
    # Startup / growth companies focused on data
    "rippling", "gusto", "lattice", "checkr", "carta",
    "benchling", "scale", "weights-biases", "cohere", "openai",
    "anthropic", "perplexity", "mistral",
    # Indian IT / outsourcing
    "cognizant", "capgemini", "epam", "globallogic",
]

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_SEM = asyncio.Semaphore(50)


def _is_relevant(title: str) -> bool:
    from scrapers.base import is_relevant_title
    return is_relevant_title(title)


def _is_recent(date_str: str) -> bool:
    if not date_str:
        return True
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= datetime.now(timezone.utc) - timedelta(hours=CUTOFF_HOURS)
    except Exception:
        return True


BOARD_INFO_URL = "https://boards-api.greenhouse.io/v1/boards/{board}"

async def _fetch_board(client: httpx.AsyncClient, board: str) -> list[dict]:
    async with _SEM:
        try:
            jobs_url = BASE.format(board=board)
            info_url = BOARD_INFO_URL.format(board=board)

            # Fetch board info + jobs concurrently to get real company name
            jobs_resp, info_resp = await asyncio.gather(
                client.get(jobs_url, params={"content": "true"}),
                client.get(info_url),
                return_exceptions=True,
            )

            if isinstance(jobs_resp, Exception) or jobs_resp.status_code == 404:
                return []
            jobs_resp.raise_for_status()

            # Real company name from board info endpoint
            company_name = board.replace("-", " ").title()  # fallback
            if not isinstance(info_resp, Exception) and info_resp.status_code == 200:
                api_name = info_resp.json().get("name", "")
                if api_name:
                    company_name = api_name

            data = jobs_resp.json()
            jobs = []
            for item in data.get("jobs", []):
                title = item.get("title", "")
                if not _is_relevant(title):
                    continue
                updated = item.get("updated_at", "")
                if not _is_recent(updated):
                    continue

                job_url = item.get("absolute_url", "")
                if not job_url:
                    continue

                loc_list = item.get("offices", []) or item.get("location", {})
                if isinstance(loc_list, list):
                    location = ", ".join(o.get("name", "") for o in loc_list if o.get("name"))
                else:
                    location = loc_list.get("name", "") if isinstance(loc_list, dict) else ""

                country = detect_country(location, default="USA" if not location else "")
                if country not in ("USA", "India", "Remote"):
                    continue

                desc_html = item.get("content", "")
                desc = BeautifulSoup(desc_html, "lxml").get_text(separator="\n", strip=True) if desc_html else ""

                jobs.append(JobData(
                    title=title,
                    company=company_name,
                    url=job_url,
                    source="Greenhouse",
                    description=desc,
                    location=location,
                    country=country,
                    salary="",
                    remote="remote" in (title + location).lower(),
                    posted_at=updated,
                ).to_dict())
            return jobs
        except Exception:
            return []


async def fetch(settings: dict) -> list[dict]:
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        tasks = [_fetch_board(client, board) for board in BOARDS]
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

    print(f"[Greenhouse] {len(jobs)} jobs from {len(BOARDS)} boards")
    return jobs
