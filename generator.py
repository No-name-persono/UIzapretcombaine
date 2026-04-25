"""
generator.py — Генератор стратегий для Zapret2 Manager

Включает:
  1. FLOWSEAL_PRESETS — готовые стратегии из Flowseal/zapret-discord-youtube,
     адаптированные под winws2 с --lua-desync (nfqws2 формат)
  2. StrategyGenerator — комбинаторный генератор для автотестирования
  3. StrategyTester — тестер стратегий через winws2 + curl

Источник стратегий: https://github.com/Flowseal/zapret-discord-youtube
Адаптация: --dpi-desync → --lua-desync, fooling → lua параметры

Маппинг форматов:
  --dpi-desync=fake                    → --lua-desync=fake:blob=...:repeats=N
  --dpi-desync=multisplit              → --lua-desync=multisplit:pos=...:seqovl=...
  --dpi-desync=multidisorder           → --lua-desync=multidisorder:pos=...
  --dpi-desync=fake,fakedsplit         → fake:... + fakedsplit:...
  --dpi-desync=fake,multisplit         → fake:... + multisplit:...
  --dpi-desync=fake,multidisorder      → fake:... + multidisorder:...
  --dpi-desync=syndata,multidisorder   → syndata:... + multidisorder:...
  --dpi-desync=hostfakesplit           → hostfakesplit:...
  --dpi-desync-fooling=ts              → tcp_ts_up
  --dpi-desync-fooling=md5sig          → tcp_md5
  --dpi-desync-fooling=badseq          → tcp_seq=-10000
  --dpi-desync-autottl=N               → ip_autottl=-N,3-20
  --dpi-desync-repeats=N               → repeats=N
  --dpi-desync-split-seqovl=N          → seqovl=N
  --dpi-desync-fake-tls-mod=rnd,dupsid → tls_mod=rnd,dupsid
"""

import os
import sys
import subprocess
import shutil
import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple

log = logging.getLogger("generator")


# ══════════════════════════════════════════════════════
#  ОБЩИЕ БЛОКИ СТРАТЕГИЙ
# ══════════════════════════════════════════════════════

_WF_COMMON = [
    "--wf-tcp-out=80,443,2053,2083,2087,2096,8443",
    "--wf-udp-out=443,19294-19344,50000-50100",
]

_LUA_INIT = [
    "--lua-init=@zapret-lib.lua",
    "--lua-init=@zapret-antidpi.lua",
]

_QUIC_UDP_CHAIN = [
    "--filter-udp=443 --filter-l7=quic",
    "--payload=quic_initial",
    "--lua-desync=fake:blob=fake_default_quic:repeats=6",
]

_DISCORD_UDP_CHAIN = [
    "--new",
    "--filter-udp=19294-19344,50000-50100 --filter-l7=discord,stun",
    "--payload=discord_ip_discovery,stun",
    "--lua-desync=fake:blob=0x00000000000000000000000000000000:repeats=6",
]

_HTTP_CHAIN_AUTOTTL = [
    "--new",
    "--filter-tcp=80 --filter-l7=http",
    "--out-range=-d10",
    "--payload=http_req",
    "--lua-desync=fake:blob=fake_default_http:ip_autottl=-5,3-20:repeats=1",
    "--payload=empty --out-range=s1<d1",
    "--lua-desync=pktmod:ip_ttl=1",
]

_HTTP_CHAIN_SIMPLE = [
    "--new",
    "--filter-tcp=80 --filter-l7=http",
    "--out-range=-d10",
    "--payload=http_req",
    "--lua-desync=fake:blob=fake_default_http:repeats=6",
]


