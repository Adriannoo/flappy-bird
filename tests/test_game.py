import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame
from main import Game, PipePair, load_record, save_record, FLOOR_Y, BIRD_X
from main import difficulty_for, medal_for
from storage import load_profile, data_file, load_settings


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "data" / "record.json"

    def tearDown(self):
        self.temporary.cleanup()

    def test_missing_record_starts_at_zero(self):
        self.assertEqual(load_record(self.path), 0)

    def test_saved_record_survives_reload(self):
        save_record(self.path, 7)
        self.assertEqual(load_record(self.path), 7)
        self.assertFalse(self.path.with_name("record.json.tmp").exists())

    def test_invalid_records_do_not_crash(self):
        self.path.parent.mkdir()
        for value in ["invalid json", "null", "[]", '{"high_score": -1}', '{"high_score": true}', '{"high_score": "9"}']:
            with self.subTest(value=value):
                self.path.write_text(value, encoding="utf-8")
                self.assertEqual(load_record(self.path), 0)


class GameTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "record.json"
        self.game = Game(self.path)

    def tearDown(self):
        pygame.quit()
        self.temporary.cleanup()

    def test_ready_screen_waits_for_input(self):
        initial = self.game.bird_y
        self.game.update(2)
        self.assertEqual(self.game.state, "ready")
        self.assertEqual(self.game.bird_y, initial)
        self.assertEqual(self.game.pipes, [])

    def test_keyboard_and_mouse_start_or_flap(self):
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
        self.assertEqual(self.game.state, "countdown")
        self.game.update(3)
        self.assertEqual(self.game.state, "playing")
        for event in [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE), pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP), pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=self.game.scene_geometry().center)]:
            with self.subTest(event=event):
                self.game.velocity = 0
                self.game.handle_event(event)
                self.assertEqual(self.game.state, "playing")
                self.assertLess(self.game.velocity, 0)

    def test_restart_clears_round_state(self):
        self.game.pipes = [PipePair(200, 400, True)]
        self.game.score = 5
        self.game.spawn_time = 1.3
        self.game.state = "over"
        self.game.flap()
        self.assertEqual(self.game.score, 0)
        self.assertEqual(self.game.pipes, [])
        self.assertEqual(self.game.spawn_time, 0)
        self.assertEqual(self.game.state, "playing")

    def test_each_pipe_pair_scores_once(self):
        self.game.reset()
        self.game.pipes = [PipePair(self.game.bird_rect.left - self.game.pipe.get_width() - 1, 500)]
        self.game.update(0)
        self.game.update(0)
        self.assertEqual(self.game.score, 1)

    def test_two_passed_pairs_both_score(self):
        self.game.reset()
        x = self.game.bird_rect.left - self.game.pipe.get_width() - 1
        self.game.pipes = [PipePair(x, 500), PipePair(x - 10, 500)]
        self.game.update(0)
        self.assertEqual(self.game.score, 2)

    def test_score_waits_for_complete_passage(self):
        self.game.reset()
        self.game.pipes = [PipePair(self.game.bird_rect.left - self.game.pipe.get_width() + 1, 500)]
        self.game.update(0)
        self.assertEqual(self.game.score, 0)

    def test_collision_with_top_bottom_and_pipe(self):
        for position, pipe in [(0, None), (FLOOR_Y, None), (200, PipePair(BIRD_X, 500))]:
            with self.subTest(position=position):
                self.game.reset()
                self.game.bird_y = position
                self.game.pipes = [pipe] if pipe else []
                self.game.update(0)
                self.assertEqual(self.game.state, "over")

    def test_no_points_on_a_collision_frame(self):
        self.game.reset()
        self.game.bird_y = FLOOR_Y
        self.game.pipes = [PipePair(-50, 500)]
        self.game.update(0)
        self.assertEqual(self.game.score, 0)

    def test_record_saved_at_end_and_not_reduced(self):
        self.game.reset()
        self.game.score = 6
        self.game.finish_round()
        self.assertEqual(load_record(self.path), 6)
        self.game.reset()
        self.game.score = 2
        self.game.finish_round()
        self.assertEqual(load_record(self.path), 6)

    def test_save_failure_keeps_game_usable(self):
        self.game.reset()
        self.game.score = 3
        with patch("main.save_record", side_effect=OSError("disk unavailable")):
            self.game.finish_round()
        self.assertEqual(self.game.state, "over")
        self.assertTrue(self.game.record_notice)
        self.game.flap()
        self.assertEqual(self.game.state, "playing")

    def test_motion_is_consistent_at_60_and_120_fps(self):
        results = []
        for fps in [60, 120]:
            self.game.reset()
            self.game.flap()
            self.game.pipes = [PipePair(500, 500)]
            for _ in range(int(fps * .2)):
                self.game.update(1 / fps)
            results.append((self.game.bird_y, self.game.pipes[0].x))
        self.assertAlmostEqual(results[0][0], results[1][0], places=6)
        self.assertAlmostEqual(results[0][1], results[1][1], places=6)

    def test_resize_and_all_screens_render(self):
        for size in [(320, 600), (900, 600), (200, 300)]:
            self.game.handle_event(pygame.event.Event(pygame.VIDEORESIZE, w=size[0], h=size[1]))
            self.assertEqual(self.game.screen.get_size(), size)
            for state in ["ready", "playing", "over", "paused", "history", "ranking", "settings", "countdown"]:
                self.game.state = state
                self.game.draw()

    def test_assets_load_from_another_working_directory(self):
        original = Path.cwd()
        try:
            os.chdir(self.temporary.name)
            other = Game(self.path)
            self.assertGreater(other.font.get_height(), 0)
        finally:
            os.chdir(original)

    def test_quit_and_escape_close_game(self):
        for event in [pygame.event.Event(pygame.QUIT), pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)]:
            self.game.running = True
            self.game.handle_event(event)
            self.assertFalse(self.game.running)

    def test_game_runs_without_audio_device(self):
        with patch("pygame.mixer.get_init", return_value=None):
            other = Game(self.path)
        self.assertEqual(other.sounds, {})
        other.flap()
        other.draw()
        self.assertEqual(other.state, "playing")

    def test_difficulty_changes_at_each_25_points(self):
        for score, level in [(0, 1), (24, 1), (25, 2), (49, 2), (50, 3), (75, 4), (100, 5), (125, 6), (1000, 6)]:
            self.assertEqual(difficulty_for(score).level, level)
        self.assertGreater(difficulty_for(125).speed, difficulty_for(0).speed)
        self.assertEqual(difficulty_for(1000).gap, 200)
        self.assertEqual(difficulty_for(1000).distance, 256)

    def test_new_difficulty_keeps_existing_pipe_gap(self):
        self.game.reset()
        existing = PipePair(400, 500)
        self.game.pipes = [existing]
        self.game.score = 25
        self.game.spawn_time = 1.4
        self.game.update(0)
        self.assertEqual(existing.gap, 300)
        self.assertEqual(self.game.pipes[-1].gap, 280)
        top, bottom = self.game.pipes[-1].rectangles(self.game.pipe.get_size())
        self.assertEqual(bottom.top - top.bottom, 280)

    def test_pause_freezes_physics_duration_and_scenery(self):
        self.game.flap()
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p))
        initial = (self.game.bird_y, self.game.duration, self.game.floor_offset, self.game.background_offset)
        self.game.update(2)
        self.assertEqual(initial, (self.game.bird_y, self.game.duration, self.game.floor_offset, self.game.background_offset))
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p))
        self.assertEqual(self.game.state, "countdown")
        self.game.update(3)
        self.assertEqual(self.game.state, "playing")

    def test_losing_focus_pauses_without_automatic_resume(self):
        self.game.flap()
        self.game.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        self.assertEqual(self.game.state, "paused")
        self.game.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
        self.assertEqual(self.game.state, "paused")

    def test_menu_navigation_and_history_return(self):
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertEqual(self.game.state, "ranking")
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertEqual(self.game.state, "ready")

    def test_mouse_menu_and_letterbox_coordinates(self):
        area = self.game.scene_geometry()
        point = (round(area.x + 288 * area.width / 576), round(area.y + 422 * area.height / 1024))
        self.game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point))
        self.assertEqual(self.game.state, "countdown")
        self.assertIsNone(self.game.logical_point((-10, -10)))

    def test_sound_toggle_suppresses_playback(self):
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m))
        self.assertTrue(self.game.muted)
        with patch.object(self.game, "sounds", {"flap": unittest.mock.Mock()}) as sounds:
            self.game.play_sound("flap")
            sounds["flap"].play.assert_not_called()

    def test_history_survives_reload_and_round_is_saved_once(self):
        self.game.reset()
        self.game.score = 27
        self.game.duration = 42.5
        self.game.finish_round()
        self.game.finish_round()
        profile = load_profile(self.path)
        self.assertEqual(len(profile["history"]), 1)
        self.assertEqual(profile["history"][0]["score"], 27)
        self.assertEqual(profile["history"][0]["level"], 2)
        self.assertEqual(profile["history"][0]["duration"], 42.5)

    def test_history_limit_does_not_erase_best_scores(self):
        for score in [150, *range(25)]:
            self.game.reset()
            self.game.score = score
            self.game.finish_round()
        profile = load_profile(self.path)
        self.assertEqual(len(profile["history"]), 20)
        self.assertEqual(len(profile["best"]), 5)
        self.assertEqual(profile["best"][0]["score"], 150)
        self.assertEqual(profile["high_score"], 150)

    def test_interrupted_round_is_recorded(self):
        self.game.flap()
        self.game.state = "paused"
        self.game.activate("menu")
        self.assertEqual(self.game.state, "ready")
        self.assertEqual(self.game.history[0]["result"], "interrompida")

    def test_user_data_location_is_outside_resources(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": self.temporary.name}):
            self.assertEqual(data_file(), Path(self.temporary.name) / "AdrianoGames" / "FlappyBird" / "profile.json")

    def test_history_pagination(self):
        for _ in range(6):
            self.game.reset()
            self.game.finish_round()
        self.game.activate("history")
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT))
        self.assertEqual(self.game.history_page, 1)
        self.game.draw()

    def test_countdown_freezes_round_and_ignores_flap(self):
        self.game.activate("play")
        initial = (self.game.bird_y, self.game.velocity, self.game.duration)
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
        self.game.update(2)
        self.assertEqual(self.game.state, "countdown")
        self.assertEqual(initial, (self.game.bird_y, self.game.velocity, self.game.duration))
        self.assertEqual(self.game.pipes, [])
        self.game.update(1)
        self.assertEqual(self.game.state, "playing")
        self.assertLess(self.game.velocity, 0)

    def test_resume_preserves_velocity_and_pipes(self):
        self.game.reset()
        self.game.velocity = 120
        self.game.pipes = [PipePair(400, 500)]
        self.game.state = "paused"
        self.game.activate("resume")
        self.game.update(3)
        self.assertEqual(self.game.state, "playing")
        self.assertEqual(self.game.velocity, 120)
        self.assertEqual(self.game.pipes[0].x, 400)
        self.assertEqual(self.game.duration, 0)

    def test_countdown_focus_loss_requires_new_countdown(self):
        self.game.activate("play")
        self.game.update(1)
        self.game.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        self.game.update(10)
        self.assertEqual(self.game.state, "paused")
        self.game.activate("resume")
        self.assertEqual(self.game.countdown, 3)

    def test_initial_countdown_does_not_create_empty_history(self):
        self.game.activate("play")
        self.game.activate("menu")
        self.assertEqual(self.game.history, [])
        self.game.reset()
        self.game.score = 4
        self.game.state = "paused"
        self.game.activate("resume")
        self.game.activate("menu")
        self.assertEqual(self.game.history[0]["score"], 4)

    def test_level_notice_only_at_a_new_level_and_expires(self):
        self.game.reset()
        self.game.score = 24
        self.game.pipes = [PipePair(self.game.bird_rect.left - self.game.pipe.get_width() - 1, 500)]
        self.game.update(0)
        self.assertEqual(self.game.score, 25)
        self.assertEqual(self.game.level_notice, 2.5)
        self.game.update(0.1)
        self.assertAlmostEqual(self.game.level_notice, 2.4)
        self.game.reset()
        self.assertEqual(self.game.level_notice, 0)

    def test_new_record_and_medals_thresholds(self):
        for score, name in [(0, "RUMO AOS 10 PONTOS"), (10, "BRONZE"), (25, "PRATA"), (50, "OURO"), (100, "PLATINA")]:
            self.assertEqual(medal_for(score)[0], name)
        self.game.reset()
        self.game.score = 10
        self.game.finish_round()
        self.assertTrue(self.game.new_record)
        self.game.reset()
        self.game.score = 10
        self.game.finish_round()
        self.assertFalse(self.game.new_record)

    def test_settings_survive_reload_and_volume_is_clamped(self):
        self.game.activate("mute")
        for _ in range(15):
            self.game.activate("volume_down")
        self.assertEqual(self.game.volume, 0)
        for _ in range(15):
            self.game.activate("volume_up")
        self.assertEqual(self.game.volume, 1)
        other = Game(self.path)
        self.assertTrue(other.muted)
        self.assertEqual(other.volume, 1)

    def test_invalid_settings_and_save_failure(self):
        path = self.game.settings_path
        for content in ["null", "broken", '{"volume": true, "muted": "yes", "fullscreen": 1}', '{"volume": 2}']:
            path.write_text(content, encoding="utf-8")
            self.assertEqual(load_settings(path), {"volume": 0.7, "muted": False, "fullscreen": False})
        with patch("main.save_settings", side_effect=OSError("disk unavailable")):
            self.game.activate("mute")
        self.assertTrue(self.game.record_notice)

    def test_fullscreen_toggle_preserves_window_size_and_preference(self):
        window_size = self.game.screen.get_size()
        with patch("pygame.display.set_mode", return_value=self.game.screen) as display:
            self.game.activate("fullscreen")
            self.assertTrue(self.game.fullscreen)
            self.assertTrue(load_settings(self.game.settings_path)["fullscreen"])
            display.assert_called_with((0, 0), pygame.FULLSCREEN)
            self.game.activate("fullscreen")
            display.assert_called_with(window_size, pygame.RESIZABLE)
        self.assertFalse(load_settings(self.game.settings_path)["fullscreen"])

    def test_fullscreen_failure_keeps_window_mode(self):
        with patch("pygame.display.set_mode", side_effect=pygame.error("unavailable")):
            self.game.activate("fullscreen")
        self.assertFalse(self.game.fullscreen)
        self.assertTrue(self.game.record_notice)


if __name__ == "__main__":
    unittest.main()
