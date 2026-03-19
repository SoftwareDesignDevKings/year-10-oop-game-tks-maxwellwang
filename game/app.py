import hashlib
import os
import random
import shlex
import signal
import subprocess
import sys
import tempfile

import pygame
import settings
from game.enemy import Enemy
from game.pickup import Pickup
from game.player import Player
try:
    import pygame.mixer as pygame_mixer
except ModuleNotFoundError:
    pygame_mixer = None

WIDTH = settings.WIDTH
HEIGHT = settings.HEIGHT
FPS = settings.FPS
SPAWN_MARGIN = settings.SPAWN_MARGIN
ENEMY_SCALE_FACTOR = settings.ENEMY_SCALE_FACTOR
PLAYER_SCALE_FACTOR = settings.PLAYER_SCALE_FACTOR
FLOOR_TILE_SCALE_FACTOR = settings.FLOOR_TILE_SCALE_FACTOR
PUSHBACK_DISTANCE = settings.PUSHBACK_DISTANCE
BGM_VOLUME = 1.0

UPGRADE_POOL = [
    ("bigger_projectile", "Bigger Projectile"),
    ("bigger_melee_range", "Bigger Melee Range"),
    ("higher_damage", "Higher Damage (Both)"),
    ("more_projectiles", "More Projectiles (+1)"),
    ("less_mana_cost", "Less Mana Cost"),
    ("higher_mana_cap", "Higher Mana Cap"),
    ("higher_mana_regen", "Higher Mana Regen"),
    ("less_projectile_cooldown", "Less Projectile Cooldown"),
    ("increase_magnetic_range", "Increase Magnetic Range"),
    ("faster_movement", "Faster Movement"),
    ("reinforced_health", "Reinforced Health"),
    ("faster_melee", "Faster Melee Cooldown"),
]
SPECIAL_UPGRADE = ("special_360_melee", "Special: 360 Melee Range")
REPEATABLE_UPGRADES = {
    "increase_magnetic_range",
    "faster_movement",
    "reinforced_health",
    "faster_melee",
}

def find_bgm_path(folder="assets"):
    if not os.path.isdir(folder):
        return None

    candidates = []
    for file_name in sorted(os.listdir(folder)):
        if not file_name.lower().endswith(".mp3"):
            continue
        file_path = os.path.join(folder, file_name)
        if os.path.isfile(file_path):
            candidates.append(file_path)

    if not candidates:
        return None

    for file_path in candidates:
        lower_name = os.path.basename(file_path).lower()
        if "bgm" in lower_name or "music" in lower_name:
            return file_path
    return candidates[0]