def _make_full(name, desc, tls_chain, http_chain=None, extra_wf=None):
    """Собирает полную многоцепочечную стратегию."""
    args = list(_WF_COMMON)
    if extra_wf:
        args.extend(extra_wf)
    args.extend(_LUA_INIT)
    args.extend(_QUIC_UDP_CHAIN)
    args.extend(_DISCORD_UDP_CHAIN)
    args.append("--new")
    args.extend(tls_chain)
    args.extend(http_chain or _HTTP_CHAIN_AUTOTTL)
    args.extend([
        "--new",
        "--filter-udp=443 --filter-l7=quic",
        "--payload=quic_initial",
        "--lua-desync=fake:blob=fake_default_quic:repeats=11",
    ])
    return {"name": name, "desc": desc, "args": args}


# ══════════════════════════════════════════════════════
#  FLOWSEAL PRESETS
# ══════════════════════════════════════════════════════

FLOWSEAL_PRESETS = [
    # 1. general.bat — multisplit seqovl=681
    _make_full(
        "Flowseal: multisplit seqovl=681",
        "Базовая Flowseal. TCP сегментация с overlap=681 и TLS pattern. Работает у большинства.",
        [
            "--filter-tcp=80,443,2053,2083,2087,2096,8443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=multisplit:pos=1:seqovl=681:seqovl_pattern=fake_default_tls",
        ], _HTTP_CHAIN_SIMPLE,
    ),
    # 2. ALT — fake+fakedsplit ts
    _make_full(
        "Flowseal ALT: fake+fakedsplit ts",
        "Фейк + разрезка с фейками, timestamp fooling. Если multisplit не работает.",
        [
            "--filter-tcp=80,443,2053,2083,2087,2096,8443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:tcp_ts_up:repeats=6",
            "--lua-desync=fakedsplit:pos=midsld:tcp_ts_up",
        ],
    ),
    # 3. ALT2 — multisplit seqovl=652
    _make_full(
        "Flowseal ALT2: multisplit seqovl=652",
        "Вариант multisplit: overlap=652, pos=2. Попробуйте если базовая не работает.",
        [
            "--filter-tcp=80,443,2053,2083,2087,2096,8443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=multisplit:pos=2:seqovl=652:seqovl_pattern=fake_default_tls",
        ], _HTTP_CHAIN_SIMPLE,
    ),
    # 4. ALT3 — autottl + md5sig/badseq
    _make_full(
        "Flowseal ALT3: autottl + md5sig/badseq",
        "Разные методы для HTTP и HTTPS. С автоматическим TTL. Классика.",
        [
            "--filter-tcp=443,2053,2083,2087,2096,8443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=multisplit:pos=1:tcp_seq=-10000:repeats=8",
        ],
        [
            "--new",
            "--filter-tcp=80 --filter-l7=http",
            "--out-range=-d10",
            "--payload=http_req",
            "--lua-desync=fake:blob=fake_default_http:ip_autottl=-2,3-20:tcp_md5:repeats=1",
            "--lua-desync=multisplit:pos=2",
        ],
    ),
    # 5. ALT5 — syndata+multidisorder (агрессивная)
    _make_full(
        "Flowseal ALT5: syndata+multidisorder",
        "АГРЕССИВНАЯ: данные в SYN-пакете + перемешивание. Только IPv4. Для тяжёлых DPI.",
        [
            "--filter-l3=ipv4",
            "--filter-tcp=80,443,2053,2083,2087,2096,8443",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=syndata:blob=fake_default_tls",
            "--lua-desync=multidisorder:pos=1,midsld",
        ],
    ),
    # 6. ALT6 — fake+disorder md5sig
    _make_full(
        "Flowseal ALT6: fake md5sig + disorder",
        "Fake с TCP MD5 + multidisorder. Ростелеком/МТС.",
        [
            "--filter-tcp=80,443,2053,2083,2087,2096,8443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:tcp_md5:repeats=6",
            "--lua-desync=multidisorder:pos=1,midsld",
        ],
    ),
    # 7. ALT7 — fake+multisplit ts seqovl
    _make_full(
        "Flowseal ALT7: fake ts + multisplit",
        "Fake ts + multisplit с seqovl. Эффективна для YouTube.",
        [
            "--filter-tcp=80,443,2053,2083,2087,2096,8443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:tcp_ts_up:repeats=8",
            "--lua-desync=multisplit:pos=1:seqovl=681:seqovl_pattern=fake_default_tls",
        ],
    ),
    # 8. ALT9 — hostfakesplit
    _make_full(
        "Flowseal ALT9: hostfakesplit",
        "Разрезка по границам хоста с фейковым доменом. Уникальная техника.",
        [
            "--filter-tcp=80,443,2053,2083,2087,2096,8443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=hostfakesplit:tcp_ts_up:tcp_md5:repeats=4",
        ],
    ),
    # 9. ALT10 — простой fake ts
    _make_full(
        "Flowseal ALT10: simple fake ts",
        "Самая простая: чистый fake с timestamp. Начните с неё.",
        [
            "--filter-tcp=80,443,2053,2083,2087,2096,8443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:tcp_ts_up:repeats=6",
        ],
    ),
    # 10. ALT11 — fake+multisplit двойной
    _make_full(
        "Flowseal ALT11: fake+multisplit double",
        "Двойной fake + multisplit. Усиленная для глубокого DPI.",
        [
            "--filter-tcp=80,443,2053,2083,2087,2096,8443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:tcp_ts_up:repeats=8",
            "--lua-desync=multisplit:pos=1:seqovl=654:seqovl_pattern=fake_default_tls",
        ],
    ),
    # 11. FAKE TLS AUTO — rnd+dupsid
    _make_full(
        "Flowseal FAKE TLS AUTO: rnd+dupsid",
        "Fake с рандомизацией TLS + disorder. Для ТСПУ (продвинутый DPI).",
        [
            "--filter-tcp=80,443,2053,2083,2087,2096,8443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:tcp_seq=-10000:tls_mod=rnd,dupsid:repeats=11",
            "--lua-desync=multidisorder:pos=1,midsld",
        ],
    ),
    # 12. FAKE TLS AUTO ALT — fakedsplit badseq
    _make_full(
        "Flowseal FAKE TLS AUTO ALT: fakedsplit",
        "Fake badseq + fakedsplit + TLS рандомизация. Альтернатива для ТСПУ.",
        [
            "--filter-tcp=80,443,2053,2083,2087,2096,8443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:tcp_seq=-10000:tls_mod=rnd,dupsid:repeats=8",
            "--lua-desync=fakedsplit:pos=1:tcp_seq=-10000",
        ],
    ),
    # 13. SIMPLE FAKE — минимальный
    _make_full(
        "Flowseal SIMPLE FAKE",
        "Минимальная: один fake ts. Самая лёгкая по ресурсам.",
        [
            "--filter-tcp=80,443,2053,2083,2087,2096,8443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:tcp_ts_up:repeats=6",
        ], _HTTP_CHAIN_SIMPLE,
    ),
    # 14. Комбо: autottl + orig-ttl
    _make_full(
        "Комбо: fake autottl + orig-ttl=1",
        "Проверенная для РФ: fake autottl, оригинал с TTL=1.",
        [
            "--filter-tcp=443,2053,2083,2087,2096,8443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:ip_autottl=-5,3-20:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
        ],
    ),
    # 15. Комбо: double fake autottl
    _make_full(
        "Комбо: double fake autottl + orig-ttl",
        "Два fake (пустой + TLS rnd,dupsid) + orig-ttl=1. Усиленная.",
        [
            "--filter-tcp=443,2053,2083,2087,2096,8443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=0x00000000:ip_autottl=-5,3-20:repeats=1",
            "--lua-desync=fake:blob=fake_default_tls:ip_autottl=-5,3-20:tls_mod=rnd,dupsid:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
        ],
    ),
    # 16. Комбо: wssize + fakedsplit
    _make_full(
        "Комбо: wssize + fakedsplit (TLS 1.2)",
        "Уменьшение TCP окна + fakedsplit. Для анализа TLS server hello. ЗАМЕДЛЯЕТ!",
        [
            "--filter-tcp=443,2053,2083,2087,2096,8443 --filter-l7=tls",
            "--out-range=-d10",
            "--lua-desync=wssize:wsize=1:scale=6",
            "--payload=tls_client_hello",
            "--lua-desync=fakedsplit:pos=midsld:ip_ttl=3:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
        ],
    ),
    # 17. Discord Focus
    _make_full(
        "Discord Focus: fake+disorder",
        "Оптимизировано для Discord: Cloudflare порты + голосовые.",
        [
            "--filter-tcp=443,2053,2083,2087,2096,8443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:ip_autottl=-5,3-20:repeats=6",
            "--lua-desync=multidisorder:pos=1,midsld",
        ],
        extra_wf=[
            '--wf-raw-part=@"windivert.filter\\windivert_part.discord_media.txt"',
            '--wf-raw-part=@"windivert.filter\\windivert_part.stun.txt"',
        ],
    ),
    # 18. Полный: все протоколы
    _make_full(
        "Полный: TLS+QUIC+Discord+VPN",
        "Всё в одном: YouTube, Discord голос, QUIC, WireGuard, STUN.",
        [
            "--filter-tcp=443,2053,2083,2087,2096,8443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:ip_autottl=-5,3-20:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
        ],
        extra_wf=[
            '--wf-raw-part=@"windivert.filter\\windivert_part.discord_media.txt"',
            '--wf-raw-part=@"windivert.filter\\windivert_part.stun.txt"',
            '--wf-raw-part=@"windivert.filter\\windivert_part.wireguard.txt"',
            '--wf-raw-part=@"windivert.filter\\windivert_part.quic_initial_ietf.txt"',
        ],
    ),
]


