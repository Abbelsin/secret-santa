#!/usr/bin/env python3
"""
Secret Santa – lottning från Google Forms-CSV, krypterad avslöjar-sida på GitHub Pages,
och utskick av emoji-koder via Gmail.

Flöde:
  python3 santa.py kolla                 Läs in CSV + config, visa deltagare/budget (ingen lottning)
  python3 santa.py testmejl DIN@ADRESS   Kolla att Gmail-inloggningen funkar
  python3 santa.py lotta                 Lotta och skriv data.json (krypterad). Visar aldrig vem som har vem.
  git add data.json && git commit -m "Lottning" && git push
  python3 santa.py skicka                Mejla ut koderna (kollar först att sidan har nya data.json)
  python3 santa.py skicka-igen NAMN      Skicka samma kod igen till NAMN

Kräver Python 3.11+ (för tomllib). Inga andra beroenden.
App-lösenordet läses från miljövariabeln SANTA_APP_PASSWORD, annars frågar skriptet.
"""

import argparse
import base64
import csv
import getpass
import hashlib
import hmac
import imaplib
import json
import os
import random
import re
import secrets
import smtplib
import statistics
import sys
import tomllib
import urllib.request
import uuid
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.toml"
DRAW_PATH = HERE / "lottning.dat"   # obfuskerad, så du inte råkar läsa den av misstag
DATA_PATH = HERE / "data.json"      # det som publiceras på sidan (krypterat)

PALETTE = ["⛄", "🎅", "🎄", "🎁", "⭐", "🦌", "🍪", "🔔", "🧦", "🍬", "🌟", "🧤", "🍭", "🧣", "🛷"]
CODE_LENGTH = 3
PBKDF2_ITER = 250_000   # gör det långsamt att gissa alla 3375 koder, men snabbt nog på en mobil

rng = random.SystemRandom()


# ---------------------------------------------------------------- config & CSV

def load_config():
    if not CONFIG_PATH.exists():
        sys.exit(f"Hittar inte {CONFIG_PATH.name} – kopiera config.example.toml till config.toml och fyll i.")
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def find_column(headers, override, keywords, required=True):
    if override:
        if override not in headers:
            sys.exit(f"Kolumnen '{override}' från config finns inte i CSV:n. Kolumner: {headers}")
        return override
    for h in headers:
        hl = h.lower()
        if any(k in hl for k in keywords):
            return h
    if required:
        sys.exit(f"Hittar ingen kolumn som matchar {keywords}. Kolumner: {headers}\n"
                 f"Ange kolumnnamnet i [kolumner] i config.toml.")
    return None


def load_participants(cfg):
    csv_path = (HERE / cfg["csv_fil"]).expanduser()
    if not csv_path.exists():
        sys.exit(f"Hittar inte CSV-filen: {csv_path}")
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit("CSV-filen är tom.")

    headers = list(rows[0].keys())
    col = cfg.get("kolumner", {})
    c_name = find_column(headers, col.get("namn"), ["namn", "name"])
    c_mail = find_column(headers, col.get("epost"), ["e-post", "epost", "mejl", "mail", "email"])
    c_budget = find_column(headers, col.get("budget"), ["budget"], required=False)
    c_wish = find_column(headers, col.get("onskemal"), ["önsk", "onsk", "tips"], required=False)
    c_nope = find_column(headers, col.get("inte_ha"), ["inte ha", "inte vill", "undvik"], required=False)

    # Senaste svaret per (namn, mejladress) vinner om någon fyllt i två gånger.
    # Flera namn på samma adress är okej – t.ex. mamma som fyller i åt mormor.
    # Då får adressen ett mejl per person.
    people = {}
    for r in rows:
        email = (r.get(c_mail) or "").strip().lower()
        name = (r.get(c_name) or "").strip()
        if not email or not name:
            continue
        people[(name.lower(), email)] = {
            "namn": name,
            "epost": email,
            "budget": (r.get(c_budget) or "").strip() if c_budget else "",
            "onskemal": (r.get(c_wish) or "").strip() if c_wish else "",
            "inte_ha": (r.get(c_nope) or "").strip() if c_nope else "",
        }

    plist = list(people.values())
    names = [p["namn"].lower() for p in plist]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        sys.exit(f"Flera personer har samma namn: {', '.join(dupes)}. Be dem skriva efternamn/initial.")
    return plist


