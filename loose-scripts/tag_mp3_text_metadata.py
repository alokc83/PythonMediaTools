#!/usr/bin/env python3
import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, COMM, TCON, TDRC, TLAN, TPUB, TXXX


@dataclass
class BookQuery:
    title: str
    author: str


@dataclass
class BookMeta:
    title: str = ""
    authors: List[str] = None

    subtitle: str = ""
    narrators: List[str] = None
    publisher: str = ""
    published_date: str = ""
    language: str = ""
    description: str = ""

    genres: List[str] = None
    tags: List[str] = None

    isbn10: str = ""
    isbn13: str = ""
    rating: str = ""
    rating_count: str = ""
    source: str = ""
    source_url: str = ""

    def __post_init__(self):
        if self.authors is None:
            self.authors = []
        if self.narrators is None:
            self.narrators = []
        if self.genres is None:
            self.genres = []
        if self.tags is None:
            self.tags = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "authors": self.authors,
            "subtitle": self.subtitle,
            "narrators": self.narrators,
            "publisher": self.publisher,
            "published_date": self.published_date,
            "language": self.language,
            "description": self.description,
            "genres": self.genres,
            "tags": self.tags,
            "isbn10": self.isbn10,
            "isbn13": self.isbn13,
            "rating": self.rating,
            "rating_count": self.rating_count,
            "source": self.source,
            "source_url": self.source_url,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "BookMeta":
        bm = BookMeta()
        for k, v in d.items():
            setattr(bm, k, v)
        bm.__post_init__()
        return bm