# ══════════════════════════════════════════════════════
#  FOOLING / SPLIT / TLS_MOD справочники
# ══════════════════════════════════════════════════════

FOOLING_METHODS = {
    "autottl": {"desc": "Авто-TTL", "params": ["ip_autottl=-5,3-20"]},
    "autottl_tight": {"desc": "Авто-TTL точный", "params": ["ip_autottl=-3,3-20"]},
    "ttl3": {"desc": "TTL=3", "params": ["ip_ttl=3"]},
    "ttl5": {"desc": "TTL=5", "params": ["ip_ttl=5"]},
    "ttl8": {"desc": "TTL=8", "params": ["ip_ttl=8"]},
    "md5sig": {"desc": "TCP MD5 Signature", "params": ["tcp_md5"]},
    "ts": {"desc": "Timestamp", "params": ["tcp_ts_up"]},
    "badseq": {"desc": "Bad TCP sequence", "params": ["tcp_seq=-10000"]},
    "badsum": {"desc": "Bad TCP checksum", "params": ["badsum"]},
}

SPLIT_POSITIONS = {
    "1": "Позиция 1", "2": "Позиция 2",
    "midsld": "Середина SLD", "sniext+1": "После SNI ext",
    "1,midsld": "1 + середина SLD",
}

TLS_MODS = {
    "rnd": ["tls_mod=rnd"],
    "rnd_dupsid": ["tls_mod=rnd,dupsid"],
    "dupsid": ["tls_mod=dupsid"],
}


