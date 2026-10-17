#!/usr/bin/env python3
"""Save one California code section from the Legislative Counsel's official bulk download.

leginfo.legislature.ca.gov refuses scripted page requests, but the Legislature publishes the same data for
download at downloads.leginfo.legislature.ca.gov (the "pubinfo" files). This reads only the two members it needs
from the session zip with HTTP range requests, so the 1 GB zip is never downloaded.

    python3 scripts/leginfo-section.py GOV 65913.4 data/manual/gov_65913_4_leginfo.txt

The output is the section's text, one paragraph per line, preceded by the history note and the source."""

import html
import io
import re
import sys
import urllib.request
import zipfile
from datetime import UTC, datetime

ZIP = "https://downloads.leginfo.legislature.ca.gov/pubinfo_{session}.zip"


class _RangeFile(io.RawIOBase):
    def __init__(self, url: str):
        self.url, self.pos = url, 0
        self.size = int(urllib.request.urlopen(urllib.request.Request(url, method="HEAD")).headers["Content-Length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size:
            return 0
        end = min(self.pos + len(b), self.size) - 1
        data = urllib.request.urlopen(urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{end}"})).read()
        b[: len(data)] = data
        self.pos += len(data)
        return len(data)


def caml_to_text(caml: str) -> str:
    s = caml.replace('<span class="EnSpace"/>', " ")
    s = re.sub(r"</p>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    return "\n".join(re.sub(r"\s+", " ", line).strip() for line in s.splitlines() if line.strip()) + "\n"


def main(code: str, section: str, out: str, session: str = "") -> None:
    session = session or str(datetime.now(UTC).year - (datetime.now(UTC).year + 1) % 2)
    url = ZIP.format(session=session)
    z = zipfile.ZipFile(io.BufferedReader(_RangeFile(url), buffer_size=1 << 20))
    want = f"`{code}`\t`{section}.`"
    for line in z.read("LAW_SECTION_TBL.dat").decode("utf-8").splitlines():
        if want in line:
            cols = line.split("\t")
            history, lob = cols[13].strip("`"), cols[14]
            break
    else:
        raise SystemExit(f"{code} {section} not found in {url}")
    text = caml_to_text(z.read(lob).decode("utf-8"))
    header = (
        f"California {code} Code Section {section}\n"
        f"Source: Legislative Counsel of California, {url} (LAW_SECTION_TBL, {lob}), "
        f"read {datetime.now(UTC).date().isoformat()}\n{history}\n\n{section}.\n"
    )
    with open(out, "w", encoding="utf-8") as f:
        f.write(header + text)
    print(f"wrote {out}: {history}")


if __name__ == "__main__":
    main(*sys.argv[1:])
