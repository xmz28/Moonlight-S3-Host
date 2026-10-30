"""Physical PIN authorization (SRP-6a) and nonce-based mutual authentication.

RFC5054 2048-bit group with SHA256. Application framing/proofs are MS3 v2,
not TLS-SRP and not wire-compatible with Moonlight/Sunshine.
"""
import hashlib
import hmac
import re
import secrets
import socket
from protocol import recv_exact, token_bytes

N = int(
    "AC6BDB41324A9A9BF166DE5E1389582FAF72B6651987EE07FC3192943DB56050"
    "A37329CBB4A099ED8193E0757767A13DD52312AB4B03310DCD7F48A9DA04FD50"
    "E8083969EDB767B0CF6095179A163AB3661A05FBD5FAAAE82918A9962F0B93B8"
    "55F97993EC975EEAA80D740ADBF4FF747359D041D5C33EA71D281E446B14773B"
    "CA97B43A23FB801676BD207A436C6481F1D2B9078717461A5B9D32E688F87748"
    "544523B524B0D57D5EA77A2775D2ECFA032CFBDBF52FB3786160279004E57AE6"
    "AF874E7303CE53299CCC041C7BC308D82A5698F3A8D0C38271AE35F8E9DBFBB6"
    "94B5C803D89F7AE435DE236D525F54759B65E372FCD68EF20FA7111F9E4AFF73", 16)
G = 2


def padded(number):
    return number.to_bytes(256, "big")


def digest(data):
    return hashlib.sha256(data).digest()


def mac(key, data):
    return hmac.new(key, data, hashlib.sha256).digest()


def identity_bytes(value, size=32):
    if not re.fullmatch(r"[0-9a-f]{%d}" % size, value):
        raise ValueError("设备或电脑身份格式无效，请重新配对")
    return value.encode("ascii")


def client_exchange(pin, host_id, challenge, expected_device="", private=None):
    if not re.fullmatch(r"[0-9]{4}", pin):
        raise ValueError("请输入 S3 屏幕上的四位数字，保留开头的0")
    if len(challenge) != 288 or challenge[:4] != b"SRP2":
        raise ValueError("设备未开启配对，请在 S3 首页点击配对电脑")
    device = challenge[4:16].decode("ascii")
    identity_bytes(device, 12)
    if expected_device and device != expected_device:
        raise ValueError("接收端身份与所选设备不一致")
    host = identity_bytes(host_id)
    salt, public = challenge[16:32], challenge[32:]
    B = int.from_bytes(public, "big")
    if not 1 < B < N:
        raise ValueError("无效的 SRP 公钥")
    a = private if private is not None else secrets.randbits(256) | (1 << 255)
    A = pow(G, a, N)
    u = int.from_bytes(digest(padded(A) + public), "big")
    if not u:
        raise ValueError("无效的 SRP 参数")
    x = int.from_bytes(digest(salt + digest(f"MoonlightS3:{device}:{pin}".encode("ascii"))), "big")
    k = int.from_bytes(digest(padded(N) + padded(G)), "big")
    base = (B - k * pow(G, x, N)) % N
    if not base:
        raise ValueError("无效的 SRP 公钥")
    S = pow(base, a + u * x, N)
    key = digest(padded(S))
    transcript = device.encode("ascii") + host + salt + padded(A) + public
    proof = mac(key, b"client-v2:" + transcript)
    server_proof = mac(key, b"server-v2:" + transcript)
    credential = mac(key, b"secret-v2:" + transcript)[:16].hex()
    return b"SRA2" + padded(A) + proof, server_proof, dict(device_id=device, host_id=host_id, token=credential)


def pair(host, port, pin, expected_device="", host_id=None):
    host_id = host_id or secrets.token_hex(16)
    identity_bytes(host_id)
    try:
        with socket.create_connection((host, int(port)), timeout=3) as sock:
            sock.settimeout(3)
            sock.sendall(b"PAR2" + host_id.encode("ascii"))
            challenge = recv_exact(sock, 288)
            request, expected, record = client_exchange(pin, host_id, challenge, expected_device)
            sock.sendall(request)
            reply = recv_exact(sock, 48)
            if reply[:4] != b"PAK2" or reply[36:] != record["device_id"].encode("ascii") or not hmac.compare_digest(reply[4:36], expected):
                raise ValueError("配对验证失败，未保存凭据")
            return record
    except (ConnectionError, OSError) as exc:
        raise ConnectionError("配对失败：请在 S3 开启配对，检查四位码及有效期后重试") from exc


def authenticate(sock, host_id, token, expected_device,request_id=None):
    host = identity_bytes(host_id)
    identity_bytes(expected_device, 12)
    key = token_bytes(token)
    if request_id is None:sock.sendall(b"AU2?" + host) # v2 tests/tools only; v3 firmware rejects it.
    else:
        if not 0<int(request_id)<=0xffffffff:raise ValueError("连接请求已取消或过期")
        sock.sendall(b"AU3?"+host+int(request_id).to_bytes(4,"big"))
    reply = recv_exact(sock, 48)
    if reply[:4] != b"CHL2" or reply[4:16] != expected_device.encode("ascii"):
        raise ValueError("设备身份或协议不匹配，请重新配对")
    transcript = reply[4:16] + host + reply[16:48]
    sock.sendall(b"PRF2" + mac(key, b"client" + transcript).hex().encode("ascii"))
    proof = recv_exact(sock, 68)
    expected = mac(key, b"server" + transcript).hex().encode("ascii")
    if proof[:4] != b"OKA2" or not hmac.compare_digest(proof[4:], expected):
        raise ValueError("设备自动验证失败，请重新配对")