@dataclass
class StrategyCandidate:
    """Кандидат стратегии для тестирования."""
    name: str
    desc: str
    tls_args: List[str]
    http_args: Optional[List[str]] = None
    priority: int = 50
    category: str = "general"
    source: str = "generated"

    def full_tls_args(self):
        return ["--filter-tcp=443 --filter-l7=tls", "--out-range=-d10"] + self.tls_args


# ══════════════════════════════════════════════════════
#  КОМБИНАТОРНЫЙ ГЕНЕРАТОР
# ══════════════════════════════════════════════════════

class StrategyGenerator:

    def __init__(self):
        self.log = logging.getLogger("strategy_gen")

    def generate_all(self, include_risky=False, include_slow=False):
        c = []
        c.extend(self._gen_flowseal_candidates())
        c.extend(self._gen_orig_ttl())
        c.extend(self._gen_fake())
        c.extend(self._gen_fake_split())
        c.extend(self._gen_fake_disorder())
        c.extend(self._gen_double_fake())
        c.extend(self._gen_faked_split())
        c.extend(self._gen_hostfakesplit())
        c.extend(self._gen_pure_split())
        if include_slow: c.extend(self._gen_wssize())
        if include_risky: c.extend(self._gen_risky())
        c.sort(key=lambda x: -x.priority)
        self.log.info(f"Generated {len(c)} candidates")
        return c

    def _gen_flowseal_candidates(self):
        items = [
            ("FS: multisplit seqovl=681", 97,
             ["--payload=tls_client_hello",
              "--lua-desync=multisplit:pos=1:seqovl=681:seqovl_pattern=fake_default_tls"]),
            ("FS: simple fake ts r=6", 96,
             ["--payload=tls_client_hello",
              "--lua-desync=fake:blob=fake_default_tls:tcp_ts_up:repeats=6"]),
            ("FS: multisplit seqovl=652", 93,
             ["--payload=tls_client_hello",
              "--lua-desync=multisplit:pos=2:seqovl=652:seqovl_pattern=fake_default_tls"]),
            ("FS: fake+fakedsplit ts", 91,
             ["--payload=tls_client_hello",
              "--lua-desync=fake:blob=fake_default_tls:tcp_ts_up:repeats=6",
              "--lua-desync=fakedsplit:pos=midsld:tcp_ts_up"]),
            ("FS: fake ts + multisplit seqovl", 92,
             ["--payload=tls_client_hello",
              "--lua-desync=fake:blob=fake_default_tls:tcp_ts_up:repeats=8",
              "--lua-desync=multisplit:pos=1:seqovl=681:seqovl_pattern=fake_default_tls"]),
            ("FS: fake md5 + disorder", 89,
             ["--payload=tls_client_hello",
              "--lua-desync=fake:blob=fake_default_tls:tcp_md5:repeats=6",
              "--lua-desync=multidisorder:pos=1,midsld"]),
            ("FS: fake badseq rnd,dupsid + disorder", 87,
             ["--payload=tls_client_hello",
              "--lua-desync=fake:blob=fake_default_tls:tcp_seq=-10000:tls_mod=rnd,dupsid:repeats=11",
              "--lua-desync=multidisorder:pos=1,midsld"]),
            ("FS: fake badseq + fakedsplit", 85,
             ["--payload=tls_client_hello",
              "--lua-desync=fake:blob=fake_default_tls:tcp_seq=-10000:tls_mod=rnd,dupsid:repeats=8",
              "--lua-desync=fakedsplit:pos=1:tcp_seq=-10000"]),
            ("FS: hostfakesplit ts+md5", 83,
             ["--payload=tls_client_hello",
              "--lua-desync=hostfakesplit:tcp_ts_up:tcp_md5:repeats=4"]),
            ("FS: syndata+disorder", 78,
             ["--payload=tls_client_hello",
              "--lua-desync=syndata:blob=fake_default_tls",
              "--lua-desync=multidisorder:pos=1,midsld"]),
        ]
        return [StrategyCandidate(n, f"Из Flowseal: {n}", a, priority=p,
                                   category="flowseal", source="flowseal")
                for n, p, a in items]

    def _gen_orig_ttl(self):
        s = []
        for fn, fp, pr in [("autottl",["ip_autottl=-5,3-20"],94),("ts",["tcp_ts_up"],90),
                            ("autottl_tight",["ip_autottl=-3,3-20"],88),("md5sig",["tcp_md5"],72)]:
            p = ":".join(["fake","blob=fake_default_tls"]+fp+["repeats=1"])
            s.append(StrategyCandidate(f"fake {fn} + orig-ttl=1",f"Fake {fn}, оригинал TTL=1",
                ["--payload=tls_client_hello",f"--lua-desync={p}",
                 "--payload=empty --out-range=s1<d1","--lua-desync=pktmod:ip_ttl=1"],
                priority=pr,category="orig_ttl"))
        return s

    def _gen_fake(self):
        s = []
        for fn,fp,pr in [("autottl",["ip_autottl=-5,3-20"],88),("ts",["tcp_ts_up"],86),
                          ("md5sig",["tcp_md5"],73),("ttl5",["ip_ttl=5"],68),
                          ("badseq",["tcp_seq=-10000"],58)]:
            for r in [1,6]:
                p = ":".join(["fake","blob=fake_default_tls"]+fp+[f"repeats={r}"])
                s.append(StrategyCandidate(f"fake {fn} r={r}",f"Fake {fn}, {r} повт.",
                    ["--payload=tls_client_hello",f"--lua-desync={p}"],
                    priority=pr-(r>1)*3,category="fake"))
        return s

    def _gen_fake_split(self):
        s = []
        for fn,fp,pr in [("autottl",["ip_autottl=-5,3-20"],84),("ts",["tcp_ts_up"],82),
                          ("md5sig",["tcp_md5"],68)]:
            for pos in ["2","midsld","1","1,midsld"]:
                p = ":".join(["fake","blob=fake_default_tls"]+fp+["repeats=1"])
                s.append(StrategyCandidate(f"fake {fn} + split {pos}",f"Fake {fn} + split {pos}",
                    ["--payload=tls_client_hello",f"--lua-desync={p}",
                     f"--lua-desync=multisplit:pos={pos}"],
                    priority=pr-3,category="fake_split"))
        return s

    def _gen_fake_disorder(self):
        s = []
        for fn,fp,pr in [("autottl",["ip_autottl=-5,3-20"],82),("ts",["tcp_ts_up"],80),
                          ("md5sig",["tcp_md5"],66),("badseq",["tcp_seq=-10000"],58)]:
            for pos in ["midsld","1,midsld","2"]:
                p = ":".join(["fake","blob=fake_default_tls"]+fp+["repeats=1"])
                s.append(StrategyCandidate(f"fake {fn} + disorder {pos}",f"Fake {fn} + disorder {pos}",
                    ["--payload=tls_client_hello",f"--lua-desync={p}",
                     f"--lua-desync=multidisorder:pos={pos}"],
                    priority=pr-3,category="fake_disorder"))
        return s

    def _gen_double_fake(self):
        s = []
        for b1,f1,b2,f2,tm,pr in [
            ("0x00000000","autottl","fake_default_tls","autottl","rnd_dupsid",82),
            ("0x00000000","ts","fake_default_tls","ts","rnd",80),
            ("fake_default_tls","ttl3","fake_default_tls","autottl","none",66),
        ]:
            p1 = ":".join(["fake",f"blob={b1}"]+FOOLING_METHODS[f1]["params"]+["repeats=1"])
            p2p = ["fake",f"blob={b2}"]+FOOLING_METHODS[f2]["params"]
            if tm!="none": p2p.extend(TLS_MODS[tm])
            p2p.append("repeats=1")
            p2 = ":".join(p2p)
            nm = f"2x fake: {f1}+{f2}"+(f" {tm}" if tm!="none" else "")
            s.append(StrategyCandidate(nm,f"Два fake: {b1}/{f1} + {b2}/{f2}",
                ["--payload=tls_client_hello",f"--lua-desync={p1}",f"--lua-desync={p2}"],
                priority=pr,category="double_fake"))
        return s

    def _gen_faked_split(self):
        s = []
        for fn,fp,pr in [("ts",["tcp_ts_up"],76),("autottl",["ip_autottl=-5,3-20"],74),
                          ("md5sig",["tcp_md5"],68),("badseq",["tcp_seq=-10000"],54)]:
            for pos in ["midsld","2","1"]:
                for func in ["fakedsplit","fakeddisorder"]:
                    p = ":".join([func,f"pos={pos}"]+fp+["repeats=1"])
                    s.append(StrategyCandidate(f"{func} {pos} {fn}",f"{func} {pos} с {fn}",
                        ["--payload=tls_client_hello",f"--lua-desync={p}"],
                        priority=pr-2,category="faked_split"))
        return s

    def _gen_hostfakesplit(self):
        s = []
        for fn,fp,pr in [("ts",["tcp_ts_up"],74),("ts+md5",["tcp_ts_up","tcp_md5"],72),
                          ("autottl",["ip_autottl=-5,3-20"],70)]:
            s.append(StrategyCandidate(f"hostfakesplit {fn}",f"Разрезка по хосту с {fn}",
                ["--payload=tls_client_hello",
                 f"--lua-desync=hostfakesplit:{':'.join(fp)}:repeats=4"],
                priority=pr,category="hostfakesplit"))
        return s

    def _gen_pure_split(self):
        s = []
        for pos in ["2","midsld","1","1,midsld"]:
            s.append(StrategyCandidate(f"split {pos}",f"Чистая TCP сегментация {pos}",
                ["--payload=tls_client_hello",f"--lua-desync=multisplit:pos={pos}"],
                priority=50,category="split"))
        for pos in ["midsld","1,midsld"]:
            s.append(StrategyCandidate(f"disorder {pos}",f"TCP disorder {pos}",
                ["--payload=tls_client_hello",f"--lua-desync=multidisorder:pos={pos}"],
                priority=48,category="disorder"))
        return s

    def _gen_wssize(self):
        s = []
        for fn,fp,pr in [("autottl",["ip_autottl=-5,3-20"],58),("ttl3",["ip_ttl=3"],53)]:
            for func in ["fakedsplit","fakeddisorder"]:
                p = ":".join([func,"pos=midsld"]+fp+["repeats=1"])
                s.append(StrategyCandidate(f"wssize+{func} {fn}",f"WSSize+{func}. МЕДЛЕННО!",
                    ["--lua-desync=wssize:wsize=1:scale=6","--payload=tls_client_hello",
                     f"--lua-desync={p}","--payload=empty --out-range=s1<d1",
                     "--lua-desync=pktmod:ip_ttl=1"],
                    priority=pr,category="wssize"))
        return s

    def _gen_risky(self):
        return [StrategyCandidate(f"fake {fn}",f"Fake {fn} (рискованно)",
            ["--payload=tls_client_hello",
             f"--lua-desync={':'.join(['fake','blob=fake_default_tls']+fp+['repeats=1'])}"],
            priority=pr,category="risky")
            for fn,fp,pr in [("badsum",["badsum"],38),("badack",["tcp_flags_unset=ack"],33)]]