def decide_budget(cfg, people):
    if cfg.get("budget"):
        return int(cfg["budget"])
    votes = []
    for p in people:
        m = re.search(r"\d[\d\s]*", p["budget"])
        if m:
            votes.append(int(m.group().replace(" ", "")))
    if not votes:
        sys.exit("Inga budgetsvar hittades – sätt 'budget' i config.toml.")
    return statistics.median_low(votes)  # medianen, och alltid ett belopp någon faktiskt valt


def exclusion_set(cfg, people):
    known = {p["namn"].lower() for p in people}
    excl = set()
    for pair in cfg.get("far_inte_dra_varandra", []):
        a, b = (x.strip().lower() for x in pair)
        for n in (a, b):
            if n not in known:
                sys.exit(f"'{n}' i far_inte_dra_varandra matchar ingen deltagare. "
                         f"Deltagare: {', '.join(sorted(known))}")
        excl.add((a, b))
        excl.add((b, a))
    # Personer med samma mejladress (t.ex. mamma som fyllt i åt mormor) får inte dra
    # varandra – annars ser den som läser mejlen båda sidor av paret.
    for p in people:
        for q in people:
            if p is not q and p["epost"] == q["epost"]:
                excl.add((p["namn"].lower(), q["namn"].lower()))
    return excl


# ---------------------------------------------------------------- lottning

def draw(people, excl, avoid_mutual):
    givers = [p["namn"].lower() for p in people]
    if len(givers) < 3:
        sys.exit("Det behövs minst 3 deltagare.")
    for _ in range(100_000):
        receivers = givers[:]
        rng.shuffle(receivers)
        pairs = dict(zip(givers, receivers))
        if any(g == r for g, r in pairs.items()):
            continue
        if any((g, r) in excl for g, r in pairs.items()):
            continue
        if avoid_mutual and any(pairs[r] == g for g, r in pairs.items()):
            continue
        return pairs
    sys.exit("Hittade ingen giltig lottning – för många regler? Prova att ta bort några "
             "eller sätt undvik_att_dra_varandra = false om den är på.")


def make_codes(n):
    if n > len(PALETTE) ** CODE_LENGTH:
        sys.exit("För många deltagare för kodlängden.")
    codes = set()
    while len(codes) < n:
        codes.add(tuple(rng.randrange(len(PALETTE)) for _ in range(CODE_LENGTH)))
    codes = list(codes)
    rng.shuffle(codes)
    return codes


def code_str(idx):
    return "".join(PALETTE[i] for i in idx)


def save_draw(data):
    raw = json.dumps(data, ensure_ascii=False).encode()
    DRAW_PATH.write_bytes(base64.b85encode(raw[::-1]))
    os.chmod(DRAW_PATH, 0o600)


def load_draw():
    if not DRAW_PATH.exists():
        sys.exit("Ingen lottning sparad än – kör 'lotta' först.")
    return json.loads(base64.b85decode(DRAW_PATH.read_bytes())[::-1])


# ---------------------------------------------------------------- kryptering (måste matcha index.html)
# PBKDF2-SHA256(kod) -> 32 B krypteringsnyckel + 32 B MAC-nyckel.
# Chiffer: keystream = HMAC(ek, nonce || räknare), XOR. Tagg: HMAC(mk, nonce || ct)[:16].

def derive_keys(idx, salt):
    pw = ",".join(str(i) for i in idx).encode()
    k = hashlib.pbkdf2_hmac("sha256", pw, salt, PBKDF2_ITER, dklen=64)
    return k[:32], k[32:]


def encrypt(idx, salt, obj):
    ek, mk = derive_keys(idx, salt)
    pt = json.dumps(obj, ensure_ascii=False).encode()
    nonce = secrets.token_bytes(16)
    ks = b""
    i = 0
    while len(ks) < len(pt):
        ks += hmac.new(ek, nonce + i.to_bytes(4, "big"), hashlib.sha256).digest()
        i += 1
    ct = bytes(a ^ b for a, b in zip(pt, ks))
    tag = hmac.new(mk, nonce + ct, hashlib.sha256).digest()[:16]
    b64 = lambda b: base64.b64encode(b).decode()
    return {"n": b64(nonce), "c": b64(ct), "t": b64(tag)}


