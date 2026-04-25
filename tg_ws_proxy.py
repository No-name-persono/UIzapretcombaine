"""
tg_ws_proxy.py — Telegram WebSocket Proxy для Zapret2 Manager

Локальный SOCKS5 прокси, который перенаправляет трафик Telegram
через WebSocket (TLS) к kws*.web.telegram.org.

Работает параллельно с winws2 (zapret DPI bypass).

Основано на: https://github.com/Flowseal/tg-ws-proxy (MIT License)
Адаптировано для встраивания в Zapret2 Manager.

Зависимости: pip install cryptography
"""

import asyncio
import base64
import struct
import ssl
import logging
import socket
import time
import threading
import os
from typing import Dict, Optional, Tuple, List

log = logging.getLogger("tg_ws_proxy")

# ══════════════════════════════════════════════════════
#  Проверка зависимостей
# ══════════════════════════════════════════════════════

try:
    import websockets  # optional
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    log.warning("cryptography not installed: pip install cryptography")

WS_PROXY_AVAILABLE = HAS_CRYPTO


# ══════════════════════════════════════════════════════
#  Telegram IP диапазоны и DC маппинг
# ══════════════════════════════════════════════════════

# Все известные IP-подсети Telegram
_TG_SUBNETS = [
    ("149.154.160.0", "149.154.175.255"),   # 149.154.160.0/20
    ("91.108.4.0", "91.108.7.255"),         # 91.108.4.0/22
    ("91.108.8.0", "91.108.11.255"),        # 91.108.8.0/22
    ("91.108.12.0", "91.108.15.255"),       # 91.108.12.0/22
    ("91.108.16.0", "91.108.19.255"),       # 91.108.16.0/22
    ("91.108.20.0", "91.108.23.255"),       # 91.108.20.0/22
    ("91.108.56.0", "91.108.59.255"),       # 91.108.56.0/22
    ("185.76.151.0", "185.76.151.255"),     # 185.76.151.0/24
    ("95.161.64.0", "95.161.79.255"),       # 95.161.64.0/20
]

# IP → (DC, is_media)
_IP_TO_DC: Dict[str, Tuple[int, bool]] = {
    # DC2 — основной
    "149.154.167.220": (2, False),
    "149.154.167.228": (2, False),
    "149.154.167.41":  (2, False),
    "149.154.167.50":  (2, False),
    "149.154.167.51":  (2, False),
    "149.154.167.222": (2, True),   # media
    # DC4
    "149.154.167.91":  (4, False),
    "149.154.167.92":  (4, False),
    "149.154.175.100": (4, False),
    "149.154.167.100": (4, True),   # media
    # DC1
    "149.154.175.50":  (1, False),
    "149.154.175.52":  (1, False),
    "149.154.175.53":  (1, False),
    "149.154.175.54":  (1, True),   # media
    # DC3
    "149.154.175.100": (3, False),
    "149.154.175.101": (3, False),
    "149.154.175.103": (3, True),   # media
    # DC5
    "91.108.56.100":   (5, False),
    "91.108.56.101":   (5, False),
    "91.108.56.102":   (5, True),   # media
}

# DC → WebSocket домены (в порядке приоритета)
def _ws_domains(dc: int, is_media: bool) -> List[str]:
    """Генерирует список WS доменов для DC."""
    # kws{N}.web.telegram.org для основных
    # kws{N}-m.web.telegram.org для media (если есть)
    domains = []
    if is_media:
        domains.append(f"kws{dc}-m.web.telegram.org")
    domains.append(f"kws{dc}.web.telegram.org")
    return domains

DEFAULT_PORT = 1080
DEFAULT_DC_IPS = {
    2: "149.154.167.220",
    4: "149.154.167.91",
}


def _ip_to_int(ip: str) -> int:
    return struct.unpack("!I", socket.inet_aton(ip))[0]


def _is_telegram_ip(ip: str) -> bool:
    """Проверяет принадлежит ли IP Telegram."""
    try:
        ip_int = _ip_to_int(ip)
        for start, end in _TG_SUBNETS:
            if _ip_to_int(start) <= ip_int <= _ip_to_int(end):
                return True
    except Exception:
        pass
    return False