# ══════════════════════════════════════════════════════
#  ТЕСТЕР СТРАТЕГИЙ
# ══════════════════════════════════════════════════════

@dataclass
class TestResult:
    ok: bool = False
    time_ms: int = 0
    curl_code: int = -1
    http_code: str = ""
    error: str = ""


class StrategyTester:
    def __init__(self, winws_bin, lua_dir, work_dir=None):
        self.winws_bin = winws_bin
        self.lua_dir = lua_dir
        self.work_dir = work_dir or os.path.dirname(winws_bin)
        self.log = logging.getLogger("strategy_tester")

    def _resolve_lua(self, f):
        full = os.path.join(self.lua_dir, f)
        try: return os.path.relpath(full, self.work_dir)
        except ValueError: return full

    def _build_args(self, c):
        return ["--wf-tcp-out=443",
                f"--lua-init=@{self._resolve_lua('zapret-lib.lua')}",
                f"--lua-init=@{self._resolve_lua('zapret-antidpi.lua')}",
                ] + c.full_tls_args()

    def _flatten(self, args):
        flat = []
        for a in args:
            a = a.strip()
            if not a: continue
            parts = a.split(" --")
            if len(parts) > 1:
                flat.append(parts[0].strip())
                for p in parts[1:]: flat.append("--" + p.strip())
            else: flat.append(a)
        return flat

    def test_candidate(self, c, domain, timeout=5, max_ok_ms=4000):
        result = TestResult()
        flat = self._flatten(self._build_args(c))
        cmd = f'"{self.winws_bin}"'
        for a in flat:
            if '"' in a: cmd += f" {a}"
            elif " " in a: cmd += f' "{a}"'
            else: cmd += f" {a}"
        proc = None
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=self.work_dir, shell=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            time.sleep(0.8)
            if proc.poll() is not None:
                result.error = "winws2 crashed"; return result
            curl_bin = "curl"
            for cp in ["curl", os.path.join(self.work_dir, "..", "cygwin", "bin", "curl.exe")]:
                if shutil.which(cp) or os.path.isfile(cp): curl_bin = cp; break
            t0 = time.time()
            cr = subprocess.run([curl_bin, "-s", "-o", "NUL", "-w", "%{http_code}",
                "--max-time", str(timeout), f"https://{domain}"],
                capture_output=True, text=True, timeout=timeout + 3,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            elapsed = int((time.time() - t0) * 1000)
            result.time_ms = elapsed; result.curl_code = cr.returncode
            result.http_code = cr.stdout.strip()
            if cr.returncode == 0 and result.http_code and result.http_code[0] in ("2","3") and elapsed < max_ok_ms:
                result.ok = True
            elif elapsed >= max_ok_ms: result.error = f"slow ({elapsed}ms)"
        except subprocess.TimeoutExpired:
            result.error = "timeout"; result.curl_code = 28; result.time_ms = (timeout+3)*1000
        except Exception as e: result.error = str(e)
        finally:
            if proc and proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=3)
                except: proc.kill()
            try: subprocess.run(["taskkill", "/F", "/IM", "winws2.exe"],
                capture_output=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except: pass
            time.sleep(0.3)
        return result

    def test_candidates(self, candidates, domain, timeout=5, max_ok_ms=4000,
                        max_working=5, progress_cb=None, stop_flag=None):
        results, working = [], 0
        for i, c in enumerate(candidates):
            if stop_flag and stop_flag(): break
            if working >= max_working: break
            r = self.test_candidate(c, domain, timeout, max_ok_ms)
            results.append((c, r))
            if r.ok: working += 1
            if progress_cb:
                try: progress_cb(i, len(candidates), c, r)
                except: pass
        return results


# ══════════════════════════════════════════════════════
#  ПОСТРОЕНИЕ ПРОФИЛЯ
# ══════════════════════════════════════════════════════

def build_profile_from_candidate(candidate, hostlist_rel=None, include_http=True, include_quic=True):
    args = list(_WF_COMMON) + list(_LUA_INIT)
    if hostlist_rel: args.append(f'--hostlist="{hostlist_rel}"')
    args.extend(_QUIC_UDP_CHAIN)
    args.extend(_DISCORD_UDP_CHAIN)
    args.append("--new")
    args.extend(candidate.full_tls_args())
    if include_http: args.extend(_HTTP_CHAIN_AUTOTTL)
    if include_quic:
        args.extend(["--new", "--filter-udp=443 --filter-l7=quic",
                      "--payload=quic_initial", "--lua-desync=fake:blob=fake_default_quic:repeats=11"])
    return args


def get_categories_info():
    return {
        "flowseal": "Flowseal — проверенные стратегии из zapret-discord-youtube",
        "orig_ttl": "Orig-TTL — фейк + оригинал с минимальным TTL",
        "fake": "Fake — фейковые пакеты с разным fooling",
        "fake_split": "Fake+Split — фейк + TCP сегментация",
        "fake_disorder": "Fake+Disorder — фейк + перестановка порядка",
        "double_fake": "Double Fake — два фейка с разными параметрами",
        "faked_split": "Fakedsplit — разрезка с замешиванием фейков",
        "hostfakesplit": "Hostfakesplit — разрезка по границам хоста",
        "split": "Split — чистая TCP сегментация",
        "disorder": "Disorder — чистая перестановка",
        "wssize": "WSSize — уменьшение TCP окна (медленно!)",
        "risky": "Рискованные — badsum/badack",
    }


def get_flowseal_presets():
    """Возвращает список готовых Flowseal стратегий."""
    return FLOWSEAL_PRESETS