def build_site_data(pairs_with_codes, budget):
    salt = secrets.token_bytes(16)
    entries = []
    for giver, receiver, idx in pairs_with_codes:
        entries.append(encrypt(idx, salt, {
            "fran": giver["namn"],
            "till": receiver["namn"],
            "budget": budget,
            "onskemal": receiver["onskemal"],
            "inte_ha": receiver["inte_ha"],
        }))
    rng.shuffle(entries)
    return {
        "v": 1,
        "salt": base64.b64encode(salt).decode(),
        "iter": PBKDF2_ITER,
        "palette": PALETTE,
        "codeLength": CODE_LENGTH,
        "entries": entries,
    }


# ---------------------------------------------------------------- mejl

def password():
    pw = os.environ.get("SANTA_APP_PASSWORD") or getpass.getpass("Gmail app-lösenord: ")
    return pw.replace(" ", "")


def build_mail(cfg, giver, idx, run_id):
    msg = EmailMessage()
    msg["From"] = f"{cfg.get('avsandarnamn', 'Tomten')} <{cfg['gmail']}>"
    msg["To"] = giver["epost"]
    msg["Subject"] = cfg.get("amne", "🎅 Din Secret Santa-kod!")
    msg["Message-ID"] = make_msgid(idstring=run_id, domain="santa.local")
    body = [
        f"Hej {giver['namn']}!",
        "",
        "Lottningen är gjord! 🎄",
        "",
        "Din hemliga kod är:",
        "",
        f"        {code_str(idx)}",
        "",
        f"Gå in på {cfg['sida_url']} och knappa in koden",
        "för att se vem du ska ge en julklapp till.",
        "",
        cfg.get("extra_text", "Ta med klappen till julafton!"),
        "",
        "Håll det hemligt! 🤫",
        "/Tomten",
    ]
    msg.set_content("\n".join(body))
    return msg


def send_all(cfg, msgs):
    pw = password()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(cfg["gmail"], pw)
        for m in msgs:
            s.send_message(m)
    return pw


def find_special_folder(imap, flag):
    typ, data = imap.list()
    for line in data:
        line = line.decode()
        if flag in line:
            return line.split(' "/" ')[-1].strip()
    return None


def scrub_sent(cfg, pw, msgs):
    """Flytta de skickade mejlen till papperskorgen och töm dem därifrån (Gmail-specifikt)."""
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com")
        imap.login(cfg["gmail"], pw)
        sent = find_special_folder(imap, "\\Sent")
        trash = find_special_folder(imap, "\\Trash")
        if not sent or not trash:
            raise RuntimeError("hittade inte Skickat/Papperskorg via IMAP")
        ids = [m["Message-ID"].strip("<>") for m in msgs]

        imap.select(sent)
        for mid in ids:
            typ, data = imap.uid("SEARCH", "X-GM-RAW", f'"rfc822msgid:{mid}"')
            for uid in data[0].split():
                imap.uid("STORE", uid, "+X-GM-LABELS", "\\Trash")
        imap.expunge()

        imap.select(trash)
        for mid in ids:
            typ, data = imap.uid("SEARCH", "X-GM-RAW", f'"rfc822msgid:{mid}"')
            for uid in data[0].split():
                imap.uid("STORE", uid, "+FLAGS", "\\Deleted")
        imap.expunge()
        imap.logout()
        print("🧹 Rensade bort mejlen från Skickat och papperskorgen.")
    except Exception as e:
        print(f"⚠️  Kunde inte rensa Skickat automatiskt ({e}).\n"
              f"   Titta INTE i Skickat – markera allt där och radera, töm sedan papperskorgen.")


def check_published(cfg, salt):
    url = cfg["sida_url"].rstrip("/") + f"/data.json?nocache={uuid.uuid4().hex}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            live = json.load(r)
    except Exception as e:
        return False, f"kunde inte hämta {url} ({e})"
    if live.get("salt") != salt:
        return False, "sidan har inte den nya data.json än"
    return True, ""


# ---------------------------------------------------------------- kommandon

def cmd_kolla(cfg):
    people = load_participants(cfg)
    excl = exclusion_set(cfg, people)
    budget = decide_budget(cfg, people)
    print(f"{len(people)} deltagare:")
    for p in sorted(people, key=lambda p: p["namn"]):
        print(f"  - {p['namn']:<20} {p['epost']:<35} budgetröst: {p['budget'] or '-'}")
    print(f"\nBudget som kommer användas: {budget} kr"
          + (" (från config)" if cfg.get("budget") else " (median av rösterna)"))
    print(f"Regler: {len(excl) // 2} par som inte får dra varandra")
    draw(people, excl, cfg.get("undvik_att_dra_varandra", False))  # bara test att det går, kastas
    print("✅ En giltig lottning är möjlig. Kör 'lotta' när alla har svarat.")


