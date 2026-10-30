import json
import os
from pathlib import Path
import queue
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch,Mock
import uuid

from computer_presence import receiver_candidates,resolve_receiver,ComputerPresence
from discovery import Device
from main import App
from settings_store import load_settings,save_settings
from single_instance import SingleInstance
from test_computer_presence import PC,DEVICE,RECORD,reply


def device(address,identity=DEVICE):return Device(identity,"moonlight-s3-"+identity[-6:],address,47989)


class AddressTests(unittest.TestCase):
    def test_manual_old_ip_cannot_replace_new_discovery(self):
        found=receiver_candidates([device("127.0.0.2")],{DEVICE:dict(RECORD,host="127.0.0.1")},"127.0.0.1",DEVICE)
        self.assertEqual([d.host for d in found],["127.0.0.2","127.0.0.1"])

    def test_start_resolves_exact_identity_and_validates_pairing(self):
        settings=dict(host="127.0.0.1",port=47989,device_id=DEVICE,**RECORD)
        latest=device("127.0.0.2")
        with patch("computer_presence.discover",return_value=[device("127.0.0.3","0"*12),latest]),patch("computer_presence.probe_receiver",return_value=dict(paired=True)) as probe:
            self.assertEqual(resolve_receiver(settings),latest)
            self.assertEqual(probe.call_args.args[2],latest)
        with patch("computer_presence.discover",return_value=[latest]),patch("computer_presence.probe_receiver",return_value=dict(paired=False)):
            with self.assertRaises(ConnectionError):resolve_receiver(settings)

    def test_same_identity_moves_ip_with_old_hint_without_pairing_or_start(self):
        old,new="127.0.0.1","127.0.0.2"
        first=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);first.bind((old,0));port=first.getsockname()[1]
        second=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);second.bind((new,port))
        sockets=[first,second];stop=threading.Event();moved=threading.Event();seen_old=threading.Event();seen_new=threading.Event()
        for sock in sockets:sock.settimeout(.1)
        def server(index):
            sock=sockets[index]
            while not stop.is_set():
                try:data,peer=sock.recvfrom(512)
                except socket.timeout:continue
                if moved.is_set()!=(index==1):continue
                nonce=data.split(b" ")[1].decode()
                sock.sendto(reply(nonce=nonce,action="00000000"),peer)
        threads=[threading.Thread(target=server,args=(i,)) for i in range(2)]
        for thread in threads:thread.start()
        online=[];requests=[]
        def updated(value):
            online.append(value)
            (seen_new if value["host"]==new else seen_old).set()
        with patch("computer_presence.PORT",port),patch("computer_presence.discover",side_effect=lambda **kwargs:[device(new if moved.is_set() else old)]):
            service=ComputerPresence(requests.append,updated,search_interval=.1,poll_interval=.03)
            try:
                service.configure(PC,{DEVICE:dict(RECORD,host=old)},old,DEVICE)
                self.assertTrue(seen_old.wait(3));moved.set();self.assertTrue(seen_new.wait(3))
                self.assertEqual([event["host"] for event in online],[old,new]);self.assertEqual(requests,[])
            finally:service.close();service.thread.join(3)
        stop.set()
        for thread in threads:thread.join(2)
        for sock in sockets:sock.close()


class Variable:
    def __init__(self,value):self.value=value
    def get(self):return self.value
    def set(self,value):self.value=value


class GuiAddressTests(unittest.TestCase):
    def fake(self):
        app=Mock()
        values=dict(host="127.0.0.1",port="47989",device_id=DEVICE,token=RECORD["token"],host_id=PC,monitor="1",quality="60",fps="25",network_version="2",resolution="400x240")
        app.vars={k:Variable(v) for k,v in values.items()}
        app.pairings={DEVICE:dict(RECORD,host="127.0.0.1")}
        app.pairing_busy=False;app.worker=None;app.fields=[];app.events=queue.Queue();app.session=None
        app.active_request=dict(device_id=DEVICE,action=42)
        return app

    def test_online_address_updates_without_changing_credentials(self):
        app=self.fake();value=dict(host="127.0.0.2",port=47989,device_id=DEVICE,name="S3",paired=True)
        App.update_endpoint(app,value)
        self.assertEqual(app.vars["host"].get(),"127.0.0.2")
        self.assertEqual(app.pairings[DEVICE]["token"],RECORD["token"])
        self.assertEqual(app.pairings[DEVICE]["host_id"],PC)
        App.update_endpoint(app,value);app.save_settings.assert_called_once()
        App.update_endpoint(app,dict(value,host="127.0.0.3",paired=False))
        self.assertEqual(app.vars["host"].get(),"127.0.0.2")

    def test_pc_start_uses_current_address_before_capture(self):
        app=self.fake()
        with patch("main.resolve_receiver",return_value=device("127.0.0.2")),patch("main.validate_request",return_value=dict(options=0x193c011c)) as validate,patch("main.StreamSession") as stream:
            App.start(app);app.worker.join(3)
            self.assertEqual(stream.call_args.args[0]["host"],"127.0.0.2");stream.return_value.run.assert_called_once()
            self.assertEqual(validate.call_args.args[2],42)

    def test_stop_during_lookup_does_not_start_stream(self):
        app=self.fake();lookup=threading.Event();release=threading.Event()
        def resolve(_):lookup.set();release.wait(2);return device("127.0.0.2")
        with patch("main.resolve_receiver",side_effect=resolve),patch("main.StreamSession") as stream:
            App.start(app);self.assertTrue(lookup.wait(2));App.stop(app);release.set();app.worker.join(3);stream.assert_not_called()


class StorageTests(unittest.TestCase):
    def test_failed_replace_preserves_original_pairing(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"settings.json";original=dict(computer_id=PC,pairings={DEVICE:RECORD})
            save_settings(path,original)
            with patch("settings_store.os.replace",side_effect=OSError("simulated")):
                with self.assertRaises(OSError):save_settings(path,{})
            self.assertEqual(load_settings(path),original);self.assertEqual(list(Path(directory).glob(".settings-*.tmp")),[])

    def test_corrupt_config_is_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"settings.json";path.write_text("{broken",encoding="utf-8")
            with self.assertRaises(ValueError):load_settings(path)
            self.assertEqual(path.read_text(),"{broken")

    @unittest.skipUnless(os.name=="nt","Windows named mutex")
    def test_single_instance_blocks_second_copy_and_releases(self):
        name="Local\\MoonlightS3Host.Test."+uuid.uuid4().hex
        first,second=SingleInstance(name),SingleInstance(name)
        try:
            self.assertTrue(first.acquire());self.assertFalse(second.acquire());first.close();self.assertTrue(second.acquire())
        finally:first.close();second.close()
