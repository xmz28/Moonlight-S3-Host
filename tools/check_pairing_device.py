"""Explicit real-device authentication checks. No capture or Windows input."""
import argparse
import json
from pathlib import Path
import socket
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pairing import mac
from protocol import recv_exact
from settings_store import load_settings,profile_path
from device_request import RequestedSession


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    settings=load_settings(profile_path(ROOT))
    device=settings["device_id"];record=settings["pairings"][device]
    host_id=record["host_id"].encode();key=record["token"].encode()
    def connect():
        sock=socket.create_connection((settings["host"],int(settings["port"])),timeout=3)
        sock.settimeout(3);return sock
    def challenge(sock):
        sock.sendall(b"AU3?"+host_id+int(settings['request_id']).to_bytes(4,'big'))
        data=recv_exact(sock,48)
        assert data[:16]==b"CHL2"+device.encode()
        return data[4:16]+host_id+data[16:]
    def rejected(sock):
        try:return sock.recv(1)==b""
        except ConnectionResetError:return True
    results={}
    with RequestedSession(settings) as permit, socket.create_connection((permit.settings['host'],int(permit.settings['port'])),timeout=3) as sock:
        settings.update(permit.settings)
        transcript=challenge(sock)
        proof=b"PRF2"+mac(key,b"client"+transcript).hex().encode()
        sock.sendall(proof)
        response=recv_exact(sock,68)
        assert response==b"OKA2"+mac(key,b"server"+transcript).hex().encode()
        assert recv_exact(sock,16)[:4]==b"RDY1"
        results["saved_credentials_authenticate"]=True
    time.sleep(.1)
    with RequestedSession(settings) as permit, socket.create_connection((permit.settings['host'],int(permit.settings['port'])),timeout=3) as sock:
        settings.update(permit.settings)
        second=challenge(sock)
        assert second!=transcript
        sock.sendall(proof)
        results["fresh_nonce"]=True
        results["old_client_proof_rejected"]=rejected(sock)
    time.sleep(.1)
    with RequestedSession(settings) as permit, socket.create_connection((permit.settings['host'],int(permit.settings['port'])),timeout=3) as sock:
        settings.update(permit.settings)
        challenge(sock);sock.sendall(b"PRF2"+b"0"*64)
        results["wrong_proof_rejected"]=rejected(sock)
    time.sleep(.1)
    with RequestedSession(settings) as permit, socket.create_connection((permit.settings['host'],int(permit.settings['port'])),timeout=3) as sock:
        settings.update(permit.settings)
        sock.sendall(b"AU3?"+b"0"*32+int(settings['request_id']).to_bytes(4,'big'))
        results["unknown_host_rejected"]=rejected(sock)
    time.sleep(.1)
    with RequestedSession(settings) as permit, socket.create_connection((permit.settings['host'],int(permit.settings['port'])),timeout=3) as sock:
        settings.update(permit.settings)
        sock.sendall(b"AUT1"+key)
        results["legacy_protocol_rejected"]=rejected(sock)
    assert all(results.values()),results
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(results,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(results))


if __name__=="__main__":main()