def cmd_testmejl(cfg, address):
    msg = EmailMessage()
    msg["From"] = f"{cfg.get('avsandarnamn', 'Tomten')} <{cfg['gmail']}>"
    msg["To"] = address
    msg["Subject"] = "Test från Secret Santa-skriptet"
    msg.set_content("Om du läser det här funkar inloggningen. 🎅")
    send_all(cfg, [msg])
    print(f"✅ Testmejl skickat till {address}.")


def cmd_lotta(cfg, force):
    if DRAW_PATH.exists() and not force:
        sys.exit("Det finns redan en lottning. Använd 'skicka-igen' för att skicka om en kod, "
                 "eller 'lotta --ny' för att lotta om från början (alla måste få nya koder).")
    people = load_participants(cfg)
    excl = exclusion_set(cfg, people)
    budget = decide_budget(cfg, people)
    pairs = draw(people, excl, cfg.get("undvik_att_dra_varandra", False))

    by_name = {p["namn"].lower(): p for p in people}
    codes = make_codes(len(pairs))
    triples = [(by_name[g], by_name[r], list(c)) for (g, r), c in zip(pairs.items(), codes)]

    site = build_site_data(triples, budget)
    DATA_PATH.write_text(json.dumps(site, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    save_draw({"budget": budget, "salt": site["salt"], "skickat": False,
               "par": [[g, r, c] for g, r, c in triples]})

    print(f"✅ Lottat {len(triples)} deltagare. Budget: {budget} kr.")
    print("   data.json är skriven (krypterad). Publicera den nu:\n")
    print('     git add data.json && git commit -m "Lottning" && git push\n')
    print("   Vänta en minut tills GitHub Pages uppdaterats, kör sedan: python3 santa.py skicka")


def cmd_skicka(cfg, force):
    data = load_draw()
    if data.get("skickat") and not force:
        sys.exit("Koderna är redan utskickade. Använd 'skicka-igen NAMN' för en person, "
                 "eller 'skicka --tvinga' för att skicka till alla igen.")
    ok, why = check_published(cfg, data["salt"])
    if not ok and not force:
        sys.exit(f"⏳ Avbryter: {why}.\n   Har du pushat data.json? Pages kan ta någon minut. "
                 f"Kör 'skicka --tvinga' för att skicka ändå.")
    run_id = uuid.uuid4().hex[:8]
    msgs = [build_mail(cfg, g, c, run_id) for g, r, c in data["par"]]
    pw = send_all(cfg, msgs)
    data["skickat"] = True
    save_draw(data)
    print(f"✅ {len(msgs)} koder skickade.")
    if cfg.get("rensa_skickat", True):
        scrub_sent(cfg, pw, msgs)


def cmd_skicka_igen(cfg, name):
    data = load_draw()
    for giver, receiver, idx in data["par"]:
        if giver["namn"].lower() == name.strip().lower():
            msg = build_mail(cfg, giver, idx, uuid.uuid4().hex[:8])
            pw = send_all(cfg, [msg])
            print(f"✅ Skickade om koden till {giver['namn']} ({giver['epost']}).")
            if cfg.get("rensa_skickat", True):
                scrub_sent(cfg, pw, [msg])
            return
    names = ", ".join(g["namn"] for g, _, _ in data["par"])
    sys.exit(f"Hittar ingen '{name}'. Deltagare: {names}")


def main():
    ap = argparse.ArgumentParser(description="Secret Santa")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("kolla")
    t = sub.add_parser("testmejl"); t.add_argument("adress")
    l = sub.add_parser("lotta"); l.add_argument("--ny", action="store_true")
    s = sub.add_parser("skicka"); s.add_argument("--tvinga", action="store_true")
    r = sub.add_parser("skicka-igen"); r.add_argument("namn")
    args = ap.parse_args()

    cfg = load_config()
    if args.cmd == "kolla":
        cmd_kolla(cfg)
    elif args.cmd == "testmejl":
        cmd_testmejl(cfg, args.adress)
    elif args.cmd == "lotta":
        cmd_lotta(cfg, args.ny)
    elif args.cmd == "skicka":
        cmd_skicka(cfg, args.tvinga)
    elif args.cmd == "skicka-igen":
        cmd_skicka_igen(cfg, args.namn)


if __name__ == "__main__":
    main()