def norm_space(s: str) -> str:
    s = s.replace("_", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def uniq_ci(values: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for v in values:
        vv = norm_space(str(v))
        if not vv:
            continue
        k = vv.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(vv)
    return out


def join_values(values: List[str]) -> str:
    return ";".join([v for v in values if norm_space(v)])


def shorten_description(s: str, limit: int = 900) -> str:
    s = re.sub(r"\s+", " ", (s or "")).strip()
    if len(s) <= limit:
        return s
    return s[:limit].rstrip() + "..."


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return s


def cache_key(q: BookQuery, region: str) -> str:
    return f"{region.lower().strip()}|{q.title.lower().strip()}|{q.author.lower().strip()}"


def guess_from_filename(p: Path) -> BookQuery:
    name = norm_space(p.stem)
    name = re.sub(r"\((.*?)\)", "", name)
    name = re.sub(r"\[(.*?)\]", "", name)
    name = re.sub(
        r"\b(abridged|unabridged|audiobook|audio book|summary|blinkist)\b",
        "",
        name,
        flags=re.I,
    )
    name = norm_space(name)

    parts = [x.strip() for x in name.split(" - ") if x.strip()]
    if len(parts) >= 2:
        return BookQuery(title=" - ".join(parts[1:]), author=parts[0])
    return BookQuery(title=name, author="")


def read_query_from_mp3(p: Path) -> BookQuery:
    title = ""
    author = ""
    try:
        tags = EasyID3(str(p))
        if tags.get("title"):
            title = tags["title"][0].strip()
        if tags.get("artist"):
            author = tags["artist"][0].strip()
        elif tags.get("albumartist"):
            author = tags["albumartist"][0].strip()
    except Exception:
        pass

    if not title:
        g = guess_from_filename(p)
        title = g.title
        if not author:
            author = g.author

    return BookQuery(title=title, author=author)


def parse_json_ld(soup: BeautifulSoup) -> List[dict]:
    out: List[dict] = []
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            txt = tag.get_text(strip=True)
            if not txt:
                continue
            data = json.loads(txt)
            if isinstance(data, list):
                out.extend([x for x in data if isinstance(x, dict)])
            elif isinstance(data, dict):
                out.append(data)
        except Exception:
            continue
    return out


def meta_og(soup: BeautifulSoup, prop: str) -> str:
    m = soup.select_one(f'meta[property="{prop}"]')
    if m and m.get("content"):
        return m.get("content").strip()
    return ""


def audible_find_asin(session: requests.Session, q: BookQuery, region: str) -> Tuple[Optional[str], Optional[str]]:
    query = (q.title + " " + q.author).strip() if q.author else q.title
    if not query:
        return None, None

    base = f"https://www.audible.{region}" if region in ("uk", "in") else "https://www.audible.com"
    r = session.get(f"{base}/search", params={"keywords": query}, timeout=25)
    if r.status_code in (401, 403):
        return None, None
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    a = soup.select_one("a[href*='/pd/']")
    if not a:
        return None, None

    href = a.get("href", "")
    book_url = href if href.startswith("http") else base + href

    m = re.search(r"/pd/[^/]+/([A-Z0-9]{10})", book_url)
    if not m:
        m = re.search(r"/([A-Z0-9]{10})(?:\?|$)", book_url)
    asin = m.group(1) if m else None

    return asin, book_url


def provider_blinkist(session: requests.Session, q: BookQuery, max_genres: int) -> Optional[BookMeta]:
    if not q.title:
        return None

    r = session.get("https://www.blinkist.com/en/search", params={"query": q.title}, timeout=25)
    if r.status_code in (401, 403):
        return None
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    a = soup.select_one("a[href*='/en/nuggets/'], a[href*='/en/books/']")
    if not a:
        return None

    href = a.get("href", "")
    page_url = href if href.startswith("http") else "https://www.blinkist.com" + href

    r2 = session.get(page_url, timeout=25)
    if r2.status_code in (401, 403):
        return None
    r2.raise_for_status()

    soup2 = BeautifulSoup(r2.text, "html.parser")

    og_title = meta_og(soup2, "og:title")
    og_desc = meta_og(soup2, "og:description")

    title = norm_space(og_title.replace("| Blinkist", "")) if og_title else ""
    description = shorten_description(og_desc) if og_desc else ""

    authors: List[str] = []
    genres: List[str] = []

    for obj in parse_json_ld(soup2):
        t = (obj.get("@type") or "").lower()
        if "book" in t or t == "product":
            name = obj.get("name")
            if isinstance(name, str) and not title:
                title = norm_space(name)

            author_obj = obj.get("author")
            if isinstance(author_obj, dict) and isinstance(author_obj.get("name"), str):
                authors.append(author_obj["name"])
            elif isinstance(author_obj, list):
                for x in author_obj:
                    if isinstance(x, dict) and isinstance(x.get("name"), str):
                        authors.append(x["name"])

            cat = obj.get("category")
            if isinstance(cat, str):
                genres.append(cat)
            elif isinstance(cat, list):
                genres.extend([str(x) for x in cat if str(x).strip()])

    bm = BookMeta(
        title=title,
        authors=uniq_ci(authors),
        description=description,
        genres=uniq_ci(genres)[:max_genres],
        source="blinkist",
        source_url=page_url,
    )

    if not any([bm.title, bm.authors, bm.description, bm.genres]):
        return None
    return bm


def provider_audnexus(session: requests.Session, q: BookQuery, region: str, max_genres: int) -> Optional[BookMeta]:
    asin, audible_url = audible_find_asin(session, q, region=region)
    if not asin:
        return None

    url = f"https://api.audnex.us/books/{asin}"
    r = session.get(url, params={"region": region}, timeout=25)
    if r.status_code in (401, 403):
        return None
    if r.status_code == 404:
        return None
    r.raise_for_status()

    data = r.json() or {}

    title = norm_space(str(data.get("title") or ""))
    description = shorten_description(str(data.get("description") or "")) or shorten_description(str(data.get("summary") or ""))

    authors = [a.get("name") for a in (data.get("authors") or []) if isinstance(a, dict) and a.get("name")]
    narrators = [n.get("name") for n in (data.get("narrators") or []) if isinstance(n, dict) and n.get("name")]

    publisher = norm_space(str(data.get("publisherName") or ""))
    release_date = norm_space(str(data.get("releaseDate") or ""))
    language = norm_space(str(data.get("language") or ""))

    isbn_raw = norm_space(str(data.get("isbn") or ""))
    isbn10 = ""
    isbn13 = ""
    if isbn_raw:
        if len(isbn_raw) == 10:
            isbn10 = isbn_raw
        elif len(isbn_raw) == 13:
            isbn13 = isbn_raw

    rating = norm_space(str(data.get("rating") or ""))
    rating_count = norm_space(str(data.get("ratingsCount") or data.get("ratingCount") or ""))

    genres: List[str] = []
    tags: List[str] = []
    for g in (data.get("genres") or []):
        if not isinstance(g, dict):
            continue
        name = norm_space(str(g.get("name") or ""))
        typ = norm_space(str(g.get("type") or "")).lower()
        if not name:
            continue
        if typ == "genre":
            genres.append(name)
        elif typ == "tag":
            tags.append(name)
        else:
            tags.append(name)

    bm = BookMeta(
        title=title,
        authors=uniq_ci([a for a in authors if a]),
        narrators=uniq_ci([n for n in narrators if n]),
        publisher=publisher,
        published_date=release_date,
        language=language,
        description=description,
        genres=uniq_ci(genres)[:max_genres],
        tags=uniq_ci(tags)[:max_genres],
        isbn10=isbn10,
        isbn13=isbn13,
        rating=rating,
        rating_count=rating_count,
        source="audnexus",
        source_url=audible_url or "",
    )

    if not any([bm.title, bm.authors, bm.description, bm.genres, bm.tags, bm.narrators, bm.publisher, bm.published_date]):
        return None
    return bm


def provider_audible(session: requests.Session, q: BookQuery, region: str, max_genres: int) -> Optional[BookMeta]:
    asin, book_url = audible_find_asin(session, q, region=region)
    if not book_url:
        return None

    r2 = session.get(book_url, timeout=25)
    if r2.status_code in (401, 403):
        return None
    r2.raise_for_status()

    soup2 = BeautifulSoup(r2.text, "html.parser")

    og_title = meta_og(soup2, "og:title")
    og_desc = meta_og(soup2, "og:description")

    title = norm_space(og_title.replace("| Audible.com", "")) if og_title else ""
    description = shorten_description(og_desc) if og_desc else ""

    authors: List[str] = []
    narrators: List[str] = []
    publisher = ""
    published_date = ""
    genres: List[str] = []

    for obj in parse_json_ld(soup2):
        t = (obj.get("@type") or "").lower()
        if "book" in t or "audiobook" in t or t == "product":
            name = obj.get("name")
            if isinstance(name, str) and not title:
                title = norm_space(name)

            author_obj = obj.get("author")
            if isinstance(author_obj, dict) and isinstance(author_obj.get("name"), str):
                authors.append(author_obj["name"])
            elif isinstance(author_obj, list):
                for x in author_obj:
                    if isinstance(x, dict) and isinstance(x.get("name"), str):
                        authors.append(x["name"])

            pub = obj.get("publisher")
            if isinstance(pub, dict) and isinstance(pub.get("name"), str):
                publisher = pub["name"]

            date_pub = obj.get("datePublished")
            if isinstance(date_pub, str):
                published_date = date_pub

            cat = obj.get("category")
            if isinstance(cat, str):
                genres.append(cat)
            elif isinstance(cat, list):
                genres.extend([str(x) for x in cat if str(x).strip()])

    bm = BookMeta(
        title=title,
        authors=uniq_ci(authors),
        narrators=uniq_ci(narrators),
        publisher=publisher,
        published_date=published_date,
        description=description,
        genres=uniq_ci(genres)[:max_genres],
        source="audible",
        source_url=book_url,
    )

    if not any([bm.title, bm.authors, bm.description, bm.genres, bm.publisher, bm.published_date]):
        return None
    return bm


def provider_goodreads(session: requests.Session, q: BookQuery, max_genres: int) -> Optional[BookMeta]:
    query = (q.title + " " + q.author).strip() if q.author else q.title
    if not query:
        return None

    search_url = "https://www.goodreads.com/search?q=" + requests.utils.quote(query)
    r = session.get(search_url, timeout=25)
    if r.status_code in (401, 403):
        return None
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    book_url = None
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if "/book/show/" in href:
            book_url = href if href.startswith("http") else "https://www.goodreads.com" + href
            break
    if not book_url:
        return None

    r2 = session.get(book_url, timeout=25)
    if r2.status_code in (401, 403):
        return None
    r2.raise_for_status()

    soup2 = BeautifulSoup(r2.text, "html.parser")

    genres: List[str] = []
    for a in soup2.select("a[href*='/genres/']"):
        t = norm_space(a.get_text(" ", strip=True))
        if t:
            genres.append(t)
        if len(genres) >= max_genres:
            break

    if not genres:
        for a in soup2.select("a[href*='/shelf/show/']"):
            t = norm_space(a.get_text(" ", strip=True))
            if t:
                genres.append(t)
            if len(genres) >= max_genres:
                break

    desc = meta_og(soup2, "og:description")

    bm = BookMeta(
        genres=uniq_ci(genres)[:max_genres],
        tags=uniq_ci(genres)[:max_genres],
        description=shorten_description(desc) if desc else "",
        source="goodreads",
        source_url=book_url,
    )
    if not bm.genres and not bm.description:
        return None
    return bm


def provider_google_books(session: requests.Session, q: BookQuery, max_genres: int) -> Optional[BookMeta]:
    if not q.title:
        return None

    parts = [f'intitle:"{q.title}"']
    if q.author:
        parts.append(f'inauthor:"{q.author}"')
    query = " ".join(parts)

    url = "https://www.googleapis.com/books/v1/volumes"
    params = {"q": query, "maxResults": 5, "printType": "books"}
    r = session.get(url, params=params, timeout=25)
    r.raise_for_status()
    data = r.json()
    items = data.get("items", []) or []
    if not items:
        return None

    item = items[0]
    vi = item.get("volumeInfo", {}) or {}

    title = (vi.get("title") or "").strip()
    subtitle = (vi.get("subtitle") or "").strip()
    authors = [str(x).strip() for x in (vi.get("authors") or []) if str(x).strip()]
    publisher = (vi.get("publisher") or "").strip()
    published = (vi.get("publishedDate") or "").strip()
    description = shorten_description(vi.get("description") or "")
    language = (vi.get("language") or "").strip()

    cats = [norm_space(str(x)) for x in (vi.get("categories") or []) if norm_space(str(x))]
    cats = uniq_ci(cats)[:max_genres]

    isbn10 = ""
    isbn13 = ""
    for it in (vi.get("industryIdentifiers") or []):
        t = (it.get("type") or "").strip()
        v = (it.get("identifier") or "").strip()
        if t == "ISBN_10":
            isbn10 = v
        if t == "ISBN_13":
            isbn13 = v

    rating = str(vi.get("averageRating") or "").strip()
    rating_count = str(vi.get("ratingsCount") or "").strip()
    info_link = (vi.get("infoLink") or "").strip()

    return BookMeta(
        title=title,
        subtitle=subtitle,
        authors=authors,
        publisher=publisher,
        published_date=published,
        description=description,
        language=language,
        genres=cats,
        tags=cats,
        isbn10=isbn10,
        isbn13=isbn13,
        rating=rating,
        rating_count=rating_count,
        source="google_books",
        source_url=info_link,
    )


def merge_in_order(metas: List[Optional[BookMeta]]) -> BookMeta:
    def pick_text(field: str) -> str:
        for m in metas:
            if not m:
                continue
            v = getattr(m, field, "") or ""
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    def pick_list(field: str) -> List[str]:
        for m in metas:
            if not m:
                continue
            v = getattr(m, field, None) or []
            if isinstance(v, list) and len(v) > 0:
                return uniq_ci(v)
        return []

    out = BookMeta()
    out.title = pick_text("title")
    out.authors = pick_list("authors")

    out.subtitle = pick_text("subtitle")
    out.narrators = pick_list("narrators")
    out.publisher = pick_text("publisher")
    out.published_date = pick_text("published_date")
    out.language = pick_text("language")
    out.description = pick_text("description")

    out.genres = pick_list("genres")
    out.tags = pick_list("tags")

    out.isbn10 = pick_text("isbn10")
    out.isbn13 = pick_text("isbn13")
    out.rating = pick_text("rating")
    out.rating_count = pick_text("rating_count")
    out.source_url = pick_text("source_url")

    for m in metas:
        if m and m.source:
            out.source = m.source
            break

    return out


def set_txxx(id3: ID3, desc: str, value: str) -> None:
    id3.delall("TXXX:" + desc)
    if value:
        id3.add(TXXX(encoding=3, desc=desc, text=[value]))


def overwrite_text_metadata(mp3: Path, meta: BookMeta, tag_key: str) -> None:
    id3 = ID3(str(mp3))

    genres = uniq_ci(meta.genres or [])
    tags = uniq_ci(meta.tags or [])

    genre_value = join_values(genres)
    tag_value = join_values(tags) if tags else genre_value

    id3.delall("TCON")
    if genre_value:
        id3.add(TCON(encoding=3, text=[genre_value]))

    id3.delall("TDRC")
    if meta.published_date:
        id3.add(TDRC(encoding=3, text=[meta.published_date]))

    id3.delall("TPUB")
    if meta.publisher:
        id3.add(TPUB(encoding=3, text=[meta.publisher]))

    id3.delall("TLAN")
    if meta.language:
        id3.add(TLAN(encoding=3, text=[meta.language]))

    id3.delall("COMM")
    if meta.description:
        id3.add(COMM(encoding=3, lang="eng", desc="Description", text=shorten_description(meta.description)))

    set_txxx(id3, "Subtitle", meta.subtitle or "")
    set_txxx(id3, "Narrator", join_values(meta.narrators or []))
    set_txxx(id3, "ISBN10", meta.isbn10 or "")
    set_txxx(id3, "ISBN13", meta.isbn13 or "")
    set_txxx(id3, "Rating", meta.rating or "")
    set_txxx(id3, "RatingCount", meta.rating_count or "")
    set_txxx(id3, "Source", meta.source or "")
    set_txxx(id3, "SourceUrl", meta.source_url or "")

    set_txxx(id3, tag_key, tag_value)

    id3.save(v2_version=3)


def load_cache(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cache(path: Path, cache: Dict[str, Any]) -> None:
    path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="Root directory to scan")
    ap.add_argument("--dryrun", action="store_true")
    ap.add_argument("--tagkey", default="TAGS")
    ap.add_argument("--maxgenres", type=int, default=8)
    ap.add_argument("--sleepms", type=int, default=250)
    ap.add_argument("--cache", default="")
    ap.add_argument("--region", default="us")
    ap.add_argument(
        "--order",
        default="blinkist,audnexus,audible,goodreads,google_books",
        help="Comma separated provider order",
    )
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print("Root is not a directory")
        return 2

    order = [x.strip() for x in args.order.split(",") if x.strip()]
    valid = {"blinkist", "audnexus", "audible", "goodreads", "google_books"}
    for name in order:
        if name not in valid:
            print(f"Unknown provider in order: {name}")
            print("Valid providers: blinkist, audnexus, audible, goodreads, google_books")
            return 2

    session = make_session()

    cache_path = Path(args.cache).expanduser().resolve() if args.cache else (root / ".meta_cache.json")
    cache: Dict[str, Any] = load_cache(cache_path)

    mp3s: List[Path] = []
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if fn.lower().endswith(".mp3"):
                mp3s.append(Path(dp) / fn)

    def sleep():
        time.sleep(max(0.0, args.sleepms / 1000.0))

    total = 0
    updated = 0
    nomatch = 0
    errors = 0

    for mp3 in sorted(mp3s):
        total += 1
        q = read_query_from_mp3(mp3)
        if not q.title:
            nomatch += 1
            continue

        key = cache_key(q, args.region)
        entry = cache.get(key, {})

        metas: List[Optional[BookMeta]] = []

        for prov in order:
            cached = entry.get(prov)
            bm = BookMeta.from_dict(cached) if isinstance(cached, dict) and cached else None
            if bm is None:
                try:
                    if prov == "blinkist":
                        bm = provider_blinkist(session, q, args.maxgenres)
                    elif prov == "audnexus":
                        bm = provider_audnexus(session, q, args.region, args.maxgenres)
                    elif prov == "audible":
                        bm = provider_audible(session, q, args.region, args.maxgenres)
                    elif prov == "goodreads":
                        bm = provider_goodreads(session, q, args.maxgenres)
                    elif prov == "google_books":
                        bm = provider_google_books(session, q, args.max_genres)
                except Exception:
                    bm = None

                entry[prov] = bm.to_dict() if bm else {}
                cache[key] = entry
                sleep()

            metas.append(bm)

        final_meta = merge_in_order(metas)

        print(f"File: {mp3.name}")
        print(f"  search title: {q.title}")
        print(f"  search author: {q.author or '(none)'}")
        print(f"  order: {', '.join(order)}")
        print(f"  genres: {join_values(final_meta.genres) if final_meta.genres else '(none)'}")
        print(f"  tags: {join_values(final_meta.tags) if final_meta.tags else '(none)'}")
        print(f"  publisher: {final_meta.publisher or '(none)'}")
        print(f"  date: {final_meta.published_date or '(none)'}")
        print(f"  language: {final_meta.language or '(none)'}")
        print(f"  source: {final_meta.source or '(none)'}")
        print(f"  source url: {final_meta.source_url or '(none)'}")

        if args.dryrun:
            continue

        try:
            overwrite_text_metadata(mp3, final_meta, tag_key=args.tagkey)
            updated += 1
        except Exception as e:
            errors += 1
            print(f"  write failed: {e}")

    if not args.dryrun:
        try:
            save_cache(cache_path, cache)
        except Exception:
            pass

    print("")
    print(f"Files scanned: {total}")
    print(f"Files updated: {updated}")
    print(f"No match: {nomatch}")
    print(f"Errors: {errors}")
    print(f"Cache: {cache_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