def load_image(path, use_alpha=True):
    try:
        image = pygame.image.load(path)
    except pygame.error as original_error:
        if not path.lower().endswith(".png"):
            raise original_error

        base_name = os.path.splitext(os.path.basename(path))[0]
        cache_key = hashlib.sha1(os.path.abspath(path).encode("utf-8")).hexdigest()[:12]
        cache_dir = os.path.join(tempfile.gettempdir(), "pygame_image_cache")
        os.makedirs(cache_dir, exist_ok=True)
        bmp_path = os.path.join(cache_dir, f"{base_name}_{cache_key}.bmp")

        source_mtime = os.path.getmtime(path)
        cache_mtime = os.path.getmtime(bmp_path) if os.path.exists(bmp_path) else 0
        if cache_mtime < source_mtime:
            try:
                subprocess.run(
                    ["sips", "-s", "format", "bmp", path, "--out", bmp_path],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except (FileNotFoundError, subprocess.CalledProcessError):
                raise original_error

        try:
            image = pygame.image.load(bmp_path)
        except pygame.error:
            raise original_error

    if use_alpha:
        return image.convert_alpha()
    return image.convert()


def load_frames(prefix, frame_count, scale_factor=1, folder="assets"):
    frames = []
    for i in range(frame_count):
        image_path = os.path.join(folder, f"{prefix}_{i}.png")
        img = load_image(image_path, use_alpha=True)

        if scale_factor != 1:
            w = img.get_width() * scale_factor
            h = img.get_height() * scale_factor
            img = pygame.transform.scale(img, (w, h))

        frames.append(img)
    return frames

def load_floor_tiles(folder="assets"):
    floor_tiles = []
    for i in range(8):
        path = os.path.join(folder, f"floor_{i}.png")
        tile = load_image(path, use_alpha=False)

        if FLOOR_TILE_SCALE_FACTOR != 1:
            tw = tile.get_width() * FLOOR_TILE_SCALE_FACTOR
            th = tile.get_height() * FLOOR_TILE_SCALE_FACTOR
            tile = pygame.transform.scale(tile, (tw, th))

        floor_tiles.append(tile)
    return floor_tiles

def load_assets():
    assets = {}
    player_idle = []
    player_run = []
    try:
        player_idle = load_frames("player_idle", 4, scale_factor=PLAYER_SCALE_FACTOR)
        player_run = load_frames("player_run", 4, scale_factor=PLAYER_SCALE_FACTOR)
    except (pygame.error, FileNotFoundError):
        pass

    player_attack = []
    if player_idle:
        try:
            player_attack = load_frames("player_attack", 4, scale_factor=PLAYER_SCALE_FACTOR)
        except (pygame.error, FileNotFoundError):
            pass

    assets["player"] = {
        "idle": player_idle,
        "run": player_run,
        "attack": player_attack,
    }

    try:
        assets["enemies"] = {
            "demon": load_frames("demon", 4, scale_factor=ENEMY_SCALE_FACTOR),
            "orc": load_frames("orc", 4, scale_factor=ENEMY_SCALE_FACTOR),
            "undead": load_frames("undead", 4, scale_factor=ENEMY_SCALE_FACTOR),
        }
    except (pygame.error, FileNotFoundError):
        assets["enemies"] = {}

    try:
        assets["floor_tiles"] = load_floor_tiles()
    except (pygame.error, FileNotFoundError):
        assets["floor_tiles"] = []

    return assets

class Game:
    def __init__(self):
        pygame.init()

        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Shooter Game")
        self.clock = pygame.time.Clock()
        self.running = True

        font_path = os.path.join("assets", "PressStart2P.ttf")
        if os.path.exists(font_path):
            self.font_small = pygame.font.Font(font_path, 14)
            self.font_medium = pygame.font.Font(font_path, 20)
        else:
            self.font_small = pygame.font.SysFont(None, 24)
            self.font_medium = pygame.font.SysFont(None, 32)

        self.bgm_backend = None
        self.bgm_error = None
        self.bgm_process = None
        self.bgm_path = find_bgm_path()
        self.start_bgm()

        self.assets = load_assets()
        self.reset_game()
        self.main_menu_active = True
        self.main_menu_option_rects = {}

    def start_bgm(self):
        if not self.bgm_path:
            self.bgm_error = "no mp3 file found in assets/"
            return
        self.cleanup_orphan_bgm()
        if pygame_mixer is not None:
            try:
                if not pygame_mixer.get_init():
                    pygame_mixer.init()
                pygame_mixer.music.load(self.bgm_path)
                pygame_mixer.music.set_volume(BGM_VOLUME)
                pygame_mixer.music.play(-1)
                self.bgm_backend = "pygame"
                self.bgm_error = None
                return
            except (AttributeError, NotImplementedError, pygame.error) as error:
                self.bgm_error = f"pygame mixer failed: {error}"

        # fallback for macOS builds where pygame mixer is unavailable
        if sys.platform == "darwin":
            try:
                loop_cmd = f"while true; do afplay {shlex.quote(self.bgm_path)}; done"
                self.bgm_process = subprocess.Popen(
                    ["/bin/sh", "-c", loop_cmd],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                self.bgm_backend = "afplay"
                self.bgm_error = None
                return
            except OSError as error:
                if self.bgm_error:
                    self.bgm_error = f"{self.bgm_error}; afplay failed: {error}"
                else:
                    self.bgm_error = f"afplay failed: {error}"

        if self.bgm_error:
            print(f"[BGM] {self.bgm_error}")

    def cleanup_orphan_bgm(self):
        if sys.platform != "darwin" or not self.bgm_path:
            return

        track_name = os.path.basename(self.bgm_path)
        patterns = [f"afplay {self.bgm_path}", f"afplay {track_name}"]
        for pattern in patterns:
            subprocess.run(
                ["pkill", "-f", pattern],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )

    def stop_bgm(self):
        if pygame_mixer is not None:
            try:
                if pygame_mixer.get_init():
                    pygame_mixer.music.stop()
            except (AttributeError, NotImplementedError, pygame.error):
                pass

        if self.bgm_process is not None:
            if self.bgm_process.poll() is None:
                try:
                    os.killpg(self.bgm_process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    self.bgm_process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(self.bgm_process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            self.bgm_process = None

        self.cleanup_orphan_bgm()

    def reset_game(self):
        self.background = self.build_background()
        self.world_offset_x = 0.0
        self.world_offset_y = 0.0
        self.game_start_ms = pygame.time.get_ticks()

        player_assets = self.get_player_assets()
        self.player = Player(WIDTH // 2, HEIGHT // 2, player_assets)
        self.round = 1
        self.start_round()

        self.enemies = []
        self.spawn_enemies_for_round()
        self.projectiles = []
        self.pickups = []
        self.gold = 0
        self.total_xp = 0
        self.level = 1
        self.level_xp = 0
        self.xp_to_next_level = settings.LEVEL_UP_BASE_XP
        self.pending_level_ups = 0
        self.upgrade_active = False
        self.upgrade_choices = []
        self.upgrade_option_rects = []
        self.picked_normal_upgrades = set()
        self.special_upgrade_taken = False
        self.settings_active = False
        self.settings_option_rects = {}
        self.player_damage_cooldown = 0
        self.game_over = False
        self.game_over_option_rects = {}
        self.main_menu_option_rects = {}

    def shift_world(self, dx, dy):
        if dx == 0 and dy == 0:
            return

        self.world_offset_x += dx
        self.world_offset_y += dy

        for enemy in self.enemies:
            enemy.x += dx
            enemy.y += dy
            enemy.rect.center = (int(enemy.x), int(enemy.y))

        for projectile in self.projectiles:
            projectile.x += dx
            projectile.y += dy
            projectile.rect.center = (int(projectile.x), int(projectile.y))

        shift_x = int(dx)
        shift_y = int(dy)
        if shift_x != 0 or shift_y != 0:
            for pickup in self.pickups:
                pickup.rect.move_ip(shift_x, shift_y)

    def build_background(self):
        floor_tiles = self.assets.get("floor_tiles", [])
        if floor_tiles:
            return self.create_random_background(WIDTH, HEIGHT, floor_tiles)

        bg = pygame.Surface((WIDTH, HEIGHT))
        bg.fill((30, 30, 30))
        return bg

    def get_player_assets(self):
        if self.assets.get("player", {}).get("idle"):
            return self.assets

        placeholder = pygame.Surface((24, 24), pygame.SRCALPHA)
        pygame.draw.rect(placeholder, (250, 220, 90), (0, 0, 24, 24))
        return {
            "player": {
                "idle": [placeholder],
                "run": [placeholder],
                "attack": [],
            }
        }

    def create_random_background(self, width, height, floor_tiles):
        bg = pygame.Surface((width, height))
        tile_w = floor_tiles[0].get_width()
        tile_h = floor_tiles[0].get_height()

        for y in range(0, height, tile_h):
            for x in range(0, width, tile_w):
                tile = random.choice(floor_tiles)
                bg.blit(tile, (x, y))

        return bg

    def start_round(self):
        self.kills_in_round = 0
        self.kills_target = 10 + ((self.round - 1) * 3)
        self.enemies_to_spawn = self.kills_target
        self.max_alive_enemies = min(6, 1 + (self.round // 2))

    def spawn_enemies_for_round(self):
        while self.enemies_to_spawn > 0 and len(self.enemies) < self.max_alive_enemies:
            enemy = self.create_enemy()
            if enemy is None:
                break
            self.enemies.append(enemy)
            self.enemies_to_spawn -= 1

    def create_enemy(self):
        enemy_assets = self.assets.get("enemies", {})
        available = [enemy_type for enemy_type, frames in enemy_assets.items() if frames]
        if not available:
            return None

        chosen_type = random.choice(available)
        left = SPAWN_MARGIN
        right = WIDTH - SPAWN_MARGIN
        top = SPAWN_MARGIN
        bottom = HEIGHT - SPAWN_MARGIN

        side = random.choice(["top", "bottom", "left", "right"])
        if side == "top":
            enemy_x = random.randint(left, right)
            enemy_y = top
        elif side == "bottom":
            enemy_x = random.randint(left, right)
            enemy_y = bottom
        elif side == "left":
            enemy_x = left
            enemy_y = random.randint(top, bottom)
        else:
            enemy_x = right
            enemy_y = random.randint(top, bottom)

        elapsed_min = (pygame.time.get_ticks() - self.game_start_ms) / 60000.0
        round_index = max(0, self.round - 1)
        type_stats = settings.ENEMY_TYPE_STATS.get(chosen_type, {})
        speed_mult = float(type_stats.get("speed_mult", 1.0))
        health_mult = float(type_stats.get("health_mult", 1.0))

        base_speed = (
            settings.DEFAULT_ENEMY_SPEED
            + (elapsed_min * settings.ENEMY_SPEED_PER_MIN)
            + (round_index * settings.ENEMY_SPEED_PER_ROUND)
        )
        enemy_speed = min(
            base_speed * speed_mult,
            settings.ENEMY_SPEED_CAP * speed_mult,
        )
        base_health = int(
            settings.ENEMY_MAX_HEALTH
            * (settings.ENEMY_HP_GROWTH_PER_ROUND ** round_index)
            * (settings.ENEMY_HP_GROWTH_PER_MIN ** elapsed_min)
        )
        enemy_health = int(base_health * health_mult)

        enemy = Enemy(
            enemy_x,
            enemy_y,
            chosen_type,
            enemy_assets,
            speed=enemy_speed,
        )
        enemy.health = max(1, enemy_health)
        return enemy

    def run(self):
        while self.running:
            self.clock.tick(FPS)
            self.handle_events()
            self.update()
            self.draw()

        self.stop_bgm()
        pygame.quit()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                continue

            if self.main_menu_active:
                self.handle_main_menu_selection(event)
                continue

            if self.settings_active:
                self.handle_settings_selection(event)
                continue

            if self.game_over:
                self.handle_game_over_selection(event)
                continue

            if self.upgrade_active:
                self.handle_upgrade_selection(event)
                continue

            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.settings_active = True
                continue

            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    self.handle_melee_attack()
                elif event.button == 3:
                    self.handle_ranged_attack(event.pos)

    def start_game_from_menu(self):
        self.reset_game()
        self.main_menu_active = False

    def handle_main_menu_selection(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_s):
                self.start_game_from_menu()
            elif event.key in (pygame.K_q, pygame.K_ESCAPE):
                self.running = False
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            start_rect = self.main_menu_option_rects.get("start")
            quit_rect = self.main_menu_option_rects.get("quit")
            if start_rect and start_rect.collidepoint(event.pos):
                self.start_game_from_menu()
            elif quit_rect and quit_rect.collidepoint(event.pos):
                self.running = False

    def handle_game_over_selection(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_r, pygame.K_RETURN, pygame.K_SPACE):
                self.reset_game()
            elif event.key in (pygame.K_q, pygame.K_ESCAPE):
                self.running = False
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            restart_rect = self.game_over_option_rects.get("restart")
            quit_rect = self.game_over_option_rects.get("quit")
            if restart_rect and restart_rect.collidepoint(event.pos):
                self.reset_game()
            elif quit_rect and quit_rect.collidepoint(event.pos):
                self.running = False

    def handle_settings_selection(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.settings_active = False
            elif event.key == pygame.K_r:
                self.reset_game()
            elif event.key == pygame.K_q:
                self.running = False
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            resume_rect = self.settings_option_rects.get("resume")
            restart_rect = self.settings_option_rects.get("restart")
            quit_rect = self.settings_option_rects.get("quit")
            if resume_rect and resume_rect.collidepoint(event.pos):
                self.settings_active = False
            elif restart_rect and restart_rect.collidepoint(event.pos):
                self.reset_game()
            elif quit_rect and quit_rect.collidepoint(event.pos):
                self.running = False

    def handle_upgrade_selection(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_1:
                self.select_upgrade(0)
            elif event.key == pygame.K_2:
                self.select_upgrade(1)
            elif event.key == pygame.K_3:
                self.select_upgrade(2)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index, rect in enumerate(self.upgrade_option_rects):
                if rect.collidepoint(event.pos):
                    self.select_upgrade(index)
                    return

    def grant_xp(self, amount):
        self.total_xp += amount
        self.level_xp += amount

        while self.level_xp >= self.xp_to_next_level:
            self.level_xp -= self.xp_to_next_level
            self.level += 1
            self.pending_level_ups += 1
            self.xp_to_next_level = int(
                self.xp_to_next_level * settings.LEVEL_UP_GROWTH
                + settings.LEVEL_UP_GROWTH_FLAT
            )

        if self.pending_level_ups > 0 and not self.upgrade_active:
            self.open_upgrade_menu()

    def open_upgrade_menu(self):
        base_pool = [
            {"id": key, "label": label}
            for key, label in UPGRADE_POOL
            if key in REPEATABLE_UPGRADES or key not in self.picked_normal_upgrades
        ]
        include_special = (
            not self.special_upgrade_taken
            and (random.random() < 0.2 or len(base_pool) < 3)
        )

        choices = []
        if include_special:
            choices.append({"id": SPECIAL_UPGRADE[0], "label": SPECIAL_UPGRADE[1]})

        remaining_slots = 3 - len(choices)
        if remaining_slots > 0 and base_pool:
            normal_count = min(remaining_slots, len(base_pool))
            choices.extend(random.sample(base_pool, normal_count))

        if not choices:
            return

        random.shuffle(choices)
        self.upgrade_choices = choices

        self.upgrade_active = True
        self.upgrade_option_rects = []

    def select_upgrade(self, option_index):
        if option_index < 0 or option_index >= len(self.upgrade_choices):
            return

        upgrade_id = self.upgrade_choices[option_index]["id"]
        self.apply_upgrade(upgrade_id)

        self.pending_level_ups = max(0, self.pending_level_ups - 1)
        self.upgrade_active = False
        self.upgrade_choices = []
        self.upgrade_option_rects = []

        if self.pending_level_ups > 0:
            self.open_upgrade_menu()

    def apply_upgrade(self, upgrade_id):
        if upgrade_id == "bigger_projectile":
            self.player.projectile_radius += settings.UPGRADE_PROJECTILE_RADIUS_INC
            self.picked_normal_upgrades.add(upgrade_id)
            return

        if upgrade_id == "bigger_melee_range":
            self.player.melee_range += settings.UPGRADE_MELEE_RANGE_INC
            self.picked_normal_upgrades.add(upgrade_id)
            return

        if upgrade_id == "higher_damage":
            self.player.melee_damage += settings.UPGRADE_DAMAGE_INC
            self.player.ranged_damage += settings.UPGRADE_DAMAGE_INC
            self.picked_normal_upgrades.add(upgrade_id)
            return

        if upgrade_id == "more_projectiles":
            self.player.projectile_count = min(
                settings.MAX_PROJECTILE_COUNT,
                self.player.projectile_count + settings.UPGRADE_PROJECTILE_COUNT_INC,
            )
            self.picked_normal_upgrades.add(upgrade_id)
            return

        if upgrade_id == "less_mana_cost":
            self.player.ranged_cost = max(
                settings.MIN_RANGED_MANA_COST,
                self.player.ranged_cost - settings.UPGRADE_MANA_COST_REDUCE,
            )
            self.picked_normal_upgrades.add(upgrade_id)
            return

        if upgrade_id == "higher_mana_cap":
            self.player.max_mana += settings.UPGRADE_MAX_MANA_INC
            self.player.mana = min(
                self.player.max_mana,
                self.player.mana + settings.UPGRADE_MAX_MANA_INC,
            )
            self.picked_normal_upgrades.add(upgrade_id)
            return

        if upgrade_id == "higher_mana_regen":
            self.player.mana_regen += settings.UPGRADE_MANA_REGEN_INC
            self.picked_normal_upgrades.add(upgrade_id)
            return

        if upgrade_id == "less_projectile_cooldown":
            self.player.ranged_cooldown = max(
                settings.MIN_RANGED_COOLDOWN,
                self.player.ranged_cooldown - settings.UPGRADE_RANGED_COOLDOWN_REDUCE,
            )
            self.picked_normal_upgrades.add(upgrade_id)
            return

        if upgrade_id == "increase_magnetic_range":
            self.player.pickup_range += settings.UPGRADE_PICKUP_RANGE_INC
            return

        if upgrade_id == "faster_movement":
            self.player.speed += settings.UPGRADE_SPEED_INC
            return

        if upgrade_id == "reinforced_health":
            self.player.max_health += settings.UPGRADE_HEALTH_INC
            self.player.health = min(
                self.player.max_health,
                self.player.health
                + settings.UPGRADE_HEALTH_INC
                + settings.UPGRADE_HEAL_ON_GAIN,
            )
            return

        if upgrade_id == "faster_melee":
            self.player.melee_cooldown = max(
                settings.MIN_MELEE_COOLDOWN,
                self.player.melee_cooldown - settings.UPGRADE_MELEE_COOLDOWN_REDUCE,
            )
            return

        if upgrade_id == "special_360_melee":
            self.special_upgrade_taken = True
            self.player.melee_range = max(
                self.player.melee_range,
                settings.SPECIAL_MELEE_RANGE,
            )

    def handle_melee_attack(self):
        if not self.player.attack_melee():
            return

        for enemy in self.enemies[:]:
            dx = enemy.x - self.player.x
            dy = enemy.y - self.player.y
            if dx * dx + dy * dy <= self.player.melee_range * self.player.melee_range:
                enemy.set_knockback(self.player.x, self.player.y, PUSHBACK_DISTANCE)
                if enemy.take_damage(self.player.melee_damage):
                    self.defeat_enemy(enemy)

    def handle_ranged_attack(self, target_pos):
        projectiles = self.player.cast_spell(target_pos[0], target_pos[1])
        if projectiles:
            self.projectiles.extend(projectiles)

    def defeat_enemy(self, enemy):
        self.spawn_pickups(enemy.x, enemy.y)
        if enemy in self.enemies:
            self.enemies.remove(enemy)
            self.kills_in_round += 1

        if (
            self.kills_in_round >= self.kills_target
            and not self.enemies
            and self.enemies_to_spawn == 0
        ):
            self.round += 1
            self.start_round()

    def spawn_pickups(self, x, y):
        pickup_offset = settings.PICKUP_SIZE + 2
        self.pickups.append(Pickup(x - pickup_offset, y - pickup_offset, "gold"))
        self.pickups.append(Pickup(x + pickup_offset, y + pickup_offset, "xp"))

    def update_projectiles(self):
        for projectile in self.projectiles[:]:
            projectile.update()
            if projectile.is_offscreen():
                self.projectiles.remove(projectile)
                continue

            for enemy in self.enemies[:]:
                if projectile.rect.colliderect(enemy.rect):
                    enemy.set_knockback(self.player.x, self.player.y, PUSHBACK_DISTANCE)
                    if enemy.take_damage(projectile.damage):
                        self.defeat_enemy(enemy)
                    self.projectiles.remove(projectile)
                    break

    def update_pickups(self):
        pickup_range_sq = self.player.pickup_range * self.player.pickup_range
        for pickup in self.pickups[:]:
            dx = pickup.rect.centerx - self.player.rect.centerx
            dy = pickup.rect.centery - self.player.rect.centery
            in_pickup_range = (dx * dx + dy * dy) <= pickup_range_sq
            if self.player.rect.colliderect(pickup.rect) or in_pickup_range:
                if pickup.kind == "gold":
                    self.gold += pickup.value
                else:
                    self.grant_xp(pickup.value)
                self.pickups.remove(pickup)

    def update_player_hits(self):
        if self.player_damage_cooldown > 0:
            self.player_damage_cooldown -= 1
            return

        for enemy in self.enemies:
            if enemy.rect.colliderect(self.player.rect):
                self.player.take_damage(settings.ENEMY_CONTACT_DAMAGE)
                self.player_damage_cooldown = settings.ENEMY_CONTACT_COOLDOWN
                break

    def trigger_game_over(self):
        self.game_over = True
        self.settings_active = False
        self.settings_option_rects = {}
        self.upgrade_active = False
        self.upgrade_choices = []
        self.upgrade_option_rects = []
        self.game_over_option_rects = {}

    def update(self):
        if self.main_menu_active or self.game_over or self.settings_active or self.upgrade_active:
            return

        self.spawn_enemies_for_round()
        move_x, move_y = self.player.handle_input()
        self.shift_world(-move_x, -move_y)
        self.player.set_position(WIDTH // 2, HEIGHT // 2)
        self.player.update()
        for enemy in self.enemies:
            enemy.update(self.player)
        self.update_projectiles()
        self.update_pickups()
        if self.upgrade_active:
            return
        self.update_player_hits()
        if self.player.health <= 0:
            self.trigger_game_over()

    def draw_health_bar(self):
        bar_x = 20
        bar_y = 20
        bar_w = 220
        bar_h = 18
        ratio = 0
        if self.player.max_health > 0:
            ratio = self.player.health / self.player.max_health

        pygame.draw.rect(self.screen, (55, 55, 55), (bar_x, bar_y, bar_w, bar_h))
        pygame.draw.rect(self.screen, (200, 45, 45), (bar_x, bar_y, int(bar_w * ratio), bar_h))
        pygame.draw.rect(self.screen, (230, 230, 230), (bar_x, bar_y, bar_w, bar_h), 2)

    def draw_upgrade_menu(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 185))
        self.screen.blit(overlay, (0, 0))

        title = self.font_medium.render("LEVEL UP", True, (255, 255, 255))
        subtitle = self.font_small.render("Pick 1 Upgrade", True, (220, 220, 220))
        instruction = self.font_small.render("Click or Press 1 / 2 / 3", True, (190, 190, 190))

        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 120))
        self.screen.blit(subtitle, (WIDTH // 2 - subtitle.get_width() // 2, 155))
        self.screen.blit(instruction, (WIDTH // 2 - instruction.get_width() // 2, 185))

        card_w = 620
        card_h = 70
        gap = 18
        start_y = 235
        start_x = (WIDTH - card_w) // 2
        self.upgrade_option_rects = []

        for index, option in enumerate(self.upgrade_choices):
            card_rect = pygame.Rect(start_x, start_y + (index * (card_h + gap)), card_w, card_h)
            self.upgrade_option_rects.append(card_rect)

            pygame.draw.rect(self.screen, (40, 44, 52), card_rect)
            pygame.draw.rect(self.screen, (220, 220, 220), card_rect, 2)

            option_text = self.font_small.render(
                f"{index + 1}. {option['label']}",
                True,
                (250, 250, 250),
            )
            text_y = card_rect.y + (card_rect.height - option_text.get_height()) // 2
            self.screen.blit(option_text, (card_rect.x + 20, text_y))

    def draw_settings_menu(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        self.screen.blit(overlay, (0, 0))

        title = self.font_medium.render("SETTINGS", True, (255, 255, 255))
        instruction = self.font_small.render(
            "Esc Resume  R Restart  Q Quit",
            True,
            (210, 210, 210),
        )

        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 165))
        self.screen.blit(
            instruction,
            (WIDTH // 2 - instruction.get_width() // 2, 205),
        )

        resume_rect = pygame.Rect((WIDTH // 2) - 145, 265, 290, 58)
        restart_rect = pygame.Rect((WIDTH // 2) - 145, 335, 290, 58)
        quit_rect = pygame.Rect((WIDTH // 2) - 145, 405, 290, 58)
        self.settings_option_rects = {
            "resume": resume_rect,
            "restart": restart_rect,
            "quit": quit_rect,
        }

        pygame.draw.rect(self.screen, (45, 100, 65), resume_rect)
        pygame.draw.rect(self.screen, (235, 235, 235), resume_rect, 2)
        pygame.draw.rect(self.screen, (85, 85, 115), restart_rect)
        pygame.draw.rect(self.screen, (235, 235, 235), restart_rect, 2)
        pygame.draw.rect(self.screen, (120, 45, 45), quit_rect)
        pygame.draw.rect(self.screen, (235, 235, 235), quit_rect, 2)

        resume_text = self.font_small.render("Resume (Esc)", True, (245, 245, 245))
        restart_text = self.font_small.render("Restart (R)", True, (245, 245, 245))
        quit_text = self.font_small.render("Quit (Q)", True, (245, 245, 245))

        self.screen.blit(
            resume_text,
            (
                resume_rect.x + (resume_rect.width - resume_text.get_width()) // 2,
                resume_rect.y + (resume_rect.height - resume_text.get_height()) // 2,
            ),
        )
        self.screen.blit(
            restart_text,
            (
                restart_rect.x + (restart_rect.width - restart_text.get_width()) // 2,
                restart_rect.y + (restart_rect.height - restart_text.get_height()) // 2,
            ),
        )
        self.screen.blit(
            quit_text,
            (
                quit_rect.x + (quit_rect.width - quit_text.get_width()) // 2,
                quit_rect.y + (quit_rect.height - quit_text.get_height()) // 2,
            ),
        )

    def draw_game_over_menu(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        self.screen.blit(overlay, (0, 0))

        title = self.font_medium.render("GAME OVER", True, (255, 110, 110))
        summary = self.font_small.render(
            f"Gold {self.gold}  XP {self.total_xp}  Lvl {self.level}",
            True,
            (220, 220, 220),
        )
        instruction = self.font_small.render(
            "Press R to Restart or Q to Quit",
            True,
            (200, 200, 200),
        )

        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 180))
        self.screen.blit(summary, (WIDTH // 2 - summary.get_width() // 2, 225))
        self.screen.blit(
            instruction,
            (WIDTH // 2 - instruction.get_width() // 2, 255),
        )

        restart_rect = pygame.Rect((WIDTH // 2) - 190, 320, 180, 58)
        quit_rect = pygame.Rect((WIDTH // 2) + 10, 320, 180, 58)
        self.game_over_option_rects = {
            "restart": restart_rect,
            "quit": quit_rect,
        }

        pygame.draw.rect(self.screen, (45, 100, 65), restart_rect)
        pygame.draw.rect(self.screen, (235, 235, 235), restart_rect, 2)
        pygame.draw.rect(self.screen, (120, 45, 45), quit_rect)
        pygame.draw.rect(self.screen, (235, 235, 235), quit_rect, 2)

        restart_text = self.font_small.render("Restart (R)", True, (245, 245, 245))
        quit_text = self.font_small.render("Quit (Q)", True, (245, 245, 245))
        self.screen.blit(
            restart_text,
            (
                restart_rect.x + (restart_rect.width - restart_text.get_width()) // 2,
                restart_rect.y + (restart_rect.height - restart_text.get_height()) // 2,
            ),
        )
        self.screen.blit(
            quit_text,
            (
                quit_rect.x + (quit_rect.width - quit_text.get_width()) // 2,
                quit_rect.y + (quit_rect.height - quit_text.get_height()) // 2,
            ),
        )

    def draw_main_menu(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 210))
        self.screen.blit(overlay, (0, 0))

        title = self.font_medium.render("SHOOTER GAME", True, (245, 245, 245))
        subtitle = self.font_small.render("Press Enter or Click Start", True, (210, 210, 210))
        future_text = self.font_small.render("More menu options coming soon", True, (165, 165, 165))

        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 160))
        self.screen.blit(subtitle, (WIDTH // 2 - subtitle.get_width() // 2, 205))
        self.screen.blit(future_text, (WIDTH // 2 - future_text.get_width() // 2, 250))

        start_rect = pygame.Rect((WIDTH // 2) - 145, 315, 290, 58)
        quit_rect = pygame.Rect((WIDTH // 2) - 145, 385, 290, 58)
        self.main_menu_option_rects = {
            "start": start_rect,
            "quit": quit_rect,
        }

        pygame.draw.rect(self.screen, (45, 100, 65), start_rect)
        pygame.draw.rect(self.screen, (235, 235, 235), start_rect, 2)
        pygame.draw.rect(self.screen, (120, 45, 45), quit_rect)
        pygame.draw.rect(self.screen, (235, 235, 235), quit_rect, 2)

        start_text = self.font_small.render("Start (Enter)", True, (245, 245, 245))
        quit_text = self.font_small.render("Quit (Q)", True, (245, 245, 245))

        self.screen.blit(
            start_text,
            (
                start_rect.x + (start_rect.width - start_text.get_width()) // 2,
                start_rect.y + (start_rect.height - start_text.get_height()) // 2,
            ),
        )
        self.screen.blit(
            quit_text,
            (
                quit_rect.x + (quit_rect.width - quit_text.get_width()) // 2,
                quit_rect.y + (quit_rect.height - quit_text.get_height()) // 2,
            ),
        )

    def draw(self):
        bg_offset_x = int(self.world_offset_x) % WIDTH
        bg_offset_y = int(self.world_offset_y) % HEIGHT
        for x in (-WIDTH, 0, WIDTH):
            for y in (-HEIGHT, 0, HEIGHT):
                self.screen.blit(self.background, (bg_offset_x + x, bg_offset_y + y))

        for enemy in self.enemies:
            enemy.draw(self.screen)
        for pickup in self.pickups:
            pickup.draw(self.screen)
        for projectile in self.projectiles:
            projectile.draw(self.screen)
        self.player.draw(self.screen)

        self.draw_health_bar()

        mana_text = self.font_small.render(
            f"Mana: {int(self.player.mana)}/{self.player.max_mana}",
            True,
            (80, 220, 255),
        )
        self.screen.blit(mana_text, (20, 45))

        loot_text = self.font_small.render(
            f"Gold: {self.gold}  XP: {self.total_xp}  Lvl: {self.level}",
            True,
            (230, 230, 230),
        )
        self.screen.blit(loot_text, (20, 70))

        xp_text = self.font_small.render(
            f"Next Level: {self.level_xp}/{self.xp_to_next_level}",
            True,
            (120, 230, 120),
        )
        self.screen.blit(xp_text, (20, 95))

        round_text = self.font_small.render(
            f"Round: {self.round}  Kills: {self.kills_in_round}/{self.kills_target}",
            True,
            (240, 220, 120),
        )
        self.screen.blit(round_text, (20, 120))

        if self.main_menu_active:
            self.draw_main_menu()
        elif self.game_over:
            self.draw_game_over_menu()
        elif self.settings_active:
            self.draw_settings_menu()
        elif self.upgrade_active:
            self.draw_upgrade_menu()

        pygame.display.flip()
