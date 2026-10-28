import numpy as np
import pytest

pytest.importorskip("win32gui")  # Desktop backend is Windows-only

from src.core.area import Region  # noqa: E402
from src.utils.device.desktop.window_manager import (  # noqa: E402
    WindowManager,
    bars_are_black,
    crop_to_client,
    game_area,
    to_base_resolution,
)


class StubWindow(WindowManager):
    """WindowManager over a fixed client area, no real window behind it."""

    def __init__(self, client: Region):
        self.client = client

    def get_client_region(self) -> Region:
        return self.client


class TestCropToClient:
    def test_crops_client_out_of_window_frame(self):
        # Windowed: 1px border left/right/bottom and a 31px title bar
        frame = Region(100, 50, 1838, 1065)
        client = Region(101, 81, 1836, 1033)
        image = np.zeros((frame.height, frame.width, 3), np.uint8)
        image[31, 1] = 255  # first client pixel
        image[31 + 1032, 1 + 1835] = 128  # last client pixel

        crop = crop_to_client(image, frame, client)

        assert crop.shape == (1033, 1836, 3)
        assert crop[0, 0, 0] == 255
        assert crop[-1, -1, 0] == 128

    def test_fullscreen_has_no_offset(self):
        region = Region(0, 0, 1920, 1080)
        image = np.zeros((1080, 1920, 3), np.uint8)
        assert crop_to_client(image, region, region).shape == (1080, 1920, 3)

    def test_rejects_capture_smaller_than_client(self):
        image = np.zeros((700, 1280, 3), np.uint8)
        with pytest.raises(RuntimeError):
            crop_to_client(image, Region(0, 0, 1280, 700), Region(0, 0, 1280, 720))

    def test_rejects_window_that_moved_during_capture(self):
        # Client read after a move sits left of the frame read before it
        image = np.zeros((767, 1284, 3), np.uint8)
        with pytest.raises(RuntimeError):
            crop_to_client(image, Region(210, 150, 1284, 767), Region(209, 195, 1280, 720))

    def test_rejects_capture_not_matching_frame_size(self):
        image = np.zeros((787, 1284, 3), np.uint8)  # frame grew during capture
        with pytest.raises(RuntimeError):
            crop_to_client(image, Region(0, 0, 1284, 767), Region(2, 45, 1280, 720))


class TestToBaseResolution:
    @pytest.mark.parametrize("size", [(1836, 1033), (1920, 1080), (960, 540)])
    def test_scales_to_1280x720(self, size):
        w, h = size
        image = np.zeros((h, w, 3), np.uint8)
        image[h // 2 :, w // 2 :] = 255  # bottom-right quadrant

        out = to_base_resolution(image)

        assert out.shape == (720, 1280, 3)
        assert out[100, 100, 0] == 0
        assert out[620, 1180, 0] == 255

    def test_keeps_1280x720_untouched(self):
        image = np.zeros((720, 1280, 3), np.uint8)
        assert to_base_resolution(image) is image


class TestGameArea:
    @pytest.mark.parametrize(
        ("client", "area"),
        [
            ((2560, 1600), (0, 80, 2560, 1440)),  # 16:10 fullscreen, letterboxed
            ((3440, 1440), (440, 0, 2560, 1440)),  # 21:9, pillarboxed
            ((1440, 1080), (0, 135, 1440, 810)),  # 4:3
            ((1280, 800), (0, 40, 1280, 720)),
            ((1920, 1080), (0, 0, 1920, 1080)),
            ((1922, 1081), (0, 0, 1922, 1081)),  # Within 1% of 16:9: all picture
        ],
    )
    def test_largest_centred_16_9_rectangle(self, client, area):
        assert game_area(*client) == Region(*area)


class TestBarsAreBlack:
    def test_letterbox_bars(self):
        image = np.zeros((1600, 2560, 3), np.uint8)
        image[80:1520] = 200
        assert bars_are_black(image, Region(0, 80, 2560, 1440))

    def test_stretched_picture_has_no_bars(self):
        image = np.full((1600, 2560, 3), 200, np.uint8)
        assert not bars_are_black(image, Region(0, 80, 2560, 1440))

    def test_tolerates_capture_noise_and_a_few_bright_pixels(self):
        image = np.full((1440, 3440, 3), 12, np.uint8)
        image[:, 440:3000] = 200
        image[700:710, 0:100] = 255  # 1000 of the 1.27M bar pixels
        assert bars_are_black(image, Region(440, 0, 2560, 1440))

    def test_bright_bar_strip_fails(self):
        image = np.zeros((1080, 1440, 3), np.uint8)
        image[135:945] = 200
        image[0:20] = 255  # 7% of the bars
        assert not bars_are_black(image, Region(0, 135, 1440, 810))

    def test_whole_client_picture_has_nothing_to_check(self):
        image = np.full((1080, 1920, 3), 200, np.uint8)
        assert bars_are_black(image, Region(0, 0, 1920, 1080))

    def test_picture_a_pixel_off_centre_on_thin_bars_passes(self):
        # 1920x1093: 13 rows of bars, the game put the odd one at the top
        image = np.zeros((1093, 1920, 3), np.uint8)
        image[7 : 7 + 1080] = 200
        area = game_area(1920, 1093)
        assert area.y == 6
        assert bars_are_black(image, area)


class TestScaleCoords:
    def test_maps_into_the_letterboxed_picture(self):
        wm = StubWindow(Region(0, 0, 2560, 1600))
        assert wm.scale_coords(1238, 25) == (2476, 130)
        assert wm.scale_coords(0, 0) == (0, 80)  # Picture corners
        assert wm.scale_coords(1280, 720) == (2560, 1520)

    def test_adds_client_origin_and_pillarbox_offset(self):
        wm = StubWindow(Region(100, 50, 3440, 1440))
        assert wm.scale_coords(0, 0) == (540, 50)
        assert wm.scale_coords(1280, 720) == (3100, 1490)

    def test_16_9_window_fills_the_client(self):
        wm = StubWindow(Region(301, 245, 1920, 1080))
        assert wm.scale_coords(0, 0) == (301, 245)
        assert wm.scale_coords(640, 360) == (1261, 785)