# ══════════════════════════════════════════════════════
#  MTProto парсинг
# ══════════════════════════════════════════════════════

def _dc_from_init(data: bytes) -> Tuple[Optional[int], Optional[bool]]:
    """
    Извлекает DC ID из 64-байтного MTProto init пакета.
    Bytes 60-61 содержат DC ID (little-endian signed int16).
    Отрицательный = media DC.
    """
    if len(data) < 64:
        return None, None
    try:
        dc_raw = struct.unpack_from("<h", data, 60)[0]
        if dc_raw == 0:
            return None, None
        is_media = dc_raw < 0
        dc = abs(dc_raw)
        if dc < 1 or dc > 5:
            return None, None
        return dc, is_media
    except Exception:
        return None, None


def _patch_init_dc(data: bytes, dc: int) -> bytes:
    """Патчит DC ID в init пакете (для клиентов с random dc bytes)."""
    if len(data) < 64:
        return data
    try:
        patched = bytearray(data[:64])
        struct.pack_into("<h", patched, 60, dc)
        if len(data) > 64:
            return bytes(patched) + data[64:]
        return bytes(patched)
    except Exception:
        return data


_ZERO_64 = b'\x00' * 64


def _xor_mask(data: bytes, mask: bytes) -> bytes:
    if not data:
        return data
    size = len(data)
    mask_repeated = (mask * (size // 4 + 1))[:size]
    return (
        int.from_bytes(data, "big") ^ int.from_bytes(mask_repeated, "big")
    ).to_bytes(size, "big")


class _RawWebSocket:
    """Minimal WebSocket client for Telegram relay endpoints."""

    OP_BINARY = 0x2
    OP_CLOSE = 0x8
    OP_PING = 0x9
    OP_PONG = 0xA

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self._closed = False

    @classmethod
    async def connect(cls, host: str, domain: str, timeout: float = 10.0):
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, 443, ssl=ssl_ctx, server_hostname=domain),
            timeout=min(timeout, 10.0),
        )

        ws_key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET /apiws HTTP/1.1\r\n"
            f"Host: {domain}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {ws_key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"Sec-WebSocket-Protocol: binary\r\n"
            f"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/131.0.0.0 Safari/537.36\r\n"
            f"\r\n"
        )
        writer.write(request.encode("ascii"))
        await writer.drain()

        response_lines = []
        try:
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=timeout)
                if line in (b"\r\n", b"\n", b""):
                    break
                response_lines.append(line.decode("utf-8", errors="replace").strip())
        except Exception:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            raise

        if not response_lines:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            raise ConnectionError("empty response")

        first_line = response_lines[0]
        parts = first_line.split(" ", 2)
        try:
            status_code = int(parts[1]) if len(parts) >= 2 else 0
        except ValueError:
            status_code = 0

        if status_code != 101:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            raise ConnectionError(first_line)

        return cls(reader, writer)

    def __aiter__(self):
        return self

    async def __anext__(self):
        while not self._closed:
            opcode, payload = await self._read_frame()
            if opcode == self.OP_CLOSE:
                self._closed = True
                try:
                    self.writer.write(self._build_frame(self.OP_CLOSE, b"", mask=True))
                    await self.writer.drain()
                except Exception:
                    pass
                raise StopAsyncIteration
            if opcode == self.OP_PING:
                try:
                    self.writer.write(self._build_frame(self.OP_PONG, payload, mask=True))
                    await self.writer.drain()
                except Exception:
                    pass
                continue
            if opcode == self.OP_PONG:
                continue
            if opcode in (0x1, 0x2):
                return payload
        raise StopAsyncIteration

    async def send(self, data: bytes):
        if self._closed:
            raise ConnectionError("WebSocket closed")
        self.writer.write(self._build_frame(self.OP_BINARY, data, mask=True))
        await self.writer.drain()

    async def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.writer.write(self._build_frame(self.OP_CLOSE, b"", mask=True))
            await self.writer.drain()
        except Exception:
            pass
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass

    @staticmethod
    def _build_frame(opcode: int, data: bytes, mask: bool = False) -> bytes:
        length = len(data)
        first_byte = 0x80 | opcode

        if not mask:
            if length < 126:
                return struct.pack(">BB", first_byte, length) + data
            if length < 65536:
                return struct.pack(">BBH", first_byte, 126, length) + data
            return struct.pack(">BBQ", first_byte, 127, length) + data

        mask_key = os.urandom(4)
        masked = _xor_mask(data, mask_key)
        if length < 126:
            return struct.pack(">BB", first_byte, 0x80 | length) + mask_key + masked
        if length < 65536:
            return struct.pack(">BBH", first_byte, 0x80 | 126, length) + mask_key + masked
        return struct.pack(">BBQ", first_byte, 0x80 | 127, length) + mask_key + masked

    async def _read_frame(self) -> Tuple[int, bytes]:
        header = await self.reader.readexactly(2)
        opcode = header[0] & 0x0F
        length = header[1] & 0x7F

        if length == 126:
            length = struct.unpack(">H", await self.reader.readexactly(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", await self.reader.readexactly(8))[0]

        if header[1] & 0x80:
            mask_key = await self.reader.readexactly(4)
            payload = await self.reader.readexactly(length)
            return opcode, _xor_mask(payload, mask_key)

        payload = await self.reader.readexactly(length)
        return opcode, payload


class _MsgSplitter:
    """
    Разбивает TCP данные клиента на отдельные MTProto сообщения
    для отправки каждого как отдельный WebSocket фрейм.

    Telegram WS relay обрабатывает одно MTProto сообщение на WS фрейм.
    """

    def __init__(self, init_data: bytes):
        if not HAS_CRYPTO:
            self._dec = None
            return
        cipher = Cipher(algorithms.AES(init_data[8:40]),
                        modes.CTR(init_data[40:56]))
        self._dec = cipher.encryptor()
        self._dec.update(_ZERO_64)  # пропускаем init пакет

    def split(self, chunk: bytes) -> List[bytes]:
        """Расшифровывает чтобы найти границы сообщений, возвращает разрезанный шифротекст."""
        if self._dec is None:
            return [chunk]

        plain = self._dec.update(chunk)
        boundaries = []
        pos = 0
        while pos < len(plain):
            if pos >= len(plain):
                break
            b0 = plain[pos]
            if b0 == 0x7f:
                if pos + 4 > len(plain):
                    break
                msg_len = struct.unpack_from("<I", plain, pos)[0] >> 8
                msg_len = (msg_len + 1) * 4
            else:
                msg_len = (b0 >> 0) * 4
                if msg_len == 0:
                    msg_len = 4
            boundaries.append((pos, pos + msg_len))
            pos += msg_len

        if not boundaries:
            return [chunk]

        result = []
        for start, end in boundaries:
            if start < len(chunk) and end <= len(chunk):
                result.append(chunk[start:end])
            elif start < len(chunk):
                result.append(chunk[start:])
        return result if result else [chunk]


# ══════════════════════════════════════════════════════
#  WebSocket соединение
# ══════════════════════════════════════════════════════

async def _connect_ws(target_ip: str, dc: int, is_media: bool,
                       timeout: float = 10.0):
    """Подключается к Telegram WS relay."""
    domains = _ws_domains(dc, is_media)

    for domain in domains:
        try:
            ws = await _RawWebSocket.connect(target_ip, domain, timeout=timeout)
            log.info(f"WS connected: {domain} (DC{dc}{'m' if is_media else ''})")
            return ws
        except Exception as e:
            log.debug(f"WS failed {domain}: {e}")
            continue

    return None


# ══════════════════════════════════════════════════════
#  SOCKS5 сервер
# ══════════════════════════════════════════════════════

class _Stats:
    """Статистика прокси."""
    def __init__(self):
        self.connections_total = 0
        self.connections_ws = 0
        self.connections_tcp = 0
        self.connections_rejected = 0
        self.bytes_sent = 0
        self.bytes_received = 0
        self.active = 0

    def to_dict(self):
        return {
            "total": self.connections_total,
            "ws": self.connections_ws,
            "tcp": self.connections_tcp,
            "rejected": self.connections_rejected,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "active": self.active,
        }


async def _socks5_handshake(reader, writer) -> Optional[Tuple[str, int]]:
    """SOCKS5 handshake. Возвращает (dst_ip, dst_port) или None."""
    try:
        # Greeting
        data = await asyncio.wait_for(reader.read(258), timeout=10)
        if len(data) < 3 or data[0] != 0x05:
            return None

        # No auth
        writer.write(b'\x05\x00')
        await writer.drain()

        # Request
        data = await asyncio.wait_for(reader.read(262), timeout=10)
        if len(data) < 7 or data[0] != 0x05 or data[1] != 0x01:
            # Только CONNECT поддерживается
            writer.write(b'\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00')
            await writer.drain()
            return None

        atyp = data[3]
        if atyp == 0x01:  # IPv4
            if len(data) < 10:
                return None
            dst_ip = socket.inet_ntoa(data[4:8])
            dst_port = struct.unpack("!H", data[8:10])[0]
        elif atyp == 0x03:  # Domain
            dlen = data[4]
            if len(data) < 5 + dlen + 2:
                return None
            domain = data[5:5 + dlen].decode("ascii", errors="ignore")
            dst_port = struct.unpack("!H", data[5 + dlen:7 + dlen])[0]
            # Резолвим домен
            try:
                info = await asyncio.get_event_loop().getaddrinfo(
                    domain, dst_port, socket.AF_INET, socket.SOCK_STREAM)
                dst_ip = info[0][4][0]
            except Exception:
                writer.write(b'\x05\x04\x00\x01\x00\x00\x00\x00\x00\x00')
                await writer.drain()
                return None
        elif atyp == 0x04:  # IPv6
            if len(data) < 22:
                return None
            # IPv6 пока не поддерживаем через WS, пропускаем напрямую
            dst_ip = socket.inet_ntop(socket.AF_INET6, data[4:20])
            dst_port = struct.unpack("!H", data[20:22])[0]
        else:
            writer.write(b'\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00')
            await writer.drain()
            return None

        # Success response
        writer.write(b'\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00')
        await writer.drain()

        return dst_ip, dst_port

    except Exception as e:
        log.debug(f"SOCKS5 handshake error: {e}")
        return None


async def _tcp_bridge(reader, writer, dst_ip, dst_port, init_data, label):
    """Прямой TCP мост (fallback)."""
    try:
        remote_reader, remote_writer = await asyncio.wait_for(
            asyncio.open_connection(dst_ip, dst_port),
            timeout=10,
        )
    except Exception as e:
        log.debug(f"[{label}] TCP connect failed: {e}")
        writer.close()
        return

    # Отправляем init данные
    remote_writer.write(init_data)
    await remote_writer.drain()

    async def _pipe(r, w, direction):
        try:
            while True:
                data = await r.read(65536)
                if not data:
                    break
                w.write(data)
                await w.drain()
        except Exception:
            pass
        finally:
            try:
                w.close()
            except Exception:
                pass

    await asyncio.gather(
        _pipe(reader, remote_writer, "c2s"),
        _pipe(remote_reader, writer, "s2c"),
    )


async def _ws_bridge(reader, writer, ws, init_data, splitter, label, stats):
    """WebSocket мост: клиент ↔ WS."""
    # Отправляем init как первый фрейм
    try:
        await ws.send(init_data)
    except Exception as e:
        log.debug(f"[{label}] WS send init failed: {e}")
        writer.close()
        return

    async def client_to_ws():
        """Клиент → WS (разбиваем на отдельные MTProto сообщения)."""
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                stats.bytes_sent += len(data)
                frames = splitter.split(data)
                for frame in frames:
                    await ws.send(frame)
        except Exception:
            pass
        finally:
            try:
                await ws.close()
            except Exception:
                pass

    async def ws_to_client():
        """WS → Клиент."""
        try:
            async for msg in ws:
                if isinstance(msg, bytes):
                    stats.bytes_received += len(msg)
                    writer.write(msg)
                    await writer.drain()
        except Exception:
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass

    await asyncio.gather(client_to_ws(), ws_to_client())


# ══════════════════════════════════════════════════════
#  Главный сервер
# ══════════════════════════════════════════════════════

class TelegramWsProxy:
    """
    Telegram WebSocket прокси-сервер.

    Запускается параллельно с winws2 (zapret).
    Обрабатывает ТОЛЬКО соединения к IP Telegram,
    остальное проксирует напрямую через TCP.
    """

    def __init__(self, port: int = DEFAULT_PORT,
                 host: str = "127.0.0.1",
                 dc_ips: Dict[int, str] = None):
        self.port = port
        self.host = host
        self.dc_ips = dc_ips or dict(DEFAULT_DC_IPS)
        self.stats = _Stats()
        self._server = None
        self._loop = None
        self._thread = None
        self._running = False
        self._stop_event = None
        self._client_tasks = set()

    @property
    def is_running(self) -> bool:
        return self._running and self._thread and self._thread.is_alive()

    def start(self) -> Tuple[bool, str]:
        """Запускает прокси в фоновом потоке."""
        if self.is_running:
            return True, f"Уже запущен на {self.host}:{self.port}"

        if not WS_PROXY_AVAILABLE:
            missing = ["cryptography"]
            return False, (
                f"Нужны библиотеки: {', '.join(missing)}\n"
                f"Установите: pip install {' '.join(missing)}"
            )

        # Проверяем доступность порта
        try:
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.settimeout(1)
            test_sock.bind((self.host, self.port))
            test_sock.close()
        except OSError as e:
            return False, f"Порт {self.port} занят: {e}"

        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True,
            name="tg-ws-proxy",
        )
        self._thread.start()

        # Ждём запуска
        for _ in range(30):
            if self._running:
                return True, f"Запущен на {self.host}:{self.port}"
            time.sleep(0.1)

        return False, "Таймаут запуска"

    def stop(self) -> Tuple[bool, str]:
        """Останавливает прокси."""
        if not self.is_running:
            self._running = False
            self._server = None
            self._loop = None
            self._thread = None
            self._stop_event = None
            return True, "Не запущен"

        if self._stop_event is not None:
            self._stop_event.set()

        if self._loop and self._loop.is_running():
            try:
                fut = asyncio.run_coroutine_threadsafe(self._shutdown_async(), self._loop)
                fut.result(timeout=3)
            except Exception as e:
                log.debug(f"TG WS Proxy graceful shutdown fallback: {e}")
            try:
                self._loop.call_soon_threadsafe(lambda: None)
            except Exception:
                pass

        if self._thread:
            self._thread.join(timeout=5)

        if self._thread and self._thread.is_alive():
            if self._loop and self._loop.is_running():
                try:
                    self._loop.call_soon_threadsafe(self._loop.stop)
                except Exception:
                    pass
            self._thread.join(timeout=2)

        if self._thread and self._thread.is_alive():
            return False, "Не удалось остановить прокси"

        self._running = False
        self._server = None
        self._loop = None
        self._thread = None
        self._stop_event = None
        log.info("TG WS Proxy stopped")
        return True, "Остановлен"

    def _run_loop(self):
        """Asyncio event loop в отдельном потоке."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._serve())
        except Exception as e:
            log.error(f"TG WS Proxy loop error: {e}")
        finally:
            self._running = False
            try:
                pending = [task for task in asyncio.all_tasks(self._loop) if not task.done()]
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            try:
                self._loop.close()
            except Exception:
                pass
            self._server = None
            self._loop = None
            self._thread = None
            self._stop_event = None

    async def _serve(self):
        """Основной серверный корутин."""
        server = await asyncio.start_server(
            self._handle_client,
            self.host, self.port,
        )
        self._server = server
        self._running = True
        log.info(f"TG WS Proxy listening on {self.host}:{self.port}")
        log.info(f"DC config: {self.dc_ips}")

        # Ждём stop_event
        while not self._stop_event.is_set():
            await asyncio.sleep(0.2)

        server.close()
        await server.wait_closed()
        self._server = None

    async def _handle_client(self, reader, writer):
        """Обработка одного клиентского соединения."""
        current_task = asyncio.current_task()
        if current_task is not None:
            self._client_tasks.add(current_task)
        self.stats.connections_total += 1
        self.stats.active += 1
        peer = writer.get_extra_info("peername")
        label = f"{peer[0]}:{peer[1]}" if peer else "?"

        try:
            # SOCKS5 handshake
            result = await _socks5_handshake(reader, writer)
            if result is None:
                self.stats.connections_rejected += 1
                log.debug(f"[{label}] SOCKS5 rejected")
                writer.close()
                return

            dst_ip, dst_port = result
            log.debug(f"[{label}] CONNECT → {dst_ip}:{dst_port}")

            # Не-Telegram трафик → прямой TCP
            if not _is_telegram_ip(dst_ip):
                log.debug(f"[{label}] Non-Telegram IP, TCP passthrough")
                self.stats.connections_tcp += 1
                # Читаем данные и проксируем напрямую
                init = await asyncio.wait_for(reader.read(65536), timeout=30)
                if init:
                    await _tcp_bridge(reader, writer, dst_ip, dst_port, init, label)
                return

            # Telegram IP — читаем init пакет
            init = await asyncio.wait_for(reader.read(65536), timeout=30)
            if not init or len(init) < 64:
                log.debug(f"[{label}] No init data")
                writer.close()
                return

            # Извлекаем DC
            dc, is_media = _dc_from_init(init)

            # Если DC не определён, пробуем по IP
            if dc is None and dst_ip in _IP_TO_DC:
                dc, is_media = _IP_TO_DC[dst_ip]
                init = _patch_init_dc(init, dc if not is_media else -dc)

            if dc is None:
                log.debug(f"[{label}] Unknown DC for {dst_ip}, TCP fallback")
                self.stats.connections_tcp += 1
                await _tcp_bridge(reader, writer, dst_ip, dst_port, init, label)
                return

            media_tag = "m" if is_media else ""
            relay_ip = self.dc_ips.get(dc, dst_ip)
            log.info(
                f"[{label}] DC{dc}{media_tag} via WS → {dst_ip}:{dst_port} "
                f"(relay {relay_ip})"
            )

            # Пробуем WebSocket
            ws = await _connect_ws(relay_ip, dc, is_media or False)

            if ws is None:
                log.info(f"[{label}] WS unavailable, TCP fallback")
                self.stats.connections_tcp += 1
                await _tcp_bridge(reader, writer, dst_ip, dst_port, init, label)
                return

            # WS мост
            self.stats.connections_ws += 1
            splitter = _MsgSplitter(init)
            await _ws_bridge(reader, writer, ws, init, splitter, label, self.stats)

        except asyncio.TimeoutError:
            log.debug(f"[{label}] Timeout")
        except Exception as e:
            log.debug(f"[{label}] Error: {e}")
        finally:
            self.stats.active -= 1
            if current_task is not None:
                self._client_tasks.discard(current_task)
            try:
                writer.close()
            except Exception:
                pass

    async def _shutdown_async(self):
        self._running = False
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None

        current_task = asyncio.current_task()
        tasks = [task for task in list(self._client_tasks) if task is not current_task and not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def get_telegram_link(self) -> str:
        """Возвращает tg://socks ссылку для автонастройки."""
        return f"tg://socks?server={self.host}&port={self.port}"

    def get_stats_str(self) -> str:
        """Форматированная статистика."""
        s = self.stats
        sent = s.bytes_sent / 1024 / 1024
        recv = s.bytes_received / 1024 / 1024
        return (
            f"Соединений: {s.connections_total} "
            f"(WS: {s.connections_ws}, TCP: {s.connections_tcp}, "
            f"отклонено: {s.connections_rejected})\n"
            f"Активных: {s.active}\n"
            f"Отправлено: {sent:.1f} MB, Получено: {recv:.1f} MB"
        )


# ══════════════════════════════════════════════════════
#  CLI запуск (для тестирования)
# ══════════════════════════════════════════════════════

def main():
    import argparse

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    ap = argparse.ArgumentParser(description="Telegram WebSocket Proxy")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--dc-ip", action="append", default=[])
    args = ap.parse_args()

    dc_ips = dict(DEFAULT_DC_IPS)
    for item in args.dc_ip:
        dc, ip = item.split(":", 1)
        dc_ips[int(dc)] = ip

    proxy = TelegramWsProxy(port=args.port, host=args.host, dc_ips=dc_ips)
    ok, msg = proxy.start()
    print(msg)

    if ok:
        print(f"\nНастройте Telegram: {proxy.get_telegram_link()}")
        print("Ctrl+C для остановки\n")
        try:
            while True:
                time.sleep(5)
                print(proxy.get_stats_str())
        except KeyboardInterrupt:
            proxy.stop()
            print("\nОстановлен")


if __name__ == "__main__":
    main()
