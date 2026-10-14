"""Flappy Bird com menu, dificuldade progressiva e histórico local."""
from dataclasses import dataclass
from datetime import datetime
import argparse
import json
import math
import os
from pathlib import Path
import random

import pygame
from storage import data_file, load_profile, load_record, save_record, load_settings, save_settings

ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 576, 1024
FLOOR_Y = 900
BIRD_X = 110
GRAVITY = 1800.0
FLAP_SPEED = -600.0
PIPE_SPEED = 240.0
PIPE_INTERVAL = 1.4
PIPE_GAP = 300


@dataclass(frozen=True)
class Difficulty:
    level: int
    speed: float
    gap: int
    distance: int


def difficulty_for(score):
    step = min(max(score, 0) // 25, 5)
    return Difficulty(step + 1, PIPE_SPEED + step * 20, PIPE_GAP - step * 20, 336 - step * 16)


def medal_for(score):
    for minimum, name, color in [(100, "PLATINA", (175, 225, 235)), (50, "OURO", (245, 190, 65)),
                                  (25, "PRATA", (205, 215, 225)), (10, "BRONZE", (195, 132, 76))]:
        if score >= minimum:
            return name, color
    return "RUMO AOS 10 PONTOS", (100, 120, 125)


@dataclass
class PipePair:
    x: float
    gap_center: int
    scored: bool = False
    gap: int = PIPE_GAP

    def rectangles(self, size):
        width, height = size
        top = pygame.Rect(round(self.x), self.gap_center - self.gap // 2 - height, width, height)
        bottom = pygame.Rect(round(self.x), self.gap_center + self.gap // 2, width, height)
        return top, bottom


class Game:
    def __init__(self, record_path=None):
        pygame.init()
        self.record_path = Path(record_path) if record_path else data_file()
        source = self.record_path
        legacy = ROOT / "data" / "record.json"
        if record_path is None and not source.exists() and legacy.exists():
            source = legacy
        profile = load_profile(source)
        self.high_score, self.history = profile["high_score"], profile["history"]
        self.best = profile["best"]
        self.settings_path = self.record_path.with_name("settings.json")
        self.settings = load_settings(self.settings_path)
        self.volume = self.settings["volume"]
        self.muted = self.settings["muted"]
        self.fullscreen = False
        self.record_notice = ""
        desktop_width, desktop_height = pygame.display.get_desktop_sizes()[0]
        scale = min(0.8, max(1, desktop_width - 100) / WIDTH, max(1, desktop_height - 120) / HEIGHT)
        self.screen = pygame.display.set_mode((max(1, int(WIDTH * scale)), max(1, int(HEIGHT * scale))), pygame.RESIZABLE)
        self.window_size = self.screen.get_size()
        if self.settings["fullscreen"]:
            self.set_fullscreen(True)
        pygame.display.set_caption("Flappy Bird")
        self.canvas = pygame.Surface((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.background = self.image("background-day.png", alpha=False)
        self.floor = self.image("base.png", alpha=False)
        self.bird_frames = [self.image(f"bluebird-{frame}.png") for frame in ("downflap", "midflap", "upflap")]
        self.pipe = self.image("pipe-green.png")
        self.pipe_top = pygame.transform.flip(self.pipe, False, True)
        self.message = self.image("message.png")
        self.game_over = self.image("gameover.png")
        pygame.display.set_icon(self.bird_frames[1])
        self.font = pygame.font.Font(str(ROOT / "assets" / "04B_19.TTF"), 40)
        self.small_font = pygame.font.Font(str(ROOT / "assets" / "04B_19.TTF"), 24)
        self.tiny_font = pygame.font.Font(str(ROOT / "assets" / "04B_19.TTF"), 20)
        self.sounds = {}
        if pygame.mixer.get_init():
            for action, filename in {"flap": "sfx_wing.wav", "hit": "sfx_hit.wav", "point": "sfx_point.wav"}.items():
                try:
                    self.sounds[action] = pygame.mixer.Sound(str(ROOT / "sound" / filename))
                except pygame.error:
                    pass
        # Nuvens em pixel art desenhadas no mesmo estilo dos sprites existentes.
        self.cloud = pygame.Surface((144, 64), pygame.SRCALPHA)
        for rect in [(0, 32, 144, 24), (20, 16, 96, 32), (44, 0, 48, 48)]:
            pygame.draw.rect(self.cloud, (235, 250, 224, 145), rect)
        self.background_offset = self.cloud_offset = self.floor_offset = 0.0
        self.animation_time = 0.0
        self.running = True
        self.apply_volume()
        self.menu_index = 0
        self.history_page = 0
        self.reset()
        self.state = "ready"

    @staticmethod
    def image(filename, alpha=True):
        image = pygame.image.load(str(ROOT / "assets" / filename))
        return pygame.transform.scale2x(image.convert_alpha() if alpha else image.convert())

    def reset(self):
        self.bird_y = HEIGHT / 2
        self.velocity = 0.0
        self.bird_rect = self.bird_frames[0].get_rect(center=(BIRD_X, round(self.bird_y)))
        self.pipes = []
        self.spawn_time = self.duration = 0.0
        self.score = 0
        self.animation_time = 0.0
        self.menu_index = 0
        self.state = "playing"
        self.countdown = 0.0
        self.countdown_initial = False
        self.level_notice = 0.0
        self.new_record = False

    def start_countdown(self, initial=False):
        self.countdown_initial = initial
        self.countdown = 3.0
        self.state = "countdown"
        self.menu_index = 0

    def apply_volume(self):
        for sound in self.sounds.values():
            sound.set_volume(0 if self.muted else self.volume)
        if self.muted and pygame.mixer.get_init():
            pygame.mixer.stop()

    def set_fullscreen(self, enabled):
        try:
            if enabled:
                self.window_size = self.screen.get_size()
            self.screen = pygame.display.set_mode((0, 0) if enabled else self.window_size,
                                                  pygame.FULLSCREEN if enabled else pygame.RESIZABLE)
            self.fullscreen = enabled
            return True
        except pygame.error:
            self.record_notice = "Tela cheia indisponivel."
            return False

    def persist_settings(self):
        self.settings = {"volume": self.volume, "muted": self.muted, "fullscreen": self.fullscreen}
        self.apply_volume()
        try:
            save_settings(self.settings_path, self.settings)
            self.record_notice = ""
        except OSError:
            self.record_notice = "Configuracoes nao salvas no disco."

    def play_sound(self, name):
        if not self.muted and name in self.sounds:
            self.sounds[name].play()

    def flap(self):
        if self.state in ("paused", "countdown"):
            return
        if self.state != "playing":
            self.reset()
        self.velocity = FLAP_SPEED
        self.play_sound("flap")

    def buttons(self):
        if self.state == "ready":
            items = [("JOGAR", "play"), ("MELHORES PONTUACOES", "ranking"), ("HISTORICO", "history"), ("CONFIGURACOES", "settings"), ("SAIR", "exit")]
            start = 390
        elif self.state == "over":
            items, start = [("JOGAR NOVAMENTE", "play"), ("MENU INICIAL", "menu")], 640
        elif self.state == "paused":
            items, start = [("CONTINUAR", "resume"), ("MENU INICIAL", "menu")], 480
        elif self.state in ("history", "ranking"):
            items, start = [("VOLTAR", "menu")], 800
        elif self.state == "settings":
            items, start = [("SOM: " + ("DESLIGADO" if self.muted else "LIGADO"), "mute"),
                            ("VOLUME -", "volume_down"), ("VOLUME +", "volume_up"),
                            ("TELA: " + ("CHEIA" if self.fullscreen else "JANELA"), "fullscreen"),
                            ("VOLTAR", "menu")], 390
        else:
            return []
        return [(pygame.Rect(78, start + i * 78, 420, 64), label, action) for i, (label, action) in enumerate(items)]

    def activate(self, action):
        if action == "play":
            self.reset()
            self.start_countdown(initial=True)
        elif action in ("mute", "volume_down", "volume_up", "fullscreen"):
            if action == "mute":
                self.muted = not self.muted
            elif action == "fullscreen":
                if not self.set_fullscreen(not self.fullscreen):
                    return
            else:
                self.volume = round(max(0, min(1, self.volume + (-0.1 if action == "volume_down" else 0.1))), 1)
            self.persist_settings()
            return
        elif action == "exit":
            self.running = False
        elif action == "resume":
            self.start_countdown(initial=self.countdown_initial)
        elif action == "menu":
            if self.state in ("playing", "paused", "countdown"):
                self.finish_round("interrompida")
            self.state = "ready"
        else:
            self.state = action
            self.history_page = 0
        self.menu_index = 0

    def scene_geometry(self):
        window_width, window_height = self.screen.get_size()
        scale = min(window_width / WIDTH, window_height / HEIGHT)
        size = (max(1, round(WIDTH * scale)), max(1, round(HEIGHT * scale)))
        return pygame.Rect((window_width - size[0]) // 2, (window_height - size[1]) // 2, *size)

    def logical_point(self, point):
        area = self.scene_geometry()
        if not area.collidepoint(point):
            return None
        return ((point[0] - area.x) * WIDTH / area.width, (point[1] - area.y) * HEIGHT / area.height)

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            if self.state in ("playing", "paused", "countdown"):
                self.finish_round("interrompida")
            self.running = False
        elif event.type == pygame.WINDOWFOCUSLOST and self.state in ("playing", "countdown"):
            self.state = "paused"
            self.menu_index = 0
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_m:
                self.activate("mute")
            elif event.key == pygame.K_F11:
                self.activate("fullscreen")
                if self.state in ("playing", "countdown"):
                    self.state = "paused"
            elif event.key == pygame.K_p and self.state in ("playing", "paused", "countdown"):
                if self.state == "paused":
                    self.activate("resume")
                else:
                    self.state = "paused"
                self.menu_index = 0
            elif event.key == pygame.K_ESCAPE:
                if self.state == "ready":
                    self.running = False
                elif self.state in ("playing", "countdown"):
                    self.state = "paused"
                    self.menu_index = 0
                elif self.state == "paused":
                    self.activate("resume")
                else:
                    self.activate("menu")
            elif self.state == "playing" and event.key in (pygame.K_SPACE, pygame.K_UP):
                self.flap()
            elif self.state != "playing":
                buttons = self.buttons()
                if event.key in (pygame.K_UP, pygame.K_DOWN) and buttons:
                    self.menu_index = (self.menu_index + (-1 if event.key == pygame.K_UP else 1)) % len(buttons)
                elif event.key in (pygame.K_SPACE, pygame.K_RETURN) and buttons:
                    self.activate(buttons[self.menu_index][2])
                elif self.state == "history" and event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    pages = max(1, math.ceil(len(self.history) / 5))
                    self.history_page = (self.history_page + (-1 if event.key == pygame.K_LEFT else 1)) % pages
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            point = self.logical_point(event.pos)
            if point is None:
                return
            if self.state == "playing":
                self.flap()
            else:
                for rect, _, action in self.buttons():
                    if rect.collidepoint(point):
                        self.activate(action)
                        return
                if self.state == "history":
                    pages = max(1, math.ceil(len(self.history) / 5))
                    if pygame.Rect(80, 730, 180, 48).collidepoint(point):
                        self.history_page = (self.history_page - 1) % pages
                    elif pygame.Rect(316, 730, 180, 48).collidepoint(point):
                        self.history_page = (self.history_page + 1) % pages
        elif event.type == pygame.VIDEORESIZE:
            if not self.fullscreen:
                self.window_size = (max(1, event.w), max(1, event.h))
                self.screen = pygame.display.set_mode(self.window_size, pygame.RESIZABLE)

    def finish_round(self, result="concluida"):
        if self.state not in ("playing", "paused", "countdown"):
            return
        if self.countdown_initial:
            self.state = "over"
            return
        self.state = "over"
        if result == "concluida":
            self.play_sound("hit")
        self.new_record = self.score > self.high_score
        self.high_score = max(self.score, self.high_score)
        self.history.insert(0, {"score": self.score, "duration": round(self.duration, 1), "level": difficulty_for(self.score).level, "date": datetime.now().astimezone().isoformat(timespec="seconds"), "result": result})
        self.history = self.history[:20]
        self.best = sorted([self.history[0], *self.best], key=lambda row: row["score"], reverse=True)[:5]
        try:
            save_record(self.record_path, self.high_score, self.history, self.best)
            self.record_notice = ""
        except OSError:
            self.record_notice = "Dados nao salvos no disco."
        self.menu_index = 0

    def update(self, dt):
        if self.state == "paused":
            return
        if self.state == "countdown":
            self.countdown = max(0, self.countdown - dt)
            if self.countdown == 0:
                self.state = "playing"
                if self.countdown_initial:
                    self.countdown_initial = False
                    self.flap()
            return
        self.animation_time += dt
        self.floor_offset = (self.floor_offset + 120 * dt) % self.floor.get_width()
        self.background_offset = (self.background_offset + 8 * dt) % WIDTH
        self.cloud_offset = (self.cloud_offset + 22 * dt) % (WIDTH + 180)
        if self.state != "playing":
            return
        self.duration += dt
        self.level_notice = max(0, self.level_notice - dt)
        self.bird_y += self.velocity * dt + 0.5 * GRAVITY * dt * dt
        self.velocity += GRAVITY * dt
        self.bird_rect.centery = round(self.bird_y)
        difficulty = difficulty_for(self.score)
        interval = difficulty.distance / difficulty.speed
        self.spawn_time += dt
        while self.spawn_time >= interval:
            self.spawn_time -= interval
            self.pipes.append(PipePair(WIDTH + self.pipe.get_width(), random.randint(260, 650), gap=difficulty.gap))
        for pair in self.pipes:
            pair.x -= difficulty.speed * dt
        hitbox = self.bird_rect.inflate(-8, -8)
        collided = self.bird_rect.top <= 0 or self.bird_rect.bottom >= FLOOR_Y
        collided = collided or any(hitbox.colliderect(rect) for pair in self.pipes for rect in pair.rectangles(self.pipe.get_size()))
        if collided:
            self.finish_round()
            return
        for pair in self.pipes:
            if not pair.scored and pair.x + self.pipe.get_width() < self.bird_rect.left:
                pair.scored = True
                self.score += 1
                self.play_sound("point")
        if difficulty_for(self.score).level > difficulty.level:
            self.level_notice = 2.5
        self.pipes = [pair for pair in self.pipes if pair.x + self.pipe.get_width() > 0]

    def text(self, message, y, small=False, tiny=False, color=(255, 255, 255), x=None):
        font = self.tiny_font if tiny else self.small_font if small else self.font
        shadow = font.render(message, True, (35, 50, 55))
        foreground = font.render(message, True, color)
        rect = foreground.get_rect(center=(WIDTH // 2, y)) if x is None else foreground.get_rect(midleft=(x, y))
        self.canvas.blit(shadow, rect.move(2, 3))
        self.canvas.blit(foreground, rect)

    def panel(self, rectangle):
        surface = pygame.Surface(rectangle.size, pygame.SRCALPHA)
        surface.fill((30, 45, 50, 215))
        self.canvas.blit(surface, rectangle)

    def draw_buttons(self):
        mouse = self.logical_point(pygame.mouse.get_pos())
        for index, (rect, label, action) in enumerate(self.buttons()):
            selected = index == self.menu_index or (mouse is not None and rect.collidepoint(mouse))
            pygame.draw.rect(self.canvas, (230, 173, 63) if selected or action == "play" else (242, 222, 161), rect, border_radius=6)
            pygame.draw.rect(self.canvas, (89, 65, 39), rect, 3, border_radius=6)
            if selected:
                pygame.draw.polygon(self.canvas, (89, 65, 39), [(rect.x + 12, rect.centery - 7), (rect.x + 12, rect.centery + 7), (rect.x + 22, rect.centery)])
            text = self.small_font.render(label, True, (58, 46, 31))
            self.canvas.blit(text, text.get_rect(center=rect.center))

    def draw_scores(self):
        self.panel(pygame.Rect(54, 265, 468, 440))
        self.text("HISTORICO" if self.state == "history" else "TOP 5", 125)
        ranking = self.state == "ranking"
        if not (self.best if ranking else self.history):
            self.text("NENHUMA PARTIDA AINDA", 360, small=True)
            self.text("JOGUE PARA REGISTRAR PONTOS", 420, tiny=True)
            return
        rows = self.best if ranking else self.history[self.history_page * 5:(self.history_page + 1) * 5]
        if not ranking:
            average = sum(row["score"] for row in self.history) / len(self.history)
            self.text(f"ULTIMAS {len(self.history)} PARTIDAS", 210, small=True)
            self.text(f"MEDIA: {average:.1f}   RECORDE: {self.high_score}", 240, tiny=True)
        else:
            self.text("SUAS CINCO MELHORES PARTIDAS", 220, tiny=True)
        for label, x in [("PTS", 100), ("DATA", 205), ("TEMPO", 390)]:
            self.text(label, 290, tiny=True, x=x, color=(242, 222, 161))
        for index, item in enumerate(rows):
            y = 335 + index * 70
            date = datetime.fromisoformat(item["date"]).strftime("%d/%m %H:%M")
            self.text(str(item["score"]), y, small=True, x=100)
            self.text(date, y, tiny=True, x=205)
            seconds = int(item["duration"])
            self.text(f"{seconds // 60}:{seconds % 60:02}", y, tiny=True, x=390)
            status = " / INTERROMPIDA" if item["result"] == "interrompida" else ""
            position = index + 1 if ranking else self.history_page * 5 + index + 1
            self.text(f"{position:02}   NIVEL {item['level']}{status}", y + 26, tiny=True, x=100, color=(185, 210, 210))
        if not ranking:
            pages = max(1, math.ceil(len(self.history) / 5))
            self.text(f"PAGINA {self.history_page + 1}/{pages}", 170, tiny=True)
            for x, label in [(80, "< ANTERIOR"), (316, "PROXIMA >")]:
                pygame.draw.rect(self.canvas, (242, 222, 161), (x, 730, 180, 48), border_radius=4)
                text = self.tiny_font.render(label, True, (58, 46, 31))
                self.canvas.blit(text, text.get_rect(center=(x + 90, 754)))

    def draw(self):
        offset = round(self.background_offset)
        self.canvas.blit(self.background, (-offset, 0))
        self.canvas.blit(self.background, (WIDTH - offset, 0))
        for x, y in [(60, 100), (340, 210), (620, 80)]:
            cloud_x = (x - self.cloud_offset) % (WIDTH + 180) - 144
            self.canvas.blit(self.cloud, (cloud_x, y))
        if self.state in ("playing", "paused", "over", "countdown"):
            for pair in self.pipes:
                top, bottom = pair.rectangles(self.pipe.get_size())
                self.canvas.blit(self.pipe_top, top)
                self.canvas.blit(self.pipe, bottom)
            frame = self.bird_frames[int(self.animation_time / 0.15) % len(self.bird_frames)]
            frame = pygame.transform.rotozoom(frame, max(-70, min(25, -self.velocity / 12)), 1)
            self.canvas.blit(frame, frame.get_rect(center=self.bird_rect.center))
        x = -round(self.floor_offset)
        self.canvas.blit(self.floor, (x, FLOOR_Y))
        self.canvas.blit(self.floor, (x + self.floor.get_width(), FLOOR_Y))
        if self.state == "ready":
            # O título original vem do sprite de apresentação, sem novo logotipo.
            self.canvas.blit(self.message, (104, 145), pygame.Rect(0, 0, 368, 140))
            frame = self.bird_frames[int(self.animation_time / .15) % 3]
            self.canvas.blit(frame, frame.get_rect(center=(WIDTH // 2, 310 + int(math.sin(self.animation_time * 3) * 10))))
            self.text(f"RECORDE: {self.high_score}", 110)
            self.text("SETAS: MENU   ENTER: ESCOLHER", 830, tiny=True)
        elif self.state == "playing":
            self.text(str(self.score), 100)
            self.text(f"NIVEL {difficulty_for(self.score).level}", 150, tiny=True)
            if self.level_notice > 0:
                self.panel(pygame.Rect(54, 904, 468, 58))
                self.text(f"NIVEL {difficulty_for(self.score).level}: MAIS DESAFIO!", 920, tiny=True)
                self.text("CANOS MAIS PROXIMOS E ESTREITOS", 946, tiny=True)
        elif self.state == "over":
            self.canvas.blit(self.game_over, self.game_over.get_rect(center=(WIDTH // 2, 180)))
            self.panel(pygame.Rect(68, 260, 440, 340))
            name, color = medal_for(self.score)
            pygame.draw.polygon(self.canvas, (70, 130, 170), [(260, 275), (280, 275), (303, 325), (283, 325)])
            pygame.draw.polygon(self.canvas, (70, 130, 170), [(296, 275), (316, 275), (293, 325), (273, 325)])
            pygame.draw.circle(self.canvas, color, (288, 335), 34)
            pygame.draw.circle(self.canvas, (255, 240, 180), (288, 335), 24, 3)
            self.text(name, 390, small=True, color=color)
            self.text(f"PONTOS: {self.score}", 440)
            self.text(f"RECORDE: {self.high_score}", 490, small=True)
            self.text(f"TEMPO: {int(self.duration)}s   NIVEL: {difficulty_for(self.score).level}", 535, tiny=True)
            if self.new_record:
                self.text("NOVO RECORDE!", 575, small=True, color=(245, 190, 65))
        elif self.state == "countdown":
            self.panel(pygame.Rect(100, 275, 376, 190))
            self.text("PREPARE-SE", 325, small=True)
            self.text(str(max(1, math.ceil(self.countdown))), 390)
        elif self.state == "paused":
            overlay = pygame.Surface((WIDTH, FLOOR_Y), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 120))
            self.canvas.blit(overlay, (0, 0))
            self.text("PAUSADO", 310)
            self.text("P OU ESC: CONTINUAR", 390, small=True)
        elif self.state == "settings":
            self.text("CONFIGURACOES", 150)
            self.panel(pygame.Rect(78, 220, 420, 120))
            self.text(f"VOLUME: {round(self.volume * 100)}%", 255, small=True)
            self.text("F11: ALTERNAR TELA CHEIA", 305, tiny=True)
            self.text("AJUSTES SALVOS AUTOMATICAMENTE", 830, tiny=True)
        else:
            self.draw_scores()
        self.draw_buttons()
        if self.record_notice and self.state != "playing":
            self.text(self.record_notice, 870, tiny=True)
        self.text("P: PAUSA   M: " + ("SOM OFF" if self.muted else "SOM ON"), 978, tiny=True)
        self.text("ESC: SAIR" if self.state == "ready" else "ESPACO / SETA / CLIQUE: VOAR" if self.state == "playing" else "ESC: PAUSAR" if self.state == "countdown" else "ESC: VOLTAR", 1005, tiny=True)
        area = self.scene_geometry()
        self.screen.fill((20, 25, 30))
        self.screen.blit(pygame.transform.scale(self.canvas, area.size), area)
        pygame.display.flip()

    def run(self):
        try:
            while self.running:
                dt = min(self.clock.tick(60) / 1000, 1 / 30)
                for event in pygame.event.get():
                    self.handle_event(event)
                if self.running:
                    self.update(dt)
                    self.draw()
        finally:
            pygame.quit()


def check_build(output):
    """Confere o pacote em modo sem janela e sem alterar os dados do jogador."""
    output.mkdir(parents=True, exist_ok=True)
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    game = Game(output / "profile.json")
    try:
        game.draw()
        pygame.image.save(game.screen, str(output / "menu.png"))
        game.activate("play")
        game.draw()
        pygame.image.save(game.screen, str(output / "contagem.png"))
        game.update(3)
        game.score, game.duration = 27, 45.0
        game.level_notice = 2.5
        game.pipes = [PipePair(420, 500, gap=difficulty_for(27).gap)]
        game.draw()
        pygame.image.save(game.screen, str(output / "partida.png"))
        game.state = "paused"
        initial = game.bird_y
        game.update(1)
        assert game.bird_y == initial
        game.draw()
        pygame.image.save(game.screen, str(output / "pausa.png"))
        game.state = "playing"
        game.finish_round()
        game.draw()
        pygame.image.save(game.screen, str(output / "resultado.png"))
        assert load_profile(output / "profile.json")["history"][0]["score"] == 27
        game.activate("history")
        game.draw()
        pygame.image.save(game.screen, str(output / "historico.png"))
        game.activate("ranking")
        game.draw()
        pygame.image.save(game.screen, str(output / "ranking.png"))
        game.activate("settings")
        game.draw()
        pygame.image.save(game.screen, str(output / "configuracoes.png"))
        (output / "result.json").write_text(json.dumps({"ok": True, "assets": True, "audio_loaded": bool(game.sounds), "history": True, "pause": True}), encoding="utf-8")
    finally:
        pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flappy Bird")
    parser.add_argument("--check-build", type=Path, metavar="PASTA", help="Validar o pacote usando dados de teste nessa pasta")
    args = parser.parse_args()
    if args.check_build:
        try:
            check_build(args.check_build)
        except Exception as error:
            args.check_build.mkdir(parents=True, exist_ok=True)
            (args.check_build / "result.json").write_text(json.dumps({"ok": False, "error": str(error)}), encoding="utf-8")
            raise SystemExit(1)
    else:
        Game().run()
