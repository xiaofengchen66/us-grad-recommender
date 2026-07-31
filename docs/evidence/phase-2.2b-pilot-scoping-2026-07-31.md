# Phase 2.2B pilot-scoping fetch log — 2026-07-31

Raw evidence backing `docs/PHASE_2_CATALOG_DESIGN.md` §13.1. Each block is the
actual command run and the actual matched output (truncated to 200 chars/line
for readability — full responses are large HTML/JSON payloads, not committed
here). All fetches used a browser-like User-Agent; plain `curl` with no UA
gets blocked on at least one of these (see the New Haven entry).

## UT Austin
`https://catalog.utexas.edu/`
```
HTTP 200, 219770 bytes
16:<link rel="stylesheet" type="text/css" href="/css/courseleaf.css" />
26:<script type="text/javascript" src="/js/courseleaf.js"></script>
```

## University of Alaska Fairbanks
`https://catalog.uaf.edu/masters/`
```
HTTP 200, 151519 bytes
17:<link rel="stylesheet" type="text/css" href="/css/courseleaf.css?v=1781278969000" />
30:<script type="text/javascript" src="/js/courseleaf.js"></script>
```

## Georgia Tech (general catalog)
`https://catalog.gatech.edu/`
```
HTTP 200, 69636 bytes
18:<link rel="stylesheet" type="text/css" href="/css/courseleaf.css?v=1776778119000" />
34:<link rel="stylesheet" type="text/css" href="/css/courseleaf.css" />
41:<script type="text/javascript" src="/js/courseleaf.js?v=1777565467000"></script>
```

## UC Davis
`https://catalog.ucdavis.edu/`
```
HTTP 200, 54313 bytes
17:<link rel="stylesheet" type="text/css" href="/css/courseleaf.css?v=1776255556000" />
24:<script type="text/javascript" src="/js/courseleaf.js?v=1776255581000"></script>
```

## UIUC
`https://catalog.illinois.edu/graduate/`
```
HTTP 200, 95182 bytes
17:<link rel="stylesheet" type="text/css" href="/css/courseleaf.css?v=1781878308000" />
24:<script type="text/javascript" src="/js/courseleaf.js?v=1781878309000"></script>
```

## MIT
`https://catalog.mit.edu/`
```
HTTP 200, 68512 bytes
16:<link rel="stylesheet" type="text/css" href="/css/courseleaf.css?v=1780508242000" />
25:<script type="text/javascript" src="/js/courseleaf.js"></script>
```

## Alabama A&M University
`https://www.aamu.edu/academics/catalogs/graduate-catalog.html`
```
HTTP 200, 43496 bytes
Graduate Catalog 2009-2011
Graduate Catalog 2011-2012
Graduate Catalog 2012-2013
Graduate Catalog 2013-2014
Graduate Catalog 2014-2015
```

## Stanford
`https://bulletin.stanford.edu/`
```
HTTP 200, 910549 bytes
4:;NREUM.info={beacon:"bam.nr-data.net",errorBeacon:"bam.nr-data.net",licenseKey:"NRJS-3b34f5fe10831ff33af",applicationID:"1298193956",sa:1}</script><style>html
9:</style></div><div id="navbar" class="relative bg-theme-navbar-background" style="box-shadow:0px 0px 6px 6px rgb(0 0 0 / 6%);"><div class="bg-theme-dark" data
414:</div></div></div></div></div><div id="teleports"></div><script>window.__NUXT__={};window.__NUXT__.config={public:{DEV:false,BASE_URL:"https://app.coursedog
```

## Georgia Tech OMSCS admission criteria
`https://omscs.gatech.edu/admission-criteria`
```
HTTP 200, 54121 bytes
```

## Georgia Tech OMSCS FAQ
`https://omscs.gatech.edu/prospective-student-faqs`
```
HTTP 200, 93616 bytes
visas, so they do not qualify for OPT.</p></div><h3 class="faqfield-question"><a href="#faq-What-are-the-expectations-for-enrollment,-coursework
visas for OMSCS students. International students do not require U.S. residency to enroll in OMSCS.</p></div><h3 class="faqfield-question"><a hre
```

## University of New Haven
`https://catalog.newhaven.edu/content.php?catoid=31&navoid=2062`
```
HTTP 202, 0 bytes
x-amzn-waf-action: challenge
Access-Control-Expose-Headers: x-amzn-waf-action
```

`https://catalog.newhaven.edu/robots.txt`
```
# Oberlin's bot.
User-agent: archive.org_bot
Disallow: /portfolio.php
Disallow: /portfolio_nopop.php
Disallow: /ajax/
Disallow: /search_advanced.php
crawl-delay: 15

#Owens Community College
User-agent: occ-crawler
Disallow: /portfolio.php
Disallow: /portfolio_nopop.php
Disallow: /ajax/
Disallow: /search_advanced.php
crawl-delay: 15

# Everyone else.
User-agent: *
Disallow: /portfolio.php
Disallow: /portfolio_nopop.php
Disallow: /ajax/
Disallow: /search_advanced.php
crawl-delay: 120
```
robots.txt does not disallow `/content.php` (the catalog page path); it sets
`crawl-delay: 120` for unnamed user-agents. The block above is an AWS WAF Bot
Control challenge (fingerprint-based), not a robots.txt exclusion.
