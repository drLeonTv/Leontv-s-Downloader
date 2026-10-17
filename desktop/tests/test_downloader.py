import unittest

from desktop.downloader import (
    build_download_options,
    parse_clip_range,
    parse_timestamp,
    validate_video_url,
)


class TimestampTests(unittest.TestCase):
    def test_parses_mm_ss_and_hh_mm_ss(self):
        self.assertEqual(parse_timestamp("15:30"), 930)
        self.assertEqual(parse_timestamp("01:15:30"), 4530)

    def test_rejects_invalid_timestamps(self):
        for value in ("", "1:75", "01:02:60", "1:2:3:4", "-01:00"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_timestamp(value)

    def test_validates_clip_order_and_duration(self):
        self.assertEqual(parse_clip_range("01:15:00", "01:20:30", 6000), (4500, 4830))
        with self.assertRaises(ValueError):
            parse_clip_range("00:20", "00:10")
        with self.assertRaises(ValueError):
            parse_clip_range("00:20", "01:00", 50)
        with self.assertRaises(ValueError):
            parse_clip_range("00:20", "")


class VideoUrlTests(unittest.TestCase):
    def test_accepts_supported_video_urls(self):
        self.assertEqual(
            validate_video_url("https://www.youtube.com/watch?v=abc123"),
            "https://www.youtube.com/watch?v=abc123",
        )
        self.assertEqual(validate_video_url("https://twitch.tv/videos/123"), "https://twitch.tv/videos/123")

    def test_rejects_untrusted_and_non_video_urls(self):
        for url in (
            "http://youtube.com/watch?v=abc",
            "https://youtube.com.evil.example/watch?v=abc",
            "https://youtube.com/watch",
            "https://twitch.tv/channelname",
            "https://user@youtube.com/watch?v=abc",
            "https://youtube.com:bad/watch?v=abc",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_video_url(url)


class DownloadOptionsTests(unittest.TestCase):
    def setUp(self):
        self.video_info = {"duration": 6000}
        self.hook = lambda _data: None

    def test_mp4_selects_height_and_merges_as_mp4(self):
        options = build_download_options(
            {"url": "https://youtube.com/watch?v=abc", "format": "mp4", "quality": "720"},
            self.video_info,
            self.hook,
        )
        self.assertIn("[height<=720]", options["format"])
        self.assertEqual(options["merge_output_format"], "mp4")

    def test_mp3_uses_audio_extraction(self):
        options = build_download_options(
            {"url": "https://youtube.com/watch?v=abc", "format": "mp3"},
            self.video_info,
            self.hook,
        )
        self.assertEqual(options["format"], "bestaudio/best")
        self.assertEqual(options["postprocessors"][0]["preferredcodec"], "mp3")

    def test_twitch_range_is_passed_as_download_section(self):
        options = build_download_options(
            {
                "url": "https://twitch.tv/videos/123",
                "format": "mp4",
                "quality": "best",
                "start": "01:15:00",
                "end": "01:20:30",
            },
            self.video_info,
            self.hook,
        )
        self.assertEqual(options["download_sections"], ["*4500-4830"])
        self.assertTrue(options["force_keyframes_at_cuts"])

    def test_rejects_clip_for_youtube(self):
        with self.assertRaises(ValueError):
            build_download_options(
                {
                    "url": "https://youtube.com/watch?v=abc",
                    "format": "mp4",
                    "start": "00:01",
                    "end": "00:02",
                },
                self.video_info,
                self.hook,
            )

    def test_rejects_mp4_when_source_has_no_mp4_video_format(self):
        with self.assertRaises(ValueError):
            build_download_options(
                {"url": "https://youtube.com/watch?v=abc", "format": "mp4"},
                {"duration": 60, "mp4_available": False},
                self.hook,
            )


if __name__ == "__main__":
    unittest.main()
