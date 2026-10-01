"""READ-ONLY: what the live sitemap lists (counts per URL pattern)."""
import re, urllib.request
xml = urllib.request.urlopen(urllib.request.Request("https://satyadheesh.in/sitemap.xml", headers={"User-Agent": "satya-diag"}), timeout=120).read().decode()
urls = re.findall(r"<loc>([^<]+)</loc>", xml)
print("total urls:", len(urls))
for pat in ["/upsc/reports", "/upsc/current-affairs/week/", "/upsc/current-affairs/month/", "/upsc/current-affairs/20", "/event/", "/vaade/", "/news/", "/source/"]:
    m = [u for u in urls if pat in u]
    print(f"{pat:32} {len(m):5}  e.g. {m[:3]}")
