#!/usr/bin/env python3
"""
Stáhne Zboží feed (shop_zbozicz.xml) a produktům, jejichž <ITEM_ID> je v seznamu
nevýkonných, nastaví vlastní štítek (default CUSTOM_LABEL_1) na "nevykonne".
Výstup zapíše do souboru (OUT_PATH).

POZOR: CUSTOM_LABEL_1 je v Zboží feedu už obsazené (i-kódy skladem/dárek) – u
nevýkonných produktů se jeho hodnota PŘEPÍŠE na "nevykonne". To je záměr: Sklik
segmentuje produktové skupiny dle CUSTOM_LABEL_0/1, takže label musí být tam.

Streamově – feed (~702 MB) se nedrží celý v paměti, zpracovává se po položkách.

Konfigurace přes proměnné prostředí:
  NEVYKONNE_CSV_URL  (povinné)  – URL publikovaného CSV se seznamem nevýkonných ID
                                  (čte se 1. sloupec; hlavička se přeskočí)
  FEED_URL           (volitelné)– zdrojový Zboží feed
  OUT_PATH           (volitelné)– výstupní soubor
  LABEL_ELEMENT      (volitelné)– do kterého prvku label zapsat (default CUSTOM_LABEL_1)
  LABEL_VALUE        (volitelné)– hodnota labelu (default "nevykonne")
"""
import os
import re
import io
import csv
import sys
import urllib.request

FEED_URL          = os.environ.get("FEED_URL", "https://www.luxusnipradlo.cz/publicdoc/shop_zbozicz.xml")
NEVYKONNE_CSV_URL = os.environ["NEVYKONNE_CSV_URL"]
OUT_PATH          = os.environ.get("OUT_PATH", "shop_zbozicz_sklik.xml")
LABEL_ELEMENT     = os.environ.get("LABEL_ELEMENT", "CUSTOM_LABEL_1")
LABEL_VALUE       = os.environ.get("LABEL_VALUE", "nevykonne")

ITEM_ID_RE = re.compile(r"<ITEM_ID>\s*([^<]+?)\s*</ITEM_ID>")
LABEL_RE   = re.compile(r"(<%s>)(.*?)(</%s>)" % (re.escape(LABEL_ELEMENT), re.escape(LABEL_ELEMENT)), re.S)


def load_ids(url):
    """Načte množinu nevýkonných ID z publikovaného CSV (1. sloupec)."""
    ids = set()
    req = urllib.request.Request(url, headers={"User-Agent": "sklik-feed-transform"})
    with urllib.request.urlopen(req, timeout=120) as r:
        reader = csv.reader(io.TextIOWrapper(r, encoding="utf-8", errors="replace"))
        for i, row in enumerate(reader):
            if not row:
                continue
            val = row[0].strip()
            if i == 0 and not val.isdigit():   # přeskoč hlavičku
                continue
            if val:
                ids.add(val)
    return ids


def write_item(buf, ids, out):
    """Zapíše blok jedné položky; pokud její ITEM_ID je mezi nevýkonnými, nastaví
    LABEL_ELEMENT na LABEL_VALUE (nahradí hodnotu, nebo vloží, když prvek chybí).
    Vrací 1 pokud byl label nastaven, jinak 0."""
    block = "".join(buf)
    m = ITEM_ID_RE.search(block)
    item_id = m.group(1).strip() if m else None
    if not (item_id and item_id in ids):
        out.write(block)
        return 0

    new_block, n = LABEL_RE.subn(lambda mm: mm.group(1) + LABEL_VALUE + mm.group(3), block, count=1)
    if n == 0:                                   # prvek v položce není → vlož nový
        idx = new_block.rfind("</SHOPITEM>")
        if idx != -1:
            line = "    <%s>%s</%s>\n" % (LABEL_ELEMENT, LABEL_VALUE, LABEL_ELEMENT)
            new_block = new_block[:idx] + line + new_block[idx:]
    out.write(new_block)
    return 1


def main():
    ids = load_ids(NEVYKONNE_CSV_URL)
    print("Nevýkonných ID načteno: %d" % len(ids))
    print("Zapisuji label: <%s>%s</%s>" % (LABEL_ELEMENT, LABEL_VALUE, LABEL_ELEMENT))
    if not ids:
        print("VAROVÁNÍ: seznam ID je prázdný – výstup bude shodný se zdrojem.", file=sys.stderr)

    items = 0
    tagged = 0

    req = urllib.request.Request(FEED_URL, headers={"User-Agent": "sklik-feed-transform"})
    with urllib.request.urlopen(req, timeout=600) as resp, \
         open(OUT_PATH, "w", encoding="utf-8", newline="") as out:

        stream = io.TextIOWrapper(resp, encoding="utf-8", errors="replace")
        buf = []
        in_item = False

        for line in stream:
            if not in_item:
                if "<SHOPITEM>" in line:
                    in_item = True
                    buf = [line]
                    if "</SHOPITEM>" in line:       # kompaktní položka na jednom řádku
                        tagged += write_item(buf, ids, out)
                        items += 1
                        in_item = False
                        buf = []
                else:
                    out.write(line)                 # hlavička / patička feedu
            else:
                buf.append(line)
                if "</SHOPITEM>" in line:
                    tagged += write_item(buf, ids, out)
                    items += 1
                    in_item = False
                    buf = []

    print("Produktů zpracováno: %d, označeno (%s): %d" % (items, LABEL_ELEMENT, tagged))
    print("Výstup: %s" % OUT_PATH)


if __name__ == "__main__":
    main()
