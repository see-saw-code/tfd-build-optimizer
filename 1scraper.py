import copy
import gzip
import time
import urllib
import urllib.request

import simplejson as json


def get_module_summary():
    """
    We have to use urllib, otherwise we get 403'd by Cloudflare. I think this is because httpx and requests both convert
    the http headers to lowercase. Although httpx says they preserve case now, I can't figure out how to turn that on.
    """
    req = urllib.request.Request("https://tfd-api.nexon.com/api/library/en/modules")

    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
    )
    req.add_header(
        "Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    )
    req.add_header("Accept-Language", "en-US,en;q=0.5")
    req.add_header("Accept-Encoding", "gzip, deflate")
    req.add_header("Connection", "keep-alive")
    req.add_header("Content-Type", "application/json")

    page = 1
    # web browser requests pages of this size, i havent tried anything else
    page_sz = 48

    with open("1modules-summary.json", "w") as f:
        f.write("[\n")
        while True:
            body = {
                "gradeType": "",
                "groupType": "",
                "pageNumber": page,
                "pageSize": page_sz,
                "runeType": "",
                "searchText": "",
                "socketType": "",
            }

            json_bytes = json.dumps(body, use_decimal=True).encode("ascii")
            req.add_header("Content-Length", len(json_bytes))

            with urllib.request.urlopen(req, json_bytes) as resp:
                if resp.info().get("Content-Encoding") == "gzip":
                    txt = gzip.decompress(resp.read())
                else:
                    txt = resp.read().decode()
            j = json.loads(txt, use_decimal=True)
            json.dump(j, f, indent=4, use_decimal=True)

            if page * page_sz > j["ResultData"]["n8TotalCount"]:
                f.write("\n")
                break
            page += 1
            f.write(",\n")
        f.write("]\n")


def get_module_details():
    with open("1modules-summary.json", "r") as f:
        j = json.load(f, use_decimal=True)
    req2_fmt = urllib.request.Request(
        "https://tfd-api.nexon.com/api/library/en/modules/{num}"
    )
    req2_fmt.add_header(
        "User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
    )
    req2_fmt.add_header("Accept", "application/json, text/plain, */*")
    req2_fmt.add_header("Accept-Language", "en-US,en;q=0.5")
    req2_fmt.add_header("Accept-Encoding", "gzip, deflate, br, zstd")
    req2_fmt.add_header("Origin", "https://tfd.nexon.com")
    req2_fmt.add_header("Connection", "keep-alive")
    req2_fmt.add_header("Referer", "https://tfd.nexon.com/")
    req2_fmt.add_header("Sec-Fetch-Dest", "empty")
    req2_fmt.add_header("Sec-Fetch-Mode", "cors")
    req2_fmt.add_header("Sec-Fetch-Site", "same-site")
    req2_fmt.add_header("Priority", "u=0")

    with open("2modules-details.json", "w") as f:
        f.write("[")

    with open("2modules-details.json", "a") as f:
        for page_idx, page in enumerate(j):
            for entry_idx, entry in enumerate(page["ResultData"]["List"]):
                req2 = copy.copy(req2_fmt)
                req2.full_url = req2.full_url.format(num=entry["id"])
                with urllib.request.urlopen(req2) as resp2:
                    if resp2.info().get("Content-Encoding") == "gzip":
                        txt = gzip.decompress(resp2.read())
                    else:
                        txt = resp2.read().decode()
                j2 = json.loads(txt, use_decimal=True)
                json.dump(j2, f, indent=4, use_decimal=True)
                if entry_idx != len(page["ResultData"]["List"]) - 1:
                    f.write(",")
                f.write("\n")
            if page_idx != len(j) - 1:
                f.write(",")
            f.write("\n")
            time.sleep(1)
        f.write("]")


if __name__ == "__main__":
    get_module_summary()
    get_module_details()
