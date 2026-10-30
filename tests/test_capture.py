import io
from types import SimpleNamespace as NS
import sys
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from capture import DesktopCapture
from protocol import Viewport, content_geometry, encode_frame


class CaptureTests(unittest.TestCase):
    def test_dxgi_exact_monitor_bgr_channels_and_cleanup(self):
        monitor=dict(left=-2560,top=100,width=2560,height=1440)
        rect=NS(left=-2560,top=100,right=0,bottom=1540)
        output=NS(update_desc=lambda:None,desc=NS(DesktopCoordinates=rect),attached_to_desktop=True)
        pixels=np.zeros((4,4,4),dtype=np.uint8)
        pixels[:]=[10,40,220,0]
        duplicate=NS(texture=object(),duplicator=object(),release_frame=lambda:None)
        stage=NS(width=4,height=4,texture=object(),interface=object())
        released=[];calls=[]
        camera=NS(_stagesurf=stage,_duplicator=duplicate,grab=lambda **kw:pixels,
                  _create_duplicator=lambda:NS(texture=object(),duplicator=object(),release_frame=lambda:None))
        def release():
            stage.release(); duplicate.release(); released.append(True)
        camera.release=release
        def create(**kwargs): calls.append(kwargs);return camera
        module=NS(__factory=NS(outputs=[[output]]),create=create)
        with patch.dict(sys.modules,dxcam=module):
            capture=DesktopCapture(monitor,(2,2))
            self.assertEqual(capture.grab().getpixel((0,0)),(220,40,10))
            self.assertEqual(calls[0]["output_idx"],0)
            recovered=camera._create_duplicator()
            recovered.release()
            self.assertIsNone(recovered.duplicator)
            capture.close();capture.close()
        self.assertEqual(released,[True])
        self.assertIsNone(stage.texture);self.assertIsNone(duplicate.duplicator)

    def test_dxgi_does_not_guess_an_unmatched_monitor(self):
        module=NS(__factory=NS(outputs=[]),create=lambda **kw:self.fail("Must not create capture"))
        with patch.dict(sys.modules,dxcam=module):
            with self.assertRaises(OSError):
                DesktopCapture(dict(left=0,top=0,width=10,height=10),(4,4))

    def test_prescaled_frame_geometry_toolbar_and_rgb(self):
        view=Viewport.fit(dict(left=-2560,top=0,width=2560,height=1440))
        for resolution in ("400x240","800x480"):
            left,top,width,height=content_geometry(view,resolution)
            jpeg=encode_frame(Image.new("RGB",(width,height),(220,40,10)),view,
                              quality=90,resolution=resolution,mode="RIGHT")
            image=Image.open(io.BytesIO(jpeg));image.load()
            self.assertEqual(image.size,tuple(map(int,resolution.split("x"))))
            r,g,b=image.getpixel((left+width//2,top+height//2))
            self.assertGreater(r,180);self.assertLess(b,40)
            scale=image.width/800
            active=image.getpixel((round(220*scale),round(450*scale)))
            inactive=image.getpixel((round(20*scale),round(450*scale)))
            self.assertGreater(active[1],inactive[1]+20)


if __name__=="__main__": unittest.main()
